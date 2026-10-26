from __future__ import annotations

import json
import os
import resource
import selectors
import signal
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class RunnerConfig:
    time_limit_s: float
    memory_limit_mb: int
    output_limit_bytes: int
    compile_flags: tuple[str, ...] = ("-std=c11", "-O2", "-Wall", "-Wextra")


@dataclass(frozen=True)
class CompileResult:
    compiled: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: float
    unavailable: bool = False
    error: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    ran: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    signal: int | None = None
    output_truncated: bool = False
    unavailable: bool = False
    error: str | None = None


@dataclass(frozen=True)
class ToolAnalysisResult:
    tool: str
    available: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    output_truncated: bool = False
    error: str | None = None


class SandboxRunner(Protocol):
    def availability(self) -> tuple[bool, str]: ...

    def compile(self, source: str, config: RunnerConfig) -> CompileResult: ...

    def run(
        self,
        source: str,
        stdin: str,
        config: RunnerConfig,
        extra_compile_flags: tuple[str, ...] = (),
    ) -> ExecutionResult: ...


def _bounded_text(value: bytes | str, limit: int) -> tuple[str, bool]:
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    if len(text.encode("utf-8")) > limit:
        encoded = text.encode("utf-8")[:limit]
        return encoded.decode("utf-8", errors="replace"), True
    return text, False


def _set_process_limits(memory_limit_mb: int, cpu_limit_s: float) -> None:
    """Apply conservative inherited limits before entering the sandbox."""

    memory_bytes = max(16, memory_limit_mb) * 1024 * 1024
    cpu_seconds = max(1, int(cpu_limit_s) + 1)
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_STACK, (8 * 1024 * 1024, 8 * 1024 * 1024))


