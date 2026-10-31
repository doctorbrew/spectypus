# Development log

Append consequential changes here. Current usage belongs in README; current
milestone status belongs in the roadmap. This log starts with the documentation
bootstrap; earlier implementation evidence is linked rather than backfilled.

## 2026-10-31 — dedicated conda runtime, validation and project bootstrap

Created a clean `spectypus` conda environment for the pipeline, tests and both
classifier subprocesses. Added `environment.yml`, the optional `engines`
dependency group, and source-distribution inclusion of setup/docs/examples.
The local config now points both adapters to the new interpreter; the previous
config is archived under `results/conda_validation/`. Existing `classify`,
`.venv`, independent NGSF/template repositories and historical results remain.

Initial real-engine tests exposed a macOS loader failure in the pip SciPy
1.15.2 `_spropack` binary, despite passing core tests and metadata checks. The
same-version conda-forge NumPy/SciPy builds passed native imports. The recipe
now installs those binaries before pip; failed attempts and initial inventories
remain beside final evidence. This was an environment failure, not a no-match
classification result. Native-import preflight and stronger native-build
provenance are recorded as future operational improvements.

Verification: 83 tests passed in conda; `pip check` and native imports passed;
four fixed and two free real-engine attempts completed; exact reruns reused
all six with zero new fits. Scope remains two spectra of SN 2022vxc, with one
redshift deliberately withheld for free-fit testing. No accuracy, calibrated
probability or large-campaign performance claim follows from this experiment.
Machine-readable evidence: `results/conda_validation/validation.json`.

Applied project-housekeeping: added AGENTS, project index, validation assessment,
canonical roadmap, decision index, bootstrap record and history ownership
policy. Preserved standard Python directories and `results/`; avoided empty
assets/reference/changelog scaffolds. README remains the usage/contract owner.

The roadmap now covers independent-label evaluation, a local campaign/object/
spectrum review website, fit overlays, bounded scaling, calibration and later
line/host redshift hypotheses. GitHub Actions/badges are a later milestone:
real reports, a verified metrics endpoint, actual run logs and rendered values
are required. No website, Git initialization, remote publication, badge endpoint
or CI success was claimed or created in this step.

## 2026-10-31 — prepare initial development publication

Connected this checkout to the existing private `sPaMFouR/spectypus` repository
and retained its `main` history and original GPLv3 LICENSE without modification.
Prepared four logical development commits: standalone pipeline, regression
tests, conda setup/examples, and project guidance/roadmap. Only source and
development documentation are included; local environments, configurations,
spectra, dependency inventories and generated results remain outside Git.

Publication checks cover the core regression suite, a fresh package build,
staged-file/whitespace checks and confirmation that existing remote history is
an ancestor of the development commits. This is a source-development push,
not a package release or a claim of verified GitHub Actions/badges. Local
validation links are explicitly labelled as unavailable from a fresh clone.
