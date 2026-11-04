# Project index

This file routes readers to the owner of each topic; it is not a history log.

| Topic | Owner | When to read |
| --- | --- | --- |
| Overview, classifier choice and quick start | [README](../README.md) | Getting started |
| Detailed configuration, inputs, outputs and support formula | [USAGE.md](USAGE.md) | Running or integrating Spectypus beyond the quick start |
| Logo, workflow graphic and generation prompt | [assets/README.md](../assets/README.md) | Reusing or editing the visual assets |
| Conda recipe | [environment.yml](../environment.yml) | Creating the dedicated environment |
| Package/runtime dependencies | [pyproject.toml](../pyproject.toml) | Changing installation requirements |
| CI reports, private badges and verification scope | [USAGE.md](USAGE.md#continuous-verification), [workflow](../.github/workflows/ci.yml) | Checking automated tests/builds or badge freshness |
| Verified behavior and scientific limitations | [VALIDATION.md](VALIDATION.md) | Assessing how well the pipeline works |
| ZTF priority, masking, fit overlays and overnight launch | [OVERNIGHT.md](OVERNIGHT.md) | Running or reviewing the current masked campaign |
| Provisional Fritz batch and frame assumptions | [FRITZ_BATCH.md](FRITZ_BATCH.md) | Running or reviewing the supplementary Fritz fits |
| Results website, local SLSN campaign and progress | [RESULTS_VIEWER.md](RESULTS_VIEWER.md) | Opening saved results or checking the full batch |
| Website, scale, evaluation and release tasks | [SPECTYPUS_ROADMAP.md](roadmap/SPECTYPUS_ROADMAP.md) | Choosing the next implementation task |
| Consequential development history | [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) | Understanding what changed and why |
| Decision ownership | [decisions/README.md](decisions/README.md) | Finding established contracts |
| Documentation ownership rules | [DEVELOPMENT_HISTORY_POLICY.md](ai/DEVELOPMENT_HISTORY_POLICY.md) | Updating documentation |
| Completed bootstrap procedure | [PROJECT_BOOTSTRAP.md](ai/PROJECT_BOOTSTRAP.md) | Auditing this documentation setup |
| Persistent agent rules | [AGENTS.md](../AGENTS.md) | Beginning development work |

`src/spectypus/` and `tests/` define current implementation behavior.
`results/` holds generated scientific and validation products; `dist/` and
`build/` retain their standard Python packaging roles.
