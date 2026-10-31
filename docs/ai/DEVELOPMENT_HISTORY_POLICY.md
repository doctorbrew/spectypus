# Documentation and history ownership

- `README.md`: current usage and scientific/software contracts.
- `docs/PROJECT_INDEX.md`: pointers to owners, with no duplicated narratives.
- `docs/roadmap/SPECTYPUS_ROADMAP.md`: future work, dependencies, acceptance
  criteria and current milestone status.
- `docs/VALIDATION.md`: what the evidence establishes and its limitations;
  detailed machine-readable evidence stays under `results/`.
- `docs/DEVELOPMENT_LOG.md`: append-only consequential changes, rationale,
  verification and remaining work. Do not copy dated history into the index.
- `docs/decisions/`: future consequential choices; its README points to
  existing informal contracts without rewriting their history.

This bootstrap preserves established package/output directories and the
independent engines. It does not move generated products, delete the prior
environment, initialize Git, or publish anything. Add `docs/CHANGELOG.md` only
when a real release cadence warrants it. Test-count snapshots in validation
records are historical evidence; live badges must come from verified CI reports.
