# Known limitations

- Codex is the only adapter with a verified automated CLI launch path. It still cannot intercept every edit or provide complete provider token accounting.
- Claude Code and Google Antigravity adapters currently provide capability detection and manual handoffs only. Their executable interfaces were not available for local verification.
- Context token counts are deterministic character-based estimates, not provider-reported measurements.
- Context retrieval uses keywords and Markdown sections; semantic retrieval is intentionally out of scope.
- The dashboard is a static local HTML export, not a multi-user service.
- `yuntra verify --command` executes a command explicitly supplied by the local user after plan approval. It must never receive untrusted command text.
- Private GitHub vulnerability reporting must be enabled by the repository owner after publication.
