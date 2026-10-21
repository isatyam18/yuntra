from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from .base import BaseCliAdapter

if TYPE_CHECKING:
    from ..models import ProjectProfile

__all__ = ["CodexAdapter", "shutil", "subprocess"]


class CodexAdapter(BaseCliAdapter):
    """Integration limited to documented Codex CLI capabilities."""

    name = "codex"
    executable_name = "codex"
    display_name = "Codex"
    supported_features: ClassVar[list[str]] = [
        "CLI health check",
        "project instruction export",
        "noninteractive task launch",
        "JSONL agent output capture",
    ]
    unsupported_features: ClassVar[list[str]] = [
        "edit interception",
        "complete token accounting",
        "provider-internal checkpoint control",
    ]

    def _build_command(
        self,
        executable: str,
        repo_path: str,
        handoff: Path,
        prompt: str,
        profile: ProjectProfile | None = None,
    ) -> tuple[list[str], str | None]:
        return (
            [
                executable,
                "exec",
                "-C",
                repo_path,
                "-s",
                "workspace-write",
                "--json",
                f"Read {handoff}.\n\nUser task:\n{prompt}",
            ],
            None,
        )
