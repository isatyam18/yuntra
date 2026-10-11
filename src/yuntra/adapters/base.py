from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


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
