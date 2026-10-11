## Summary

Describe the problem and the focused change.

## Verification

- [ ] Tests added or updated where behavior changed
- [ ] `python -m black --check src tests`
- [ ] `python -m ruff check src tests`
- [ ] `python -m mypy src`
- [ ] `python -m pytest -q`

## Safety and compatibility

- [ ] No credentials or private project data included
- [ ] Approval gates, centralized state, and no-auto-commit/no-push policies remain intact
- [ ] Schema, policy, adapter capability, and migration effects are documented when relevant
