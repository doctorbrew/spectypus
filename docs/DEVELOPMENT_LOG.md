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

## 2026-10-31 — Spectypus identity and compact getting-started guide

Added a transparent Spectypus logo combining a spectrum-shaped platypus,
supernova star and wordmark. Saved the generated PNG and its prompt under
`assets/`, alongside an editable workflow SVG showing reduced-spectrum inputs,
redshift routing, both classifier adapters, native rankings and object support.
The diagram represents logical engine branches while explicitly retaining
serial execution; it does not imply a raw-data reduction capability.

Reduced README from 1,804 to 438 whitespace-delimited words. It now focuses on
purpose, avoided manual orchestration, classifier choice, installation and a
bounded first run. No measured speedup or accuracy improvement is claimed.
Moved the detailed guide and scientific contracts to `docs/USAGE.md` and
updated the index, decision links and history policy to that single owner.
Source distributions include the visual assets. Pipeline behavior is unchanged.

Verified PNG transparency, SVG structure and visual layout, 35 local links,
CLI command syntax and a synthetic manifest/plan dry run with zero classifier
executions. A fresh source distribution includes both graphics and the detailed
usage guide. Validation evidence is under `results/branding-doc-check-q1g3jr0q/`.


## 2026-10-31 — results website and full local SLSN batch

Pushed the logo/workflow and compact README in commits `b59bbd3` and `8ba4b0a`.
Added the optional localhost results viewer (`spectypus review`), with verified
current-plan reads, progress/class counts, paginated filters, object fits, top
native candidates and original-input plots. Missing template curves remain
unavailable. Compact review records retain every tied winning vote. Core batch
execution still has no web dependencies.

Read the existing source atlas without modifying it and froze 3,876 spectrum
records for 344 catalogue objects. The plan has 2,930 eligible classifier
attempts on 1,481 unique spectra from 214 objects. Input checks, mostly unknown frame/unit metadata,
block 2,378 records; 17 repeats contribute once, and SAGE has 32
additional support exclusions. Thirty targets have no downloaded Fritz spectra;
this does not imply absence from other archives.

Launched a serial batch in the dedicated environment with a frozen package
snapshot, single-thread numerical libraries, a 900-second per-fit timeout and
a 20-GiB free-space stop. Short/long fixed/free representatives run first as
ordinary batch members. The controller records the active fit and stops after
six consecutive failures. New controller tests protect an active status file
from a second writer. The maintained controller also handles SIGTERM; the
already launched original controller snapshot is preserved unchanged.

Validation: 91 tests passed; JS syntax and desktop/mobile shell previews passed;
wheel assets verified. Actual early snapshot read/curve verification took about
0.315 seconds with 117 MiB process maximum RSS. The first four fixed fits
completed, while the first fine free-redshift search was still running. This is
partial execution evidence, not measured classification accuracy. Paths, scope,
launch/resume instructions and remaining viewer work are documented in
`docs/RESULTS_VIEWER.md` and `docs/VALIDATION.md`.

## 2026-10-31 — masked fits, ZTF review and overnight execution

Added configurable observer-frame telluric windows and native fit-curve capture
for NGSF and SNID-SAGE. NGSF masks the object and template samples in the fit's
normal equations; SAGE uses native mask-aware preprocessing. Compatibility hooks
stay inside the classifier subprocesses; external engine source and original
spectra are unchanged. Expected host-line positions use supplied redshifts and
are guides, not detections or automatic masks.

Repaired 51 identical repeated rows in a derived copy of the Chen SN2018hti
spectrum. All 78 Chen files now pass input validation. Added a retry-preparation
script that preserves prior attempts and rejects conflicting duplicate samples.

The user confirmed the atlas priority window, 2018-03-17 inclusive through
2026-01-01 exclusive. The viewer defaults to ZTF objects in that window, shows
catalogue sample membership and Fritz/TNS links, and provides fixed/free links
for each engine. Green means the requested searches finished, including explicit
no-good-match outcomes; red means unfinished. Review opens an epoch selector,
top-ten native candidates and verified model overlays with telluric bands and
expected host-line markers. Operational completion includes diagnostic modes;
combined class support still uses primary modes only.

Stopped the older unmasked batch cleanly and launched a fresh masked batch with
both modes, since the changed protocol and missing free-z fits prevent reusing
old fixed-only scores. It has 5,194 eligible fits, with 1,854 fits for 118 eligible
ZTF-era objects first. The serial controller uses a frozen runtime, timeout and
disk guards, and resumes verified finished attempts. The macOS launcher holds
sleep assertions for the job lifetime; `pmset -g assertions` verified them.

Validation: 104 tests passed, six bounded native engine runs saved 60 verified
overlays, and desktop/mobile viewer checks passed. One SAGE run returned no good
match. The full campaign is still running; no accuracy estimate follows from
these checks. Added `docs/OVERNIGHT.md` and updated the roadmap and validation
assessment. Scientific inputs, generated products and local configuration remain
outside Git.


## 2026-11-01 — Python fit galleries, explicit phases and brighter logo

Replaced browser SVG fitting plots with cached Matplotlib/LaTeX exports using the
canonical bundled plot-style helper. Each reviewed engine/mode has a top-ten
collage and scrollable individual matches, with vector PDF and 300-dpi JPG pairs.
A gap-aware 25-Angstrom Savitzky–Golay filter determines the requested 1.25-times
extrema limits only; native spectra, scores and model curves remain unchanged.
Template names/phases and target catalogue phases are labelled separately.

Prepared a review-only phase sidecar from exact-alias local catalogues: 333/344
objects have references. Discovery and band-specific maxima remain separate;
conflicting dates are shown with provenance. No live catalogue query or new
light-curve fit was performed. The running campaign's frozen inputs, runtime and
classifier environment are unchanged; plotting uses an isolated environment.

Expanded fit-button counts and reasons. The reported SN2018avk 4/14 state is four
finished plus ten ingestion blocks (nine unknown frames, one unknown unit), not
four failures. Brightened the transparent logo's navy lettering and outlines
using the built-in image tool and removed its white website backing.

Validation: 110 tests passed; real NGSF and SAGE galleries exported and inspected.
The earlier HTTPX deprecation warning remains unrelated to plot correctness.
