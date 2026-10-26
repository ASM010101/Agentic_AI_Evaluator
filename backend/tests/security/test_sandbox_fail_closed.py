from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.core.config import Settings
from app.sandbox.runner import BubblewrapSandboxRunner, DockerSandboxRunner, RunnerConfig


def test_docker_runner_never_falls_back_to_host_execution_when_docker_missing():
    settings = Settings(runner="docker", docker_image="definitely-not-present:latest")
    runner = DockerSandboxRunner(settings)
    result = runner.compile("int main(void){return 0;}", RunnerConfig(1, 64, 1000))
    if result.unavailable:
        assert result.compiled is False
        assert result.error


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap is not installed")
def test_bubblewrap_runner_compiles_runs_and_hides_host_project():
    settings = Settings(runner="bubblewrap", bubblewrap_path="bwrap")
    runner = BubblewrapSandboxRunner(settings)
    config = RunnerConfig(time_limit_s=1, memory_limit_mb=128, output_limit_bytes=10_000)
    source = '#include <stdio.h>\nint main(void){puts("sandbox-ok");return 0;}\n'
    compiled = runner.compile(source, config)
    assert compiled.compiled is True
    executed = runner.run(source, "", config)
    assert executed.stdout == "sandbox-ok\n"

    project_path = str(Path.cwd().parent / "README.md").replace("\\", "/")
    host_probe = (
        "#include <stdio.h>\n"
        f'int main(void){{FILE *f=fopen("{project_path}","r");'
        'puts(f ? "host-visible" : "host-blocked"); return f != NULL;}\n'
    )
    blocked = runner.run(host_probe, "", config)
    assert blocked.stdout == "host-blocked\n"


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap is not installed")
def test_bubblewrap_runner_reports_cpu_limit_as_timeout():
    runner = BubblewrapSandboxRunner(Settings(runner="bubblewrap", bubblewrap_path="bwrap"))
    result = runner.run(
        "int main(void){for(;;){} return 0;}\n",
        "",
        RunnerConfig(time_limit_s=1, memory_limit_mb=128, output_limit_bytes=10_000),
    )
    assert result.timed_out is True


@pytest.mark.skipif(
    shutil.which("bwrap") is None or shutil.which("cppcheck") is None,
    reason="bubblewrap and cppcheck are required",
)
def test_bubblewrap_runs_codacy_aligned_local_cppcheck_inside_the_sandbox():
    runner = BubblewrapSandboxRunner(Settings(runner="bubblewrap", bubblewrap_path="bwrap"))
    result = runner.analyze_tool(
        "#include <stdio.h>\nint main(void){char value[4]; gets(value);}\n",
        "cppcheck",
        ("--enable=warning,style,performance,portability", "--template=gcc", "--quiet"),
        output_limit=10_000,
    )
    assert result.available is True
    assert "gets" in (result.stdout + result.stderr)
