# yuntra

**Remember. Plan. Execute. Learn.**

yuntra is a local-first, provider-neutral framework for AI-assisted software development. It keeps a user-approved plan, structured project memory, decisions, verification evidence, recovery checkpoints, and tool handoffs in centralized local storage—without automatically committing, pushing, publishing, or discarding repository work.

## What exists now

yuntra is an installable Python CLI for Windows and PowerShell. It runs without an external LLM API, Docker, Redis, a vector database, or a background service.

| Phase | Delivered capability | Current status |
| --- | --- | --- |
| 0 | Repository/environment discovery and architecture plan | Complete |
| 1 | Core project profiles, manual specification, approvals, lifecycle, SQLite events, decisions, verification, checkpoints, and recovery | Complete |
| 2 | Codex CLI integration with canonical handoffs, direct Git evidence, and checkpoints | Complete |
| 3 | Claude Code and Google Antigravity CLI integration with canonical handoffs, direct Git evidence, and checkpoints | Complete |
| 4 | Deterministic context retrieval, exclusions, deduplication, budgets, manifests, and honest benchmarks | Complete |
| 5 | Evidence-backed, scoped learning capture and explicit promotion gates | Complete |
| 6 | Backup/restore safety, schema versioning, policy checks, recovery hardening, and security coverage | Complete |
| 7 | Dependency-free static project dashboard | Complete |
| 8 | Interactive architecture and sequence diagramming via Archify | Complete |

The complete local quality gate currently covers 32 automated tests, Ruff linting, Black formatting, Mypy type checks, compilation, and source/wheel builds.

yuntra is prepared for a public beta, running locally on Windows and Linux without cloud accounts or external dependencies.

## Installation on Windows / PowerShell

```powershell
cd C:\path\to\yuntra
py -m pip install -e .
yuntra init
```

yuntra stores canonical state centrally in `%LOCALAPPDATA%\yuntra` by default. To select another user-controlled location:

```powershell
$env:YUNTRA_HOME = "D:\yuntraData"
yuntra init
```

The framework references source repositories; it does not put yuntra state into them by default.

## Start-to-finish workflow

### 1. Register a repository and write the plan

```powershell
yuntra project create --name "Inventory API" --repository C:\src\inventory-api
yuntra plan edit inventory-api
```

Open the printed `PROJECT_SPEC.md` path and manually complete the required sections: problem, goal, architecture, interfaces, plan, requirements, constraints, acceptance criteria, risks, and exclusions. Do not put credentials in the specification—plan review rejects likely secrets.

### 2. Review and explicitly approve it

```powershell
yuntra plan review inventory-api
yuntra plan approve inventory-api --yes
yuntra status inventory-api
```

Implementation-oriented work is blocked until the plan is approved.

### 3. Work with a coding tool

Each adapter creates a handoff from canonical yuntra state, records bounded/redacted adapter output, compares Git state before and after, and saves a checkpoint. None of them commit or push. If the CLI is not installed, export the handoff with the `instructions` command and paste it into a manually started provider session.

Codex:

```powershell
yuntra adapter codex health
yuntra adapter codex instructions inventory-api --output C:\handoffs\inventory-codex.md
yuntra adapter codex run inventory-api --prompt "Implement the approved authentication milestone" --yes
```

Claude Code:

```powershell
yuntra adapter claude-code health
yuntra adapter claude-code instructions inventory-api --output C:\handoffs\inventory-claude.md
yuntra adapter claude-code run inventory-api --prompt "Implement the approved authentication milestone" --yes
```

Google Antigravity:

```powershell
yuntra adapter antigravity health
yuntra adapter antigravity instructions inventory-api --output C:\handoffs\inventory-antigravity.md
yuntra adapter antigravity run inventory-api --prompt "Implement the approved authentication milestone" --yes
```



### 4. Track decisions, verify, and recover

```powershell
yuntra decisions inventory-api --problem "Choose session storage" --chosen "SQLite" --rationale "Local-first deployment"
yuntra verify inventory-api --command "py -m pytest"
yuntra checkpoint save inventory-api --next-action "Review verification evidence"
yuntra resume inventory-api
yuntra log inventory-api
```

`verify --command` intentionally executes a command explicitly supplied by the local user after plan approval. Do not provide untrusted text to this option.

## Context management

```powershell
yuntra context retrieve inventory-api --query "authentication error handling"
yuntra context budget inventory-api
yuntra context budget inventory-api --set documentation=2000
yuntra context benchmark inventory-api --query "authentication error handling"
```

Retrieval uses deterministic local keyword matching and Markdown sections. It honors exclusions, skips sensitive files such as `.env*` and key material, removes exact duplicates, and labels token counts and savings as character-based estimates—not provider metrics.

## Controlled learning

Lessons are not global merely because an AI proposed them. They must follow:

`CAPTURED → VALIDATED → REVIEW → PROMOTED → EVALUATED`

```powershell
yuntra skills capture inventory-api --description "Add a regression test after a verified fix" --evidence "verification-2026-10-11" --scope PROJECT --applicability "Python CLI projects" --confidence medium
yuntra skills validate lesson-...
yuntra skills review lesson-...
yuntra skills promote lesson-... --yes
yuntra skills evaluate lesson-... --outcome "Improved future regression coverage"
```

Promotion always requires explicit confirmation. Project-scoped candidates do not leak into other projects; global listings show only promoted global lessons.

## Recovery, backups, policies, and dashboard

```powershell
yuntra backup inventory-api
yuntra restore --archive C:\path\to\backup.zip --destination C:\restore\new-folder
yuntra policy inventory-api git_push
yuntra dashboard inventory-api --output C:\reports\inventory-api.html
```

Restore only writes into a new destination and rejects unsafe archive paths. Checkpoints preserve direct Git evidence and report drift without resetting or discarding changes. The dashboard is a self-contained, read-only HTML snapshot; it starts no server and collects no telemetry.

## Architecture and sequence diagrams (Archify)

yuntra integrates with [Archify](https://github.com/tt-a1i/archify) to generate interactive, self-contained architecture and sequence diagrams directly from project workflows and specifications.

```powershell
# Verify Archify installation and health
yuntra diagram health

# Generate an interactive cache-aside sequence diagram
yuntra diagram generate inventory-api --name "web-request-cache-miss" --title "Web Request: Cache Miss and Database Fallback"

# List generated diagrams in the repository
yuntra diagram list inventory-api

# Show local path and browser URL to view the diagram
yuntra diagram show inventory-api --name "web-request-cache-miss"
```

Generated diagrams are stored under `.archify/` in the project repository as self-contained HTML visual traces featuring trace step playback, component inspection cards, and light/dark theme toggles.

## Safety boundaries and limitations

- yuntra never auto-commits or pushes. These defaults are disabled in every project profile.
- High-risk project policies default to deny: dependency installation, network access, destructive operations, auto-commit, and push.
- Common inline credential assignments are redacted before yuntra persists operational metadata; project plans with likely credentials are blocked from approval.
- All three adapter integrations (Codex, Claude Code, Antigravity) are limited to documented CLI capabilities. They cannot guarantee interception of every edit or accurate use of provider tokens.
- Semantic retrieval, embeddings, and hosted memory are deliberately not enabled.

## Useful commands

```powershell
yuntra --help
yuntra project inspect inventory-api
yuntra adapter list
yuntra adapter doctor
yuntra doctor
yuntra context show inventory-api
yuntra skills list inventory-api
yuntra diagram --help
```

For security policy and vulnerability reporting, see [SECURITY.md](SECURITY.md).
