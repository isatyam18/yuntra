# Recovery, migrations, and security

Each project SQLite store records its schema version in `schema_meta`. Initialization uses SQLite transactions and only supports additive migrations; a database newer than the running Yuntra version is refused rather than modified. Current schema version is 1.

Checkpoints are written to a temporary sibling followed by atomic replacement. Resume considers only validated `.json` checkpoints and compares direct Git status with saved evidence. It never resets, checks out, discards, or overwrites repository changes.

Backups are zip archives of central project data. Restore requires a destination that does not exist and checks archive member paths before extraction to prevent path traversal. Policy checks reject disabled high-risk operations by default. Provider adapters remain limited by their documented sandbox and cannot guarantee interception of every provider-initiated operation.
