# Known limitations

- All three adapters (Codex, Claude Code, Google Antigravity) support automated CLI task launch, but none can intercept every edit or provide complete provider token accounting.
- Context token counts are deterministic character-based estimates, not provider-reported measurements.
- Context retrieval uses keywords and Markdown sections; semantic retrieval is intentionally out of scope.
- The dashboard is a static local HTML export, not a multi-user service.
- `yuntra verify --command` executes a command explicitly supplied by the local user after plan approval. It must never receive untrusted command text.
- Private GitHub vulnerability reporting must be enabled by the repository owner after publication.
