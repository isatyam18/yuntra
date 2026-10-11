"""Small, local safeguards for data that Yuntra persists or displays."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|token|password|secret|authorization)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s;,]+"
)


def redact_text(text: str) -> str:
    """Redact common inline credential assignments without changing unrelated content."""
    return _SENSITIVE_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


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
    return [match.group(1) for match in _SENSITIVE_PATTERN.finditer(text)]
