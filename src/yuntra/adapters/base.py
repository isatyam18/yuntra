from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from ..models import LifecycleState, ProjectProfile
from ..service import (
    ProjectService,
    check_spec_drift,
    get_approved_spec,
    git_status,
    redact,
)


class AdapterError(RuntimeError):
    """Raised when an adapter cannot safely complete an operation."""


class CodingAdapter(ABC):
    """Stable boundary between Yuntra's canonical state and a coding tool."""

    name: str

    @abstractmethod
    def detect_capabilities(self) -> dict[str, Any]: ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    def export_project_instructions(self, project_data: Path) -> str: ...

    @abstractmethod
    def run_task(self, project_data: Path, prompt: str) -> dict[str, Any]: ...

    def load_context(self, project_data: Path) -> str:
        return self.export_project_instructions(project_data)

    def save_checkpoint(self, project_data: Path) -> None:
        """Adapters may delegate checkpoint creation to the canonical control layer."""

    def record_decision(self, decision: dict[str, Any]) -> None:
        """Adapters must never fabricate a decision record."""

    def record_change(self, change: dict[str, Any]) -> None:
        """Adapters must label reported changes separately from direct observation."""

    def collect_usage_metrics(self) -> dict[str, Any]:
        return {"available": False, "reason": "provider metrics unavailable"}

    def run_verification(self, project_data: Path, command: str) -> dict[str, Any]:
        raise AdapterError(
            "Verification is owned by Yuntra's canonical verification subsystem."
        )

    def report_limitations(self) -> list[str]:
        return [
            "This adapter cannot claim unobservable provider behavior as verified evidence."
        ]


