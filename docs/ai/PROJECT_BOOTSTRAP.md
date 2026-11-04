# One-time project bootstrap

This records the documentation setup procedure. Normal sessions should read
`docs/PROJECT_INDEX.md`, not repeat this audit.

1. Inspected README, package metadata, CLI/source, tests, examples, local engine
   configuration and saved validation evidence. No prior docs architecture or
   Git repository existed in this directory.
2. Preserved the Python `src/`, `tests/`, `dist/` layout, original `.venv`, all
   existing results, and external engine/template repositories.
3. Kept README as the command/input/output contract owner. Added an index,
   evidence assessment, canonical roadmap, history policy, log and decision index.
4. Added the host-supported `AGENTS.md` entrypoint and the dedicated conda recipe.
5. Kept `results/` as the sole analysis/validation output root; packaging build
   directories retain their ecosystem meanings.
6. Validate local Markdown links, dependency installation, package tests and
   bounded engine execution before logging completion.

At bootstrap, no empty assets or passive bibliography directories were created.
The current visual assets are indexed in [assets/README.md](../../assets/README.md).
No changelog was created because there was no external release cadence. Create
new owners only when real content/release history exists, not as empty scaffolding.
