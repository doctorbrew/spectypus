# Project index

This file routes readers to the owner of each topic; it is not a history log.

| Topic | Owner | When to read |
| --- | --- | --- |
| Installation, commands, inputs, outputs, support formula | [README](../README.md) | Running or integrating Spectypus |
| Conda recipe | [environment.yml](../environment.yml) | Creating the dedicated environment |
| Package/runtime dependencies | [pyproject.toml](../pyproject.toml) | Changing installation requirements |
| Verified behavior and scientific limitations | [VALIDATION.md](VALIDATION.md) | Assessing how well the pipeline works |
| Website, scale, evaluation and release tasks | [SPECTYPUS_ROADMAP.md](roadmap/SPECTYPUS_ROADMAP.md) | Choosing the next implementation task |
| Consequential development history | [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) | Understanding what changed and why |
| Decision ownership | [decisions/README.md](decisions/README.md) | Finding established contracts |
| Documentation ownership rules | [DEVELOPMENT_HISTORY_POLICY.md](ai/DEVELOPMENT_HISTORY_POLICY.md) | Updating documentation |
| Completed bootstrap procedure | [PROJECT_BOOTSTRAP.md](ai/PROJECT_BOOTSTRAP.md) | Auditing this documentation setup |
| Persistent agent rules | [AGENTS.md](../AGENTS.md) | Beginning development work |

`src/spectypus/` and `tests/` define current implementation behavior.
`results/` holds generated scientific and validation products; `dist/` and
`build/` retain their standard Python packaging roles.
