from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_report_artifacts(
    root: Path, run_id: str, report: dict[str, Any], text: str
) -> tuple[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "report.json"
    text_path = run_dir / "report.txt"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")
    return str(json_path), str(text_path)
