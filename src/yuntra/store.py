from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import ProjectProfile, utc_now
from .security import redact_payload


class Store:
    SCHEMA_VERSION = 1

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = data_dir / "state.sqlite"
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self._connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS profiles (project_id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, created_at TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS verification (verification_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, created_at TEXT NOT NULL, body TEXT NOT NULL);
            """)
            row = con.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO schema_meta VALUES (?)", (self.SCHEMA_VERSION,)
                )
            elif row["version"] > self.SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema {row['version']} is newer than this Yuntra version."
                )
            elif row["version"] < self.SCHEMA_VERSION:
                self._migrate(con, row["version"])

    def _migrate(self, con: sqlite3.Connection, version: int) -> None:
        """Apply only additive, transactionally recorded migrations."""
        # Version 1 establishes schema_meta. Future migrations must preserve event history.
        con.execute("UPDATE schema_meta SET version=?", (self.SCHEMA_VERSION,))

    def schema_version(self) -> int:
        with self._connect() as con:
            return con.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()[
                "version"
            ]

    def save_profile(self, profile: ProjectProfile) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO profiles VALUES (?, ?)",
                (profile.project_id, profile.model_dump_json()),
            )

    def profile(self, project_id: str) -> ProjectProfile:
        with self._connect() as con:
            row = con.execute(
                "SELECT body FROM profiles WHERE project_id=?", (project_id,)
            ).fetchone()
        if not row:
            raise KeyError(f"Unknown project: {project_id}")
        return ProjectProfile.model_validate_json(row["body"])

    def event(
        self, event_id: str, project_id: str, kind: str, body: dict[str, Any]
    ) -> None:
        record = redact_payload(
            {
                "event_id": event_id,
                "project_id": project_id,
                "kind": kind,
                "timestamp": utc_now(),
                **body,
            }
        )
        with self._connect() as con:
            con.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                (event_id, project_id, kind, record["timestamp"], json.dumps(record)),
            )
        with (self.data_dir / "events.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps(record) + "\n")
        with (self.data_dir / "CHANGELOG.md").open("a", encoding="utf-8") as changelog:
            changelog.write(f"- {record['timestamp']} — {kind} ({event_id})\n")

    def events(self, project_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        query = (
            "SELECT body FROM events WHERE project_id=?"
            + (" AND kind=?" if kind else "")
            + " ORDER BY created_at"
        )
        args = (project_id, kind) if kind else (project_id,)
        with self._connect() as con:
            return [json.loads(row["body"]) for row in con.execute(query, args)]

    def decision(self, body: dict[str, Any]) -> None:
        body = redact_payload(body)
        with self._connect() as con:
            con.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?)",
                (
                    body["decision_id"],
                    body["project_id"],
                    body["created_at"],
                    json.dumps(body),
                ),
            )

    def decisions(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            return [
                json.loads(row["body"])
                for row in con.execute(
                    "SELECT body FROM decisions WHERE project_id=? ORDER BY created_at",
                    (project_id,),
                )
            ]