class BaseCliAdapter(CodingAdapter):
    """Shared implementation for CLI coding tool adapters."""

    executable_name: str
    display_name: str
    cli_name: str | None = None
    supported_features: ClassVar[list[str]] = []
    unsupported_features: ClassVar[list[str]] = []

    def _which(self, name: str) -> str | None:
        mod = sys.modules.get(self.__module__)
        which_fn = getattr(getattr(mod, "shutil", None), "which", shutil.which)
        return which_fn(name)

    def _run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        mod = sys.modules.get(self.__module__)
        run_fn = getattr(getattr(mod, "subprocess", None), "run", subprocess.run)
        return run_fn(*args, **kwargs)

    def get_cli_name(self) -> str:
        return self.cli_name or self.display_name

    def detect_capabilities(self) -> dict[str, Any]:
        installed = self._which(self.executable_name)
        return {
            "name": self.name,
            "installed": bool(installed),
            "executable": installed,
            "supported": self.supported_features,
            "unsupported": self.unsupported_features,
        }

    def health_check(self) -> dict[str, Any]:
        executable = self._which(self.executable_name)
        if not executable:
            return {
                "healthy": False,
                "reason": f"{self.executable_name} executable not found",
            }
        result = self._run(
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
        spec = get_approved_spec(project_data)
        return f"""# Yuntra project handoff (canonical state)

Project: {profile.name} ({profile.project_id})
Lifecycle state: {profile.state}
Repository: {profile.repository_path}

Follow the approved specification below. Do not commit, push, publish, install dependencies, access credentials, or perform destructive operations unless the user explicitly authorizes it outside this handoff.

## Architectural and Reason Requirements
For every step, file, or function you plan or implement:
1. State the explicit problem and rationale BEFORE implementing each step or function.
2. In all code you create or modify, include clean docstrings/comments stating the design purpose and rationale for the component/function.
3. If an architectural decision or tradeoff is made, format it clearly as:
   Decision: <short title>
   Problem: <problem being solved>
   Chosen: <chosen solution>
   Rationale: <why this approach was chosen>
   Tradeoffs: <known alternatives or tradeoffs>

Report decisions and verification commands; Yuntra will only treat direct repository and command evidence as verified.

## Approved project specification

{spec}
"""

    @abstractmethod
    def _build_command(
        self,
        executable: str,
        repo_path: str,
        handoff: Path,
        prompt: str,
        profile: ProjectProfile | None = None,
    ) -> tuple[list[str], str | None]: ...

    def run_task(self, project_data: Path, prompt: str) -> dict[str, Any]:
        executable = self._which(self.executable_name)
        if not executable:
            raise AdapterError(
                f"{self.get_cli_name()} CLI is not installed; use the exported handoff manually."
            )
        service = ProjectService(project_data.parent.parent)
        store = service.store(project_data)
        profile = store.profile(service._project_id(project_data))

        # Check spec drift before launching task
        has_drifted, approved_h, live_h = check_spec_drift(project_data)
        if has_drifted:
            service.transition(
                project_data,
                LifecycleState.REVIEW,
                "Specification drift detected: live specification was modified after approval",
                actor="yuntra-integrity",
            )
            store.event(
                uuid.uuid4().hex,
                profile.project_id,
                "SPEC_DRIFT_DETECTED",
                {
                    "approved_hash": approved_h,
                    "live_hash": live_h,
                    "action": "reverted_to_review",
                },
            )
            raise AdapterError(
                "Specification has been modified after approval. Review and approve the updated specification before launching tasks."
            )

        if profile.state == LifecycleState.APPROVED:
            service.transition(
                project_data,
                LifecycleState.EXECUTING,
                f"{self.display_name} task launch",
                actor=f"{self.name}-adapter",
            )
            profile = store.profile(profile.project_id)
        if profile.state != LifecycleState.EXECUTING:
            raise AdapterError(
                f"{self.display_name} task launch requires APPROVED or EXECUTING state, got {profile.state}"
            )
        instructions = self.export_project_instructions(project_data)
        handoff = project_data / f"{self.name}-handoff.md"
        handoff.write_text(instructions, encoding="utf-8")
        before = git_status(Path(profile.repository_path))
        command, cwd = self._build_command(
            executable, profile.repository_path, handoff, prompt, profile
        )
        result = self._run(
            command,
            text=True,
            capture_output=True,
            check=False,
            **({"cwd": cwd} if cwd else {}),
        )
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
            ai_rationale = self._extract_ai_rationale(output)
            reason_msg = f"Task: {prompt}" + (
                f" ({ai_rationale})" if ai_rationale else ""
            )
            store.event(
                uuid.uuid4().hex,
                profile.project_id,
                "CHANGE_OBSERVED",
                {
                    "adapter": self.name,
                    "task_prompt": prompt,
                    "reason": reason_msg,
                    "ai_rationale": ai_rationale,
                    "summary": f"Repository state changed during {self.display_name} task",
                    "before": before,
                    "after": after,
                    "observed_directly": True,
                    "approval_state": profile.state,
                },
            )
        service.save_checkpoint(
            project_data,
            f"Review {self.display_name} output and run the required verification commands.",
            reason=f"{self.display_name}: {prompt}",
        )
        return event

    @staticmethod
    def _extract_ai_rationale(output: str) -> str | None:
        if not output:
            return None
        try:
            data = json.loads(output.strip())
            if isinstance(data, dict):
                for key in (
                    "summary",
                    "reason",
                    "message",
                    "explanation",
                    "result",
                    "rationale",
                ):
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        for line in lines:
            match = re.match(
                r"(?i)^(?:reason|summary|rationale|explanation|decision)\s*[:=-]\s*(.+)",
                line,
            )
            if match:
                extracted = match.group(1).strip()
                if extracted and len(extracted) > 3:
                    return extracted

        embedded_match = re.search(
            r"(?i)(?:rationale|reason|decision|summary)\s*[:=-]\s*([^\n\r]+)",
            output,
        )
        if embedded_match:
            candidate = embedded_match.group(1).strip()
            if candidate and len(candidate) > 3:
                return candidate

        return lines[-1][:200] if lines else None
