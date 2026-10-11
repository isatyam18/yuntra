from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .base import AdapterError, CodingAdapter
from ..models import LifecycleState
from ..service import ProjectService, git_status, redact


class CodexAdapter(CodingAdapter):
    """Integration limited to documented Codex CLI capabilities."""

    name = "codex"

    def detect_capabilities(self) -> dict[str, Any]:
        installed = shutil.which("codex")
        return {
            "name": self.name,
            "installed": bool(installed),
            "executable": installed,
            "supported": [
                "CLI health check",
                "project instruction export",
                "noninteractive task launch",
                "JSONL agent output capture",
            ],
            "unsupported": [
                "edit interception",
                "complete token accounting",
                "provider-internal checkpoint control",
            ],
        }

    def health_check(self) -> dict[str, Any]:
        executable = shutil.which("codex")
        if not executable:
            return {"healthy": False, "reason": "codex executable not found"}
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
        return f"""# Yuntra project handoff (canonical state)

Project: {profile.name} ({profile.project_id})
Lifecycle state: {profile.state}
Repository: {profile.repository_path}

Follow the approved specification below. Do not commit, push, publish, install dependencies, access credentials, or perform destructive operations unless the user explicitly authorizes it outside this handoff. Report decisions and verification commands; Yuntra will only treat direct repository and command evidence as verified.

## Approved project specification

{spec}
"""

    def run_task(self, project_data: Path, prompt: str) -> dict[str, Any]:
        executable = shutil.which("codex")
        if not executable:
            raise AdapterError(
                "Codex CLI is not installed; use the exported handoff manually."
            )
        service = ProjectService(project_data.parent.parent)
        store = service.store(project_data)
        profile = store.profile(service._project_id(project_data))
        if profile.state == LifecycleState.APPROVED:
            service.transition(
                project_data,
                LifecycleState.EXECUTING,
                "Codex task launch",
                actor="codex-adapter",
            )
            profile = store.profile(profile.project_id)
        if profile.state != LifecycleState.EXECUTING:
            raise AdapterError(
                f"Codex task launch requires APPROVED or EXECUTING state, got {profile.state}"
            )
        instructions = self.export_project_instructions(project_data)
        handoff = project_data / "codex-handoff.md"
        handoff.write_text(instructions, encoding="utf-8")
        before = git_status(Path(profile.repository_path))
        command = [
            executable,
            "exec",
            "-C",
            profile.repository_path,
            "-s",
            "workspace-write",
            "--json",
            f"Read {handoff}.\n\nUser task:\n{prompt}",
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        after = git_status(Path(profile.repository_path))
        output = redact((result.stdout + result.stderr)[-12000:])
        event = {
            "adapter": self.name,
            "exit_code": result.returncode,
            "observed_before": before,
            "observed_after": after,
            "adapter_report": output,
            "report_provenance": "adapter-reported",
            "repository_evidence": "direct-git-observation",
        }
        store.event(uuid.uuid4().hex, profile.project_id, "ADAPTER_RUN", event)
        if before != after:
            store.event(
                uuid.uuid4().hex,
                profile.project_id,
                "CHANGE_OBSERVED",
                {
                    "adapter": self.name,
                    "summary": "Repository state changed during Codex task",
                    "before": before,
                    "after": after,
                    "observed_directly": True,
                    "approval_state": profile.state,
                },
            )
        service.save_checkpoint(
            project_data,
            "Review Codex output and run the required verification commands.",
        )
        return event
