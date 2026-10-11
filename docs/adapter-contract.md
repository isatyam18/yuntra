# Adapter contract and Codex compatibility

The adapter boundary deliberately separates canonical Yuntra state from provider-specific behavior. Adapters detect capabilities, perform health checks, export instructions, launch supported tasks, and report limitations. They do not declare hidden edits, token use, or agent claims to be verified facts.

## Codex CLI

Yuntra invokes the installed documented CLI as `codex exec -C <repository> -s workspace-write --json <prompt>`. A run is allowed only after plan approval and an additional interactive or `--yes` confirmation. It generates `codex-handoff.md` in the centralized project data directory, captures only bounded/redacted agent output, compares Git status before and after, records direct evidence separately, and saves a Yuntra checkpoint.

Unsupported: intercepting every edit, reading accurate provider token totals, and controlling Codex-internal sessions/checkpoints. Claude Code and Antigravity remain manual fallbacks until separately verified.

## Claude Code and Google Antigravity

Separate adapters check their provider-specific executable names (`claude` and `antigravity`) and generate provider-labeled manual handoffs from the same central specification. Neither executable was available during Phase 3 implementation, so Yuntra deliberately implements no task-launch command, hook, edit interception, or usage capture for either one. Their `health` and `limitations` commands explicitly report this condition.
