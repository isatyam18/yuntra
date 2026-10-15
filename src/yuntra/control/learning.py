from __future__ import annotations

import hashlib
import sqlite3
import uuid
from pathlib import Path

from ..models import LearningRecord, LearningScope, LearningStatus, utc_now
from ..security import redact_text


class LearningRegistry:
    """Central registry that admits reusable knowledge only through explicit gates."""

    def __init__(self, home: Path):
        self.path = home / "learning.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS lessons (lesson_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, body TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _fingerprint(description: str, scope: LearningScope, applicability: str) -> str:
        normalized = f"{' '.join(description.lower().split())}|{scope}|{' '.join(applicability.lower().split())}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def capture(
        self,
        project_id: str,
        description: str,
        evidence: list[str],
        scope: LearningScope,
        applicability: str,
        confidence: str,
        required_tools: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> LearningRecord:
        fingerprint = self._fingerprint(description, scope, applicability)
        with self._connect() as con:
            duplicate = con.execute(
                "SELECT body FROM lessons WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
        if duplicate:
            existing = LearningRecord.model_validate_json(duplicate["body"])
            raise ValueError(f"Duplicate candidate lesson: {existing.lesson_id}")
        lesson = LearningRecord(
            lesson_id=f"lesson-{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            description=redact_text(description),
            evidence=[redact_text(item) for item in evidence],
            scope=scope,
            applicability=redact_text(applicability),
            confidence=confidence,
            required_tools=required_tools or [],
            limitations=[redact_text(item) for item in (limitations or [])],
        )
        self._save(lesson, fingerprint)
        return lesson

    def _save(self, lesson: LearningRecord, fingerprint: str | None = None) -> None:
        fingerprint = fingerprint or self._fingerprint(
            lesson.description, lesson.scope, lesson.applicability
        )
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO lessons VALUES (?, ?, ?)",
                (lesson.lesson_id, fingerprint, lesson.model_dump_json()),
            )

    def get(self, lesson_id: str) -> LearningRecord:
        with self._connect() as con:
            row = con.execute(
                "SELECT body FROM lessons WHERE lesson_id=?", (lesson_id,)
            ).fetchone()
        if not row:
            raise KeyError(f"Unknown lesson: {lesson_id}")
        return LearningRecord.model_validate_json(row["body"])

    def list(
        self, project_id: str | None = None, promoted_only: bool = False
    ) -> list[LearningRecord]:
        with self._connect() as con:
            rows = con.execute("SELECT body FROM lessons").fetchall()
        lessons = [LearningRecord.model_validate_json(row["body"]) for row in rows]

        def visible(lesson: LearningRecord) -> bool:
            is_global_promoted = (
                lesson.scope == LearningScope.GLOBAL
                and lesson.status == LearningStatus.PROMOTED
            )
            matches_scope = (
                is_global_promoted
                if project_id is None
                else (lesson.project_id == project_id or is_global_promoted)
            )
            return matches_scope and (
                not promoted_only or lesson.status == LearningStatus.PROMOTED
            )

        return [lesson for lesson in lessons if visible(lesson)]

    def validate(self, lesson_id: str) -> LearningRecord:
        lesson = self.get(lesson_id)
        if lesson.status != LearningStatus.CAPTURED:
            raise ValueError("Only CAPTURED lessons can be validated.")
        if (
            not lesson.evidence
            or not lesson.applicability.strip()
            or not lesson.confidence.strip()
        ):
            raise ValueError(
                "Evidence, applicability, and confidence are required for validation."
            )
        lesson.status = LearningStatus.VALIDATED
        self._save(lesson)
        return lesson

    def review(self, lesson_id: str) -> LearningRecord:
        lesson = self.get(lesson_id)
        if lesson.status != LearningStatus.VALIDATED:
            raise ValueError("Only VALIDATED lessons can enter review.")
        lesson.status = LearningStatus.REVIEW
        lesson.reviewed_at = utc_now()
        self._save(lesson)
        return lesson

    def promote(self, lesson_id: str) -> LearningRecord:
        lesson = self.get(lesson_id)
        if lesson.status != LearningStatus.REVIEW:
            raise ValueError("Only REVIEW lessons can be promoted.")
        lesson.status = LearningStatus.PROMOTED
        lesson.promoted_at = utc_now()
        lesson.promotion_version = (lesson.promotion_version or 0) + 1
        self._save(lesson)
        return lesson

    def evaluate(self, lesson_id: str, outcome: str) -> LearningRecord:
        lesson = self.get(lesson_id)
        if lesson.status != LearningStatus.PROMOTED:
            raise ValueError("Only PROMOTED lessons can be evaluated.")
        lesson.evaluation = outcome
        self._save(lesson)
        return lesson
