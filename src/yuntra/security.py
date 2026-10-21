"""Safeguards for credential redaction and sensitive data detection."""

from __future__ import annotations

import re
from typing import Any

# Standalone high-entropy token shapes
_TOKEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9_-]+ )?PRIVATE KEY-----"
        ),
    ),
    (
        "github_token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
    ),
    (
        "github_pat",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b"),
    ),
    (
        "aws_access_key",
        re.compile(r"\b(?:AKIA|ASIA|AROA)[0-9A-Z]{16}\b"),
    ),
    (
        "api_key",
        re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\b"
        ),
    ),
]

# Key-value credential assignments with quotes (single or double, handles spaces within quotes)
_QUOTED_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|password|passwd|secret(?:[_-]?key)?|client[_-]?secret|authorization)"
    r"\s*[:=]\s*(?:bearer\s+)?([\"'])(?:\\.|[^\\])*?\2"
)

# Authorization header or standalone Bearer token
_BEARER_TOKEN = re.compile(
    r"(?i)(?:\bauthorization\s*:\s*)?\bbearer\s+[^\s;,]+"
)

# Unquoted assignment with '=' (e.g. token=abc, password=xyz, secret=foo)
_EQUALS_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|password|passwd|secret(?:[_-]?key)?|client[_-]?secret)\s*=\s*(?:bearer\s+)?[^\s;,]+"
)

# Explicit colon assignment with unquoted token (e.g. password: xyz, api_key: xyz)
_COLON_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|client[_-]?secret)\s*:\s*(?:bearer\s+)?([A-Za-z0-9_!@#$%^&*.\-+=/]{2,})"
)


def _redact_bearer(m: re.Match[str]) -> str:
    matched = m.group(0)
    if re.match(r"(?i)\bauthorization\s*:", matched):
        return "Authorization=[REDACTED]"
    return "Bearer [REDACTED]"


def redact_text(text: str) -> str:
    """Redact credentials and tokens without changing unrelated content."""
    if not text:
        return text

    result = text

    # 1. Standalone raw tokens & PEM blocks
    for label, pat in _TOKEN_PATTERNS:
        result = pat.sub(f"[{label.upper()}_REDACTED]", result)

    # 2. Quoted credential assignments (e.g. password: "hunter two")
    result = _QUOTED_ASSIGNMENT.sub(lambda m: f"{m.group(1)}=[REDACTED]", result)

    # 3. Authorization Bearer or standalone Bearer token
    result = _BEARER_TOKEN.sub(_redact_bearer, result)

    # 4. Explicit unquoted credential assignments
    result = _EQUALS_ASSIGNMENT.sub(lambda m: f"{m.group(1)}=[REDACTED]", result)
    result = _COLON_ASSIGNMENT.sub(lambda m: f"{m.group(1)}=[REDACTED]", result)

    return result


def redact_payload(value: Any) -> Any:
    """Recursively redact strings before serializing event or metadata payloads."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_payload(item) for key, item in value.items()}
    return value


def sensitive_markers(text: str) -> list[str]:
    """Return field labels that indicate a specification may contain a credential."""
    markers: list[str] = []
    for label, pat in _TOKEN_PATTERNS:
        if pat.search(text):
            markers.append(label)

    for m in _QUOTED_ASSIGNMENT.finditer(text):
        markers.append(m.group(1).lower())

    for m in _BEARER_TOKEN.finditer(text):
        markers.append("authorization")

    for m in _EQUALS_ASSIGNMENT.finditer(text):
        markers.append(m.group(1).lower())

    for m in _COLON_ASSIGNMENT.finditer(text):
        markers.append(m.group(1).lower())

    return markers
