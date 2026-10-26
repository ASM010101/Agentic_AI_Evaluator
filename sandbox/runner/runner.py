#!/usr/bin/env python3
"""Fixed, trusted container-side runner for AutoGrader.

The API never sends a shell command. It sends this runner a JSON payload with
source text and bounded data. The runner compiles with GCC and executes only
the resulting binary under resource limits.
"""

from __future__ import annotations

import json
import os
import resource
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def bounded(value: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(value) > limit
    return value[:limit].decode("utf-8", errors="replace"), truncated


def limits(payload: dict) -> None:
    memory = int(payload.get("memory_limit_mb", 128)) * 1024 * 1024
    output = int(payload.get("output_limit_bytes", 100_000))
    cpu = max(1, int(float(payload.get("time_limit_s", 2))))
    if payload.get("mode") == "compile":
        memory = max(memory, 256 * 1024 * 1024)
        cpu = max(cpu, 5)
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_FSIZE, (output, output))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))


def main() -> int:
    payload = json.load(sys.stdin)
    source = payload.get("source", "")
    limit = int(payload.get("output_limit_bytes", 100_000))
    compile_flags = [str(flag) for flag in payload.get("compile_flags", ["-std=c11", "-O2"])]
    with tempfile.TemporaryDirectory(prefix="autograder-") as directory:
        root = Path(directory)
        source_path = root / "student.c"
        binary_path = root / "student"
        source_path.write_text(source, encoding="utf-8")
        compile_command = ["gcc", *compile_flags, str(source_path), "-o", str(binary_path)]
        started = time.perf_counter()
        try:
            compiled = subprocess.run(
                compile_command,
                capture_output=True,
                timeout=max(1.0, float(payload.get("time_limit_s", 2))),
                check=False,
                preexec_fn=lambda: limits(payload),
            )
        except subprocess.TimeoutExpired as exc:
            stdout, _ = bounded(exc.stdout or b"", limit)
            stderr, _ = bounded(exc.stderr or b"", limit)
            print(json.dumps({"compiled": False, "exit_code": None, "stdout": stdout, "stderr": stderr, "error": "compile timeout"}))
            return 0
        stdout, _ = bounded(compiled.stdout, limit)
        stderr, _ = bounded(compiled.stderr, limit)
        if payload.get("mode") == "compile" or compiled.returncode != 0:
            print(json.dumps({"compiled": compiled.returncode == 0, "exit_code": compiled.returncode, "stdout": stdout, "stderr": stderr}))
            return 0
        if payload.get("mode") != "run":
            print(json.dumps({"compiled": True, "exit_code": 0, "stdout": stdout, "stderr": stderr}))
            return 0

        run_started = time.perf_counter()
        try:
            process = subprocess.run(
                [str(binary_path)],
                input=str(payload.get("stdin", "")).encode("utf-8"),
                capture_output=True,
                timeout=max(0.1, float(payload.get("time_limit_s", 2))),
                check=False,
                preexec_fn=lambda: limits(payload),
            )
            run_stdout, run_stdout_truncated = bounded(process.stdout, limit)
            run_stderr, run_stderr_truncated = bounded(process.stderr, limit)
            signal_number = -process.returncode if process.returncode < 0 else None
            print(
                json.dumps(
                    {
                        "ran": True,
                        "exit_code": process.returncode,
                        "stdout": run_stdout,
                        "stderr": run_stderr,
                        "duration_ms": (time.perf_counter() - run_started) * 1000,
                        "signal": signal_number,
                        "output_truncated": run_stdout_truncated or run_stderr_truncated,
                    }
                )
            )
        except subprocess.TimeoutExpired as exc:
            run_stdout, _ = bounded(exc.stdout or b"", limit)
            run_stderr, _ = bounded(exc.stderr or b"", limit)
            print(
                json.dumps(
                    {
                        "ran": False,
                        "exit_code": None,
                        "stdout": run_stdout,
                        "stderr": run_stderr,
                        "duration_ms": (time.perf_counter() - run_started) * 1000,
                        "timed_out": True,
                        "error": "execution timeout",
                    }
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
