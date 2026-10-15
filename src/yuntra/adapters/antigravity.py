from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

from .base import BaseCliAdapter

__all__ = ["AntigravityAdapter", "shutil", "subprocess"]


class AntigravityAdapter(BaseCliAdapter):
    """Integration limited to documented Google Antigravity CLI capabilities."""

    name = "antigravity"
    executable_name = "agy"
    display_name = "Antigravity"
    cli_name = "Google Antigravity"
    supported_features: ClassVar[list[str]] = [
        "CLI health check",
        "project instruction export",
        "noninteractive task launch",
        "plain-text agent output capture",
    ]
    unsupported_features: ClassVar[list[str]] = [
        "edit interception",
        "complete token accounting",
        "provider-internal checkpoint control",
        "structured JSON output",
    ]

    def _build_command(
        self, executable: str, repo_path: str, handoff: Path, prompt: str
    ) -> tuple[list[str], str | None]:
        return (
            [
                executable,
                "--dangerously-skip-permissions",
                f"Read {handoff}.\n\nUser task:\n{prompt}",
            ],
            repo_path,
        )
