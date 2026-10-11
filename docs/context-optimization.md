# Context optimization

Phase 4 uses no embeddings or external service. It performs deterministic keyword matching over eligible text files, splits Markdown into heading sections, respects project exclusions plus secret-file rules, removes exact-content duplicates, and applies independent budgets to instructions, working state, documentation, code/tests, and decision history.

Every retrieval emits a manifest with selected sections, omitted material, budgets, estimated token usage, and provenance. Estimates are based on `ceil(characters / 4)` and are explicitly not provider metrics. The benchmark compares this selection against a documented all-eligible-text baseline from the same repository state.
