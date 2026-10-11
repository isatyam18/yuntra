# Phase 1 architecture

The CLI calls `ProjectService`, which owns lifecycle enforcement, plan review, checkpoints, and Git observation. `Store` owns SQLite persistence and the JSONL event projection. Canonical project data is centralized in the user data directory; projects are referenced by absolute repository path. The package never makes commits or pushes.

SQLite tables contain profiles, append-only events, decisions, and verification records. Markdown remains the human-editable source for the project specification. Checkpoints are validated JSON documents written by temporary-file replacement.
