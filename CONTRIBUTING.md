# Contributing to Yuntra

Thank you for helping improve Yuntra. The project is in public beta; maintainers prioritize reproducible bug reports, tests, documentation, Windows/PowerShell compatibility, isolated adapter work, and security hardening.

## Before opening a pull request

1. Discuss substantial architecture, persistence, policy, or adapter changes in an issue first.
2. Keep changes focused. Do not bundle unrelated refactors.
3. Preserve Yuntra's approval gates, centralized canonical state, local-first behavior, and no-auto-commit/no-push defaults.
4. Do not add a hosted service, vector database, background daemon, or provider automation without a demonstrated need and maintainer approval.

## Local checks

```powershell
py -m pip install -e ".[dev]"
$env:PYTHONPATH = "src"
py -m black --check src tests
py -m ruff check src tests
py -m mypy src
py -m pytest -q --basetemp .pytest-tmp
py -m build --no-isolation
```

Add or update tests for behavior changes. Never include credentials, private project data, or generated local Yuntra state in a contribution.

## Pull requests

Explain the problem, describe the solution and trade-offs, list verification evidence, and call out any policy, schema, security, or adapter-capability impact. By submitting a contribution, you agree it may be distributed under the Apache License 2.0.

Maintainers retain final control of architecture, releases, security policy, and core governance.
