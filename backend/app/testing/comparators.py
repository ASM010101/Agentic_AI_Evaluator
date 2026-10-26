from __future__ import annotations

from dataclasses import dataclass


class ComparatorError(ValueError):
    pass


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def normalize_output(value: str, mode: str) -> str:
    value = normalize_newlines(value)
    if mode == "exact":
        return value
    if mode == "trim_trailing_whitespace":
        return "\n".join(line.rstrip() for line in value.split("\n")).rstrip("\n")
    if mode == "whitespace":
        return " ".join(value.split())
    raise ComparatorError(f"unsupported comparison mode: {mode}")


def compare_output(expected: str, actual: str, mode: str = "trim_trailing_whitespace") -> bool:
    return normalize_output(expected, mode) == normalize_output(actual, mode)


@dataclass(frozen=True)
class ComparisonResult:
    passed: bool
    expected: str
    actual: str
    mode: str
    reason: str


def compare(expected: str, actual: str, mode: str = "trim_trailing_whitespace") -> ComparisonResult:
    passed = compare_output(expected, actual, mode)
    return ComparisonResult(
        passed=passed,
        expected=expected,
        actual=actual,
        mode=mode,
        reason="outputs match under the configured comparator" if passed else "outputs differ",
    )
