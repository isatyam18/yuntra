# Yuntra architecture and subsystems

Yuntra is a local-first, provider-neutral AI development framework for Windows and PowerShell. It runs without external LLM APIs, Docker, Redis, vector databases, or background daemons. Canonical state is centralized in the local data directory and referenced by absolute repository path.

## Core architecture and lifecycle

The CLI interacts with `ProjectService`, which coordinates lifecycle enforcement, plan review, recovery checkpoints, and Git observation.

- **Storage**: `Store` manages local SQLite persistence (`state.sqlite` with WAL mode) for profiles, events, decisions, and verification records, alongside an append-only `events.jsonl` log and `CHANGELOG.md`.
- **Specification**: `PROJECT_SPEC.md` serves as the human-editable source of truth. Plan approval requires explicit human review and rejects unverified AI proposals or credential markers.
- **Safety**: Yuntra defaults to denying automatic commits, Git pushes, dependency installation, network requests, and destructive operations.

## Context optimization and retrieval

Context retrieval operates deterministically without embeddings or remote services:

- **Filtering & exclusions**: Respects configured project exclusions (`.git`, `.venv`, `node_modules`), secret filenames (`.env`, `id_rsa`), and file extension filters.
- **Sectioning & ranking**: Splits Markdown documents into heading sections, ranks candidate files and sections using deterministic keyword matching against task objectives, and deduplicates exact-content matches using SHA-256 digests.
- **Budgets & manifests**: Enforces independent category token budgets (project instructions, working state, documentation, code/tests, decision history). Every retrieval produces an audited manifest detailing selected items, token estimates (`ceil(characters / 4)`), and omitted material.

## Controlled learning registry

The learning subsystem (`LearningRegistry`) captures reusable engineering insights without modifying framework source code, policies, or schemas:

- **Evidence-backed capture**: Lessons require verifiable evidence, originating project context, scope (`PROJECT`, `TOOL`, `DOMAIN`, `GLOBAL`), applicability criteria, and confidence ratings. Duplicate candidates are rejected by content fingerprinting.
- **Explicit promotion gates**: Lessons move strictly through staged gates: `CAPTURED` → `VALIDATED` → `REVIEW` → `PROMOTED`. Promotion always requires explicit human confirmation.
- **Project isolation**: Project-scoped lessons remain private to their originating repository. Global queries return only promoted global lessons.

## Recovery, migrations, and security

- **Checkpoints**: Written via sibling temporary files followed by atomic replacement. Resuming validates `.json` checkpoints and compares direct Git status against recorded evidence, never discarding uncommitted work.
- **Schema versioning**: SQLite database schema version is tracked in `schema_meta`. Only additive migrations are supported; newer database schemas are safely rejected.
- **Backup & restore**: Backups are standard zip archives of centralized project data. Restores enforce empty destination directories and validate member paths to prevent path traversal attacks.
