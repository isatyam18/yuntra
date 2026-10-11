# Troubleshooting

## `yuntra` is not recognized

Run commands with `py -m yuntra.cli` from the repository after setting `$env:PYTHONPATH = "src"`, or reinstall with `py -m pip install -e .`. Confirm the Python Scripts directory is on `PATH`.

## Permission errors in temporary directories

Some restricted Windows environments do not allow Python tools to use their default temporary directory. Use a writable workspace directory:

```powershell
$env:TEMP = (Resolve-Path .pytest-tmp)
$env:TMP = $env:TEMP
py -m build --no-isolation
```

## Plan cannot be approved

Run `yuntra plan review <project>`. Complete every required section in `PROJECT_SPEC.md` and remove any likely credential assignments such as API keys, passwords, tokens, or authorization values.

## Codex, Claude Code, or Antigravity is unavailable

Run `yuntra adapter list` and the adapter's `health` command. Yuntra remains usable without external tools: use project plans, decisions, verification, checkpoints, exports, and manual handoffs.

## Recovery reports repository drift

Yuntra does not discard changes. Inspect `git status`, review the checkpoint's next action, run required verification, then save a new checkpoint once the state is understood.