def _bounded_process(
    command: list[str],
    *,
    stdin_path: Path | None,
    timeout_s: float,
    output_limit: int,
    memory_limit_mb: int,
    cpu_limit_s: float,
) -> tuple[int | None, bytes, bytes, bool, bool, float]:
    """Run a process with bounded output and kill its whole process group."""

    stdin_handle = stdin_path.open("rb") if stdin_path else subprocess.DEVNULL
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        stdin=stdin_handle,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        preexec_fn=lambda: _set_process_limits(memory_limit_mb, cpu_limit_s),
    )
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    assert process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    stdout = bytearray()
    stderr = bytearray()
    output_truncated = False
    timed_out = False
    deadline = started + timeout_s
    try:
        while selector.get_map():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                break
            for key, _ in selector.select(min(0.1, remaining)):
                chunk = os.read(key.fileobj.fileno(), 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target = stdout if key.data == "stdout" else stderr
                if len(target) < output_limit:
                    target.extend(chunk[: output_limit - len(target)])
                if len(chunk) > max(0, output_limit - len(target)):
                    output_truncated = True
            if process.poll() is not None and not selector.get_map():
                break
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        if stdin_handle is not subprocess.DEVNULL:
            stdin_handle.close()
    duration = (time.perf_counter() - started) * 1000
    return process.returncode, bytes(stdout), bytes(stderr), timed_out, output_truncated, duration


class DockerSandboxRunner:
    """Run a fixed trusted runner inside Docker.

    No source is compiled or executed on the host. The host process only talks
    to the fixed container entrypoint over stdin and treats all output as data.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def availability(self) -> tuple[bool, str]:
        docker = shutil.which("docker")
        if not docker:
            return False, "Docker CLI is not installed; execution is fail-closed."
        inspect = subprocess.run(
            [docker, "image", "inspect", self.settings.docker_image],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if inspect.returncode != 0:
            return False, f"sandbox image {self.settings.docker_image!r} is unavailable"
        return True, f"Docker sandbox image {self.settings.docker_image} is ready"

    def _invoke(self, payload: dict[str, Any], timeout_s: float) -> dict[str, Any] | None:
        docker = shutil.which("docker")
        if not docker:
            return None
        command = [
            docker,
            "run",
            "--rm",
            "-i",
            "--network=none",
            "--user=1000:1000",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=16m",
            "--tmpfs",
            "/work:rw,nosuid,nodev,size=64m,mode=1777",
            "--env",
            "TMPDIR=/work",
            "--pids-limit",
            "64",
            "--memory",
            f"{max(256 if payload.get('mode') == 'compile' else 16, int(payload.get('memory_limit_mb', 128)))}m",
            "--cpus",
            "1",
            "--ulimit",
            "fsize=1048576:1048576",
            "--ulimit",
            "stack=8388608:8388608",
            self.settings.docker_image,
            "/usr/local/bin/autograder-runner",
        ]
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        output = completed.stdout
        try:
            result = json.loads(output)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": "sandbox returned malformed JSON",
                "stderr": completed.stderr[-4000:],
                "exit_code": completed.returncode,
            }
        if not isinstance(result, dict):
            return {"ok": False, "error": "sandbox returned a non-object response"}
        return result

    def availability_error(self) -> str:
        available, detail = self.availability()
        return detail if not available else ""

    def compile(self, source: str, config: RunnerConfig) -> CompileResult:
        available, detail = self.availability()
        if not available:
            return CompileResult(False, None, "", "", 0.0, unavailable=True, error=detail)
        started = time.perf_counter()
        payload = {
            "mode": "compile",
            "source": source,
            "compile_flags": list(config.compile_flags),
            "memory_limit_mb": config.memory_limit_mb,
            "output_limit_bytes": config.output_limit_bytes,
        }
        response = self._invoke(payload, max(2.0, self.settings.docker_timeout_s))
        duration = (time.perf_counter() - started) * 1000
        if response is None:
            return CompileResult(
                False,
                None,
                "",
                "",
                duration,
                unavailable=True,
                error="sandbox invocation timed out",
            )
        stdout, _ = _bounded_text(response.get("stdout", ""), config.output_limit_bytes)
        stderr, _ = _bounded_text(response.get("stderr", ""), config.output_limit_bytes)
        return CompileResult(
            compiled=bool(response.get("compiled", False)),
            exit_code=response.get("exit_code"),
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration,
            error=response.get("error"),
        )

    def run(
        self,
        source: str,
        stdin: str,
        config: RunnerConfig,
        extra_compile_flags: tuple[str, ...] = (),
    ) -> ExecutionResult:
        available, detail = self.availability()
        if not available:
            return ExecutionResult(False, None, "", "", 0.0, unavailable=True, error=detail)
        started = time.perf_counter()
        payload = {
            "mode": "run",
            "source": source,
            "stdin": stdin,
            "compile_flags": list(config.compile_flags + extra_compile_flags),
            "time_limit_s": config.time_limit_s,
            "memory_limit_mb": config.memory_limit_mb,
            "output_limit_bytes": config.output_limit_bytes,
        }
        response = self._invoke(
            payload, max(2.0, self.settings.docker_timeout_s, config.time_limit_s + 2)
        )
        duration = (time.perf_counter() - started) * 1000
        if response is None:
            return ExecutionResult(
                False,
                None,
                "",
                "",
                duration,
                unavailable=True,
                error="sandbox invocation timed out",
            )
        stdout, stdout_truncated = _bounded_text(
            response.get("stdout", ""), config.output_limit_bytes
        )
        stderr, stderr_truncated = _bounded_text(
            response.get("stderr", ""), config.output_limit_bytes
        )
        return ExecutionResult(
            ran=bool(response.get("ran", False)),
            exit_code=response.get("exit_code"),
            stdout=stdout,
            stderr=stderr,
            duration_ms=float(response.get("duration_ms", duration)),
            timed_out=bool(response.get("timed_out", False)),
            signal=response.get("signal"),
            output_truncated=stdout_truncated or stderr_truncated,
            error=response.get("error"),
        )


class BubblewrapSandboxRunner:
    """Run GCC and submissions in an unprivileged Linux namespace sandbox.

    Bubblewrap creates an empty mount namespace. Only the system toolchain is
    exposed read-only; the submission workspace is the sole writable host path.
    PID, user, mount, IPC, UTS and network namespaces are isolated, and the
    child inherits strict rlimits. This is a Linux-native alternative to the
    Docker adapter and fails closed when bubblewrap or GCC is unavailable.
    """

    _RO_BIND_ROOTS = ("/usr", "/lib", "/lib64", "/etc", "/usr/local")

    def __init__(self, settings: Settings):
        self.settings = settings

    def _binary(self) -> str | None:
        configured = self.settings.bubblewrap_path
        return (
            configured
            if Path(configured).is_absolute() and Path(configured).exists()
            else shutil.which(configured)
        )

    def availability(self) -> tuple[bool, str]:
        bwrap = self._binary()
        if not bwrap:
            return False, "Bubblewrap is not installed; install the Linux bubblewrap package."
        gcc = shutil.which("gcc")
        if not gcc:
            return False, "GCC is not installed; the bubblewrap runner cannot compile C11 source."
        return True, f"Bubblewrap namespace sandbox is ready ({bwrap})"

    def _command(self, workdir: Path, command: list[str]) -> list[str]:
        bwrap = self._binary()
        if not bwrap:
            raise RuntimeError("bubblewrap is unavailable")
        args = [
            bwrap,
            "--unshare-all",
            "--unshare-user",
            "--disable-userns",
            "--assert-userns-disabled",
            "--cap-drop",
            "ALL",
            "--die-with-parent",
            "--new-session",
        ]
        for root in self._RO_BIND_ROOTS:
            if Path(root).exists():
                args.extend(["--ro-bind", root, root])
        args.extend(
            [
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--bind",
                str(workdir),
                "/work",
                "--chdir",
                "/work",
                "--clearenv",
                "--setenv",
                "PATH",
                "/usr/bin:/bin:/usr/local/bin",
                "--setenv",
                "HOME",
                "/tmp",
                "--uid",
                str(self.settings.bubblewrap_uid),
                "--gid",
                str(self.settings.bubblewrap_gid),
                "--",
                *command,
            ]
        )
        return args

    @staticmethod
    def _workspace() -> tempfile.TemporaryDirectory[str]:
        workspace = tempfile.TemporaryDirectory(prefix="autograder-bwrap-")
        Path(workspace.name).chmod(0o777)
        return workspace

    def _compile_in_workspace(
        self,
        workspace: Path,
        source: str,
        config: RunnerConfig,
        extra_compile_flags: tuple[str, ...] = (),
    ) -> CompileResult:
        source_path = workspace / "submission.c"
        source_path.write_text(source, encoding="utf-8")
        source_path.chmod(0o644)
        gcc = shutil.which("gcc") or "/usr/bin/gcc"
        command = self._command(
            workspace,
            [
                gcc,
                *config.compile_flags,
                *extra_compile_flags,
                "/work/submission.c",
                "-o",
                "/work/program",
            ],
        )
        try:
            exit_code, stdout, stderr, timed_out, truncated, duration = _bounded_process(
                command,
                stdin_path=None,
                timeout_s=max(2.0, self.settings.docker_timeout_s),
                output_limit=config.output_limit_bytes,
                memory_limit_mb=max(256, config.memory_limit_mb),
                cpu_limit_s=max(2.0, self.settings.docker_timeout_s),
            )
        except (OSError, RuntimeError) as exc:
            return CompileResult(False, None, "", str(exc), 0.0, unavailable=True, error=str(exc))
        stdout_text, stdout_cut = _bounded_text(stdout, config.output_limit_bytes)
        stderr_text, stderr_cut = _bounded_text(stderr, config.output_limit_bytes)
        output_was_cut = truncated or stdout_cut or stderr_cut
        if timed_out:
            return CompileResult(
                False,
                exit_code,
                stdout_text,
                stderr_text,
                duration,
                error="bubblewrap compile timed out",
            )
        return CompileResult(
            compiled=exit_code == 0 and (workspace / "program").exists(),
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
            duration_ms=duration,
            error="compiler output was truncated" if output_was_cut else None,
        )

    def compile(self, source: str, config: RunnerConfig) -> CompileResult:
        available, detail = self.availability()
        if not available:
            return CompileResult(False, None, "", "", 0.0, unavailable=True, error=detail)
        with self._workspace() as workspace_name:
            workspace = Path(workspace_name)
            return self._compile_in_workspace(workspace, source, config)

    def run(
        self,
        source: str,
        stdin: str,
        config: RunnerConfig,
        extra_compile_flags: tuple[str, ...] = (),
    ) -> ExecutionResult:
        available, detail = self.availability()
        if not available:
            return ExecutionResult(False, None, "", "", 0.0, unavailable=True, error=detail)
        with self._workspace() as workspace_name:
            workspace = Path(workspace_name)
            compile_result = self._compile_in_workspace(
                workspace, source, config, extra_compile_flags=extra_compile_flags
            )
            if compile_result.unavailable:
                return ExecutionResult(
                    False,
                    None,
                    "",
                    compile_result.error or "bubblewrap compiler unavailable",
                    compile_result.duration_ms,
                    unavailable=True,
                    error=compile_result.error,
                )
            if not compile_result.compiled:
                return ExecutionResult(
                    False,
                    compile_result.exit_code,
                    compile_result.stdout,
                    compile_result.stderr,
                    compile_result.duration_ms,
                    error="submission failed to compile",
                )
            input_path = workspace / "stdin.txt"
            input_path.write_text(stdin, encoding="utf-8")
            input_path.chmod(0o644)
            command = self._command(workspace, ["/work/program"])
            try:
                exit_code, stdout, stderr, timed_out, truncated, duration = _bounded_process(
                    command,
                    stdin_path=input_path,
                    timeout_s=max(2.0, config.time_limit_s + 2),
                    output_limit=config.output_limit_bytes,
                    memory_limit_mb=config.memory_limit_mb,
                    cpu_limit_s=config.time_limit_s,
                )
            except (OSError, RuntimeError) as exc:
                return ExecutionResult(
                    False, None, "", str(exc), 0.0, unavailable=True, error=str(exc)
                )
            stdout_text, stdout_cut = _bounded_text(stdout, config.output_limit_bytes)
            stderr_text, stderr_cut = _bounded_text(stderr, config.output_limit_bytes)
            resource_limited = exit_code in {137, -signal.SIGXCPU, -signal.SIGKILL}
            return ExecutionResult(
                ran=True,
                exit_code=exit_code,
                stdout=stdout_text,
                stderr=stderr_text,
                duration_ms=duration,
                timed_out=timed_out or resource_limited,
                signal=9
                if exit_code == 137
                else -exit_code
                if exit_code is not None and exit_code < 0
                else None,
                output_truncated=truncated or stdout_cut or stderr_cut,
                error="bubblewrap execution exceeded a resource limit"
                if timed_out or resource_limited
                else None,
            )

    def analyze_tool(
        self,
        source: str,
        tool: str,
        arguments: tuple[str, ...],
        output_limit: int,
        timeout_s: float = 15.0,
    ) -> ToolAnalysisResult:
        """Run a source-only analyzer inside the same namespace policy."""

        available, detail = self.availability()
        tool_path = shutil.which(tool)
        if not available:
            return ToolAnalysisResult(tool, False, None, "", "", 0.0, error=detail)
        if not tool_path:
            return ToolAnalysisResult(
                tool, False, None, "", "", 0.0, error=f"{tool} is not installed"
            )
        with self._workspace() as workspace_name:
            workspace = Path(workspace_name)
            source_path = workspace / "submission.c"
            source_path.write_text(source, encoding="utf-8")
            source_path.chmod(0o644)
            command = self._command(workspace, [tool_path, *arguments, "/work/submission.c"])
            try:
                exit_code, stdout, stderr, timed_out, truncated, duration = _bounded_process(
                    command,
                    stdin_path=None,
                    timeout_s=timeout_s,
                    output_limit=output_limit,
                    memory_limit_mb=256,
                    cpu_limit_s=timeout_s,
                )
            except (OSError, RuntimeError) as exc:
                return ToolAnalysisResult(tool, False, None, "", str(exc), 0.0, error=str(exc))
            stdout_text, stdout_cut = _bounded_text(stdout, output_limit)
            stderr_text, stderr_cut = _bounded_text(stderr, output_limit)
            return ToolAnalysisResult(
                tool=tool,
                available=True,
                exit_code=exit_code,
                stdout=stdout_text,
                stderr=stderr_text,
                duration_ms=duration,
                timed_out=timed_out,
                output_truncated=truncated or stdout_cut or stderr_cut,
                error="tool timed out" if timed_out else None,
            )


class FakeSandboxRunner:
    """Deterministic test double; it never compiles or executes source code."""

    def __init__(
        self,
        compile_result: CompileResult | None = None,
        executions: dict[str, ExecutionResult] | None = None,
        default_execution: ExecutionResult | None = None,
        delay_ms: int = 0,
    ):
        self.compile_result = compile_result or CompileResult(True, 0, "", "", 1.0)
        self.executions = executions or {}
        self.default_execution = default_execution or ExecutionResult(True, 0, "", "", 1.0)
        self.delay_ms = max(0, delay_ms)
        self.calls: list[dict[str, Any]] = []

    def _delay(self) -> None:
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)

    def availability(self) -> tuple[bool, str]:
        return True, "deterministic fake runner"

    def compile(self, source: str, config: RunnerConfig) -> CompileResult:
        self._delay()
        self.calls.append({"operation": "compile", "source_hash": hash(source), "config": config})
        return self.compile_result

    def run(
        self,
        source: str,
        stdin: str,
        config: RunnerConfig,
        extra_compile_flags: tuple[str, ...] = (),
    ) -> ExecutionResult:
        self._delay()
        self.calls.append(
            {
                "operation": "run",
                "source_hash": hash(source),
                "stdin": stdin,
                "flags": extra_compile_flags,
            }
        )
        return self.executions.get(stdin, self.default_execution)


def build_runner(
    settings: Settings,
) -> BubblewrapSandboxRunner | DockerSandboxRunner | FakeSandboxRunner:
    if settings.runner == "fake":
        return FakeSandboxRunner(delay_ms=settings.fake_delay_ms)
    if settings.runner == "bubblewrap":
        return BubblewrapSandboxRunner(settings)
    return DockerSandboxRunner(settings)
