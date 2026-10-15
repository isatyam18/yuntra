# Adapter contract and provider compatibility

The adapter boundary deliberately separates canonical Yuntra state from provider-specific behavior. Adapters detect capabilities, perform health checks, export instructions, launch supported tasks, and report limitations. They do not declare hidden edits, token use, or agent claims to be verified facts.

## Codex CLI

Yuntra invokes the installed documented CLI as `codex exec -C <repository> -s workspace-write --json <prompt>`. A run is allowed only after plan approval and an additional interactive or `--yes` confirmation. It generates `codex-handoff.md` in the centralized project data directory, captures only bounded/redacted agent output, compares Git status before and after, records direct evidence separately, and saves a Yuntra checkpoint.

Unsupported: intercepting every edit, reading accurate provider token totals, and controlling Codex-internal sessions/checkpoints.

## Claude Code CLI

Yuntra invokes the installed documented CLI as `claude -p <prompt> --output-format json --allowedTools Read,Edit,Bash` in the project repository directory. A run is allowed only after plan approval and an additional interactive or `--yes` confirmation. It generates `claude-code-handoff.md` in the centralized project data directory, captures only bounded/redacted agent output, compares Git status before and after, records direct evidence separately, and saves a Yuntra checkpoint.

Unsupported: intercepting every edit, reading accurate provider token totals, and controlling Claude Code-internal sessions/checkpoints.

## Google Antigravity CLI

Yuntra invokes the installed documented CLI as `agy --dangerously-skip-permissions <prompt>` in the project repository directory. A run is allowed only after plan approval and an additional interactive or `--yes` confirmation. It generates `antigravity-handoff.md` in the centralized project data directory, captures only bounded/redacted agent output, compares Git status before and after, records direct evidence separately, and saves a Yuntra checkpoint.

Unsupported: intercepting every edit, reading accurate provider token totals, controlling Antigravity-internal sessions/checkpoints, and structured JSON output.
