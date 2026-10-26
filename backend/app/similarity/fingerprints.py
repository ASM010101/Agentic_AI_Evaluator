from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


TOKEN_RE = re.compile(
    r"//[^\n]*|/\*.*?\*/|"  # comments
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|"  # strings/chars
    r"[A-Za-z_]\w*|"  # identifiers
    r"\d+(?:\.\d+)?|"  # numeric literals
    r"==|!=|<=|>=|&&|\|\||\+\+|--|->|[{}()\[\];,.:?~!%^&*+\-/<>|=]",
    re.DOTALL,
)
KEYWORDS = {
    "auto",
    "break",
    "case",
    "char",
    "const",
    "continue",
    "default",
    "do",
    "double",
    "else",
    "enum",
    "extern",
    "float",
    "for",
    "goto",
    "if",
    "inline",
    "int",
    "long",
    "register",
    "restrict",
    "return",
    "short",
    "signed",
    "sizeof",
    "static",
    "struct",
    "switch",
    "typedef",
    "union",
    "unsigned",
    "void",
    "volatile",
    "while",
}


@dataclass(frozen=True)
class SimilarityResult:
    score: float
    method: str
    shared_tokens: int
    left_excerpt: str
    right_excerpt: str
    caveats: list[str]


def normalize_tokens(source: str) -> list[str]:
    tokens = TOKEN_RE.findall(source)
    normalized: list[str] = []
    for token in tokens:
        if token.startswith("//") or token.startswith("/*"):
            continue
        if (
            token in KEYWORDS
            or re.fullmatch(r"\d+(?:\.\d+)?", token)
            or token.startswith(('"', "'"))
        ):
            normalized.append(token)
        elif re.fullmatch(r"[A-Za-z_]\w*", token):
            normalized.append("IDENT")
        else:
            normalized.append(token)
    return normalized


def _excerpt(tokens: list[str], start: int, size: int = 12) -> str:
    return " ".join(tokens[max(0, start - 2) : start + size])


def compare_sources(left: str, right: str) -> SimilarityResult:
    left_tokens = normalize_tokens(left)
    right_tokens = normalize_tokens(right)
    if not left_tokens or not right_tokens:
        return SimilarityResult(
            0.0, "normalized_token_sequence_v1", 0, "", "", ["one source has no code tokens"]
        )
    matcher = difflib.SequenceMatcher(a=left_tokens, b=right_tokens, autojunk=False)
    matches = matcher.get_matching_blocks()
    shared = sum(block.size for block in matches)
    denominator = max(len(left_tokens), len(right_tokens))
    score = round(shared / denominator, 6)
    largest = max(matches, key=lambda block: block.size, default=None)
    if largest and largest.size:
        left_excerpt = _excerpt(left_tokens, largest.a, min(24, largest.size))
        right_excerpt = _excerpt(right_tokens, largest.b, min(24, largest.size))
    else:
        left_excerpt = right_excerpt = ""
    caveats = [
        "Similarity is assignment-scoped evidence for human review, not proof of misconduct.",
        "Small or highly constrained assignments can produce high common similarity.",
    ]
    return SimilarityResult(
        score=score,
        method="normalized_token_sequence_v1",
        shared_tokens=shared,
        left_excerpt=left_excerpt,
        right_excerpt=right_excerpt,
        caveats=caveats,
    )
