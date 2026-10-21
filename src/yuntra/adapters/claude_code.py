from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from .base import BaseCliAdapter

if TYPE_CHECKING:
    from ..models import ProjectProfile

__all__ = ["ClaudeCodeAdapter", "shutil", "subprocess"]


class ClaudeCodeAdapter(BaseCliAdapter):
    """Integration limited to documented Claude Code CLI capabilities."""

    name = "claude-code"
    executable_name = "claude"
    display_name = "Claude Code"
    supported_features: ClassVar[list[str]] = [
        "CLI health check",
        "project instruction export",
        "noninteractive task launch",
        "JSON agent output capture",
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
        tools = ["Read", "Edit"]
        if profile and (
            profile.policies.get("allow_destructive_operations", False)
            or profile.policies.get("allow_dependency_install", False)
        ):
            tools.append("Bash")

        return (
            [
                executable,
                "-p",
                f"Read {handoff}.\n\nUser task:\n{prompt}",
                "--output-format",
                "json",
                "--allowedTools",
                ",".join(tools),
            ],
            repo_path,
        )
