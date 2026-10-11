from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LifecycleState(StrEnum):
    NEW = "NEW"
    PLANNING = "PLANNING"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class VerificationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    NOT_RUN = "NOT_RUN"


class LearningScope(StrEnum):
    PROJECT = "PROJECT"
    TOOL = "TOOL"
    DOMAIN = "DOMAIN"
    GLOBAL = "GLOBAL"


class LearningStatus(StrEnum):
    CAPTURED = "CAPTURED"
    VALIDATED = "VALIDATED"
    REVIEW = "REVIEW"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class LearningRecord(BaseModel):
    lesson_id: str
    project_id: str
    description: str
    evidence: list[str] = Field(min_length=1)
    scope: LearningScope
    applicability: str
    confidence: str
    limitations: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    status: LearningStatus = LearningStatus.CAPTURED
    promotion_version: int | None = None
    created_at: str = Field(default_factory=utc_now)
    reviewed_at: str | None = None
    promoted_at: str | None = None
    evaluation: str | None = None


class ProjectProfile(BaseModel):
    project_id: str
    name: str
    repository_path: str
    data_path: str
    state: LifecycleState = LifecycleState.NEW
    allowed_adapters: list[str] = Field(default_factory=lambda: ["codex"])
    context_exclusions: list[str] = Field(
        default_factory=lambda: [".git", ".env", "node_modules", ".venv"]
    )
    verification_commands: list[str] = Field(default_factory=list)
    context_budgets: dict[str, int] = Field(
        default_factory=lambda: {
            "project_instructions": 3500,
            "working_state": 1000,
            "documentation": 3000,
            "code_and_tests": 5000,
            "historical_decisions": 1500,
        }
    )
    policies: dict[str, bool] = Field(
        default_factory=lambda: {
            "allow_auto_commit": False,
            "allow_git_push": False,
            "allow_dependency_install": False,
            "allow_network": False,
            "allow_destructive_operations": False,
        }
    )
    created_at: str = Field(default_factory=utc_now)


class DecisionRecord(BaseModel):
    decision_id: str
    project_id: str
    task_id: str | None = None
    status: str = "PROPOSED"
    problem: str
    requirements: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    chosen_approach: str
    rationale: str
    tradeoffs: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    rollback_plan: str = "Not supplied"
    created_at: str = Field(default_factory=utc_now)


class Checkpoint(BaseModel):
    schema_version: int = 1
    project_id: str
    lifecycle_state: LifecycleState
    active_task: str | None = None
    completed_work: list[str] = Field(default_factory=list)
    incomplete_work: list[str] = Field(default_factory=list)
    pending_tests: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_action: str
    git_status: str
    created_at: str = Field(default_factory=utc_now)
