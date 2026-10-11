from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..service import ProjectService
from .base import AdapterError, CodingAdapter


class ManualCliAdapter(CodingAdapter):
    """A provider-specific safe fallback when no verified automation is present."""

    executable_name: str
    display_name: str

    def detect_capabilities(self) -> dict[str, Any]:
        executable = shutil.which(self.executable_name)
        supported = ["canonical instruction export", "manual handoff"]
        unsupported = [
            "automated task launch",
            "edit interception",
            "token accounting",
            "provider checkpoint control",
        ]
        if executable:
            supported.append("CLI availability detection")
        return {
            "name": self.name,
            "installed": bool(executable),
            "executable": executable,
            "supported": supported,
            "unsupported": unsupported,
            "fallback": "Copy the generated handoff into a manually started provider session.",
        }

    def health_check(self) -> dict[str, Any]:
        executable = shutil.which(self.executable_name)
        if not executable:
            return {
                "healthy": False,
                "reason": f"{self.display_name} executable not found; manual handoff is available.",
            }
        result = subprocess.run(
            [executable, "--version"], text=True, capture_output=True, check=False
        )
        return {
            "healthy": result.returncode == 0,
            "version": result.stdout.strip(),
            "error": result.stderr.strip(),
        }

    def export_project_instructions(self, project_data: Path) -> str:
        service = ProjectService(project_data.parent.parent)
        store = service.store(project_data)
        profile = store.profile(service._project_id(project_data))
        spec = (project_data / "PROJECT_SPEC.md").read_text(encoding="utf-8")
        return f"""# Yuntra manual {self.display_name} handoff

Project: {profile.name} ({profile.project_id})
Lifecycle state: {profile.state}
Repository: {profile.repository_path}

This is a manual handoff, not evidence that {self.display_name} is installed or connected. Follow the approved specification. Do not commit, push, publish, install dependencies, access credentials, or perform destructive operations without explicit user authorization. Report decisions and verification commands for Yuntra to record. Only direct repository and command evidence is verified.

## Approved project specification

{spec}
"""

    def run_task(self, project_data: Path, prompt: str) -> dict[str, Any]:
        raise AdapterError(
            f"{self.display_name} automation is not verified. Export instructions and start a manual session instead."
        )

    def report_limitations(self) -> list[str]:
        return [
            f"No documented {self.display_name} automation has been verified for this installation.",
            "The adapter does not launch a provider session, intercept edits, or collect token usage.",
            "Use the generated manual handoff and record direct Git/verification evidence in Yuntra.",
        ]
