from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    os.environ.setdefault("AUTOGRADER_RUNNER", "fake")
    command = [
        sys.executable,
        "-m",
        "app.cli",
        "--assignment",
        "../examples/add_two_integers/assignment.json",
        "--submission",
        "../examples/add_two_integers/correct.c",
        "--submission",
        "../examples/add_two_integers/buggy.c",
    ]
    return subprocess.call(command, cwd="backend")


if __name__ == "__main__":
    raise SystemExit(main())
