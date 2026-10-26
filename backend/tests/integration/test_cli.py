from __future__ import annotations

import json
import sys

from app.cli import main


def test_cli_runs_a_local_deterministic_fixture(tmp_path, monkeypatch, capsys):
    assignment = tmp_path / "assignment.json"
    source = tmp_path / "program.c"
    assignment.write_text(
        json.dumps(
            {
                "name": "CLI fixture",
                "problem_statement": "Produce no output.",
                "rules": {
                    "metrics": [
                        {
                            "name": "correctness",
                            "analyzer": "io_tests",
                            "weight": 1.0,
                            "scoring": {"mode": "test_ratio"},
                        }
                    ],
                    "tests": [
                        {
                            "id": "empty",
                            "input": "",
                            "expected_output": "",
                            "rationale": "fixture",
                            "provenance": "explicit_rule",
                            "status": "validated",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    source.write_text("int main(void) { return 0; }", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autograder",
            "--assignment",
            str(assignment),
            "--submission",
            str(source),
        ],
    )
    assert main() == 0
    assert "batch=" in capsys.readouterr().out
