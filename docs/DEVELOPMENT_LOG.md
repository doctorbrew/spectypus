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


## 2026-11-01 — revise plot limits and labels; retain fitting priority

Changed display-only limit calculation to 50-Angstrom SG smoothing with a
three-bin median/MAD isolated-spike guard and 1.1× outward scaling. Removed raw
short-segment and filter-edge extrema, and avoided the three-point quadratic
identity. Native data/models/fits are unchanged. Matched SN/phase moves inside
the axes; titles follow the requested fixed/free format, all footer text is
removed and tick labels increase from 18 to 27 points. Existing galleries were
not regenerated; tests inspect figure structure with image export disabled.

Confirmed the existing controller is running both engines for eligible Chen
and Gómez inputs; the priority flag does not restrict the selected source.
Audited all 1,114 saved Fritz records and the upstream SkyPortal schema: API
wavelength units are Angstrom, but no frame declaration was found. Asked for
observer-frame confirmation before preparing a supplementary Fritz run; no
unknown frame was silently reinterpreted and the running plan was not changed.

Validation: 114 tests passed, including an in-memory layout check with image export disabled. No galleries were regenerated.


## 2026-11-01 — provisional observer-frame Fritz batch

The user clarified that Fritz spectra are almost always observer-frame, with a
possible small fraction in rest frame. Recorded this as an assumption, not a
verification or numerical probability. Added a preparation script that checks
saved metadata hashes, blocks explicit frame/unit contradictions, and extracts
only complete finite JSON arrays into derived ASCII. No source files or missing
samples are altered. Camera frame numbers are not spectral-frame evidence.

Added persistent assumption/review flags to spectrum/object summaries and CSVs;
the viewer keeps completed conditional results in review. Prepared and launched
`results/fritz_assumed_observer_20261101` with 2,851 eligible fixed/free attempts
across NGSF and SNID-SAGE. One original nm header, nonfinite/missing arrays and
duplicate wavelength inputs remain blocked. The older Chen/Gómez campaign is
unchanged and still running. Two bounded native fits succeeded and were reused
by verified execution identity. No Python galleries were rendered.

Validation: 123 tests passed, covering contradiction checks, safe JSON extraction,
assumption persistence through aggregation/CSV and the review flag after successful
fits. The run uses a frozen runtime and caffeinate; each campaign has one worker.
See `docs/FRITZ_BATCH.md` for scope, provenance, exclusions and resume commands.

## 2026-11-01 — bounded parallel campaign execution

Replaced the saved-campaign controller's one-fit bottleneck with configurable
process workers. The launcher uses the maintained scheduling controller while
importing each campaign's unchanged frozen scientific package. Each invocation
archives its controller and status; existing plan identity must match on resume.
Workers write private attempts, and one locked controller owns shared exports.
Added explicit active-run lists, incremental counts, periodic full verified
summaries (default 300 seconds), cancellation through worker/engine process
groups, and dispatch-bounded `--max-runs`. Existing disk, failure and artifact
verification safeguards remain in force.

Validation: 130 tests passed, one optional plot test skipped. Eight bounded native
fits with two workers exactly reproduced saved serial IDs, candidates, statuses
and curves. A subsequent resume executed zero fits. Measured contention motivates
an initial two workers per campaign (four total). The two active campaigns were
stopped with SIGTERM and resumed with their frozen plans and completed attempts
preserved; no classifier code, template bank, search grid or masks were changed.
Evidence, resource samples and the handover record are under
`results/parallel_benchmark_20261101_124929/`; limits and timing interpretation
are documented in `docs/VALIDATION.md`.

## 2026-11-03 — verification before GitHub synchronization

The full test suite initially reported seven controller failures because the
host had less than 20 GiB free and the tests used its actual disk capacity.
Controller tests now supply ample simulated free space by default; the explicit
low-space test overrides that fixture and still verifies dispatch is blocked.
The production disk guard and scientific execution code are unchanged by this
test fix. Validation: `python -m pytest -q` in `spectypus` passed 130 tests with
one optional plotting-dependency skip and one dependency deprecation warning.
Shell syntax and diff whitespace checks passed. Existing native benchmark and
resume records were inspected; no new real-engine fits were run.

## 2026-11-03 — isolated five-spectrum NGSF performance experiment

Created branch `perf/ngsf-five-spectrum-cache` in a separate worktree to preserve
the active campaign checkout and its local edits. Copied five length-stratified
Chen spectra with their frame/redshift provenance and hashes. Ran 20 fixed-z
fits, serially at background priority, retaining the native full extinction
grid, 947 selected SN template entries, 11 hosts, masks and score semantics.
External source/bank assets and production campaign processes were not changed.

Added opt-in benchmark launchers for error-array caching, host interpolation
caching and exact reuse of native numerical intermediates. Hooks exist only in
benchmark subprocesses. The first two steps remove repeated work but their
end-to-end benefit is not established under concurrent load. Reusing reductions
and residuals lowers native `nansum` calls from 13 to seven per grid point.
Twenty full fits yield 15 exact status/candidate/artifact comparisons. A separate
alternating-order replay on the five saved `A_v=0` fixtures measures a median
1.546× arithmetic CPU speed ratio with exact table/score equality.

Evidence and limitations are in `docs/VALIDATION.md`, commands in `docs/USAGE.md`,
and follow-up acceptance work in the canonical roadmap. Test suite: 138 passed,
one optional skip, one existing dependency deprecation warning. No free-z or
JAX speed claim is made, and the prototype is not enabled in production.

## 2026-11-03 — full free-redshift equivalence and isolated JAX testing

Ran five new intermediate-reuse fits against copied, verified historical
native free-z references, retaining all 101 redshifts and 41 extinction values.
All 20,705 grid points ran and all five status/candidate/artifact comparisons
are exact. Recorded cache counts agree with the declared experiment. A frozen
package import path keeps the benchmark separate from the active campaigns.

Added a pinned optional JAX overlay and arithmetic replay on 20 saved fixtures.
The first pilot stopped at its CPU guard and exposed a strict-overlap rounding
error. A small compiled-code reproduction confirmed constant division becoming
reciprocal multiplication; a runtime divisor restores native cutoff decisions.
The revised trial uses smaller chunks, constrained CPU dispatch, paired timing
and a blocked NumPy control. All 20 float64 real fixtures pass; float32 passes
none. Two nearly singular stress cases still fail, so JAX remains experimental.
Median arithmetic CPU ratios are 1.766× for NumPy reuse, 2.034× with blocking,
and 5.779× for JAX float64. They exclude full-engine overhead and compilation.

The isolation audit verifies source/input/reference hashes and the same live
SLSN controller, PID and plan. External assets and production settings remain
unchanged; JAX is absent from the shared environment. Evidence and limits are
recorded in `docs/VALIDATION.md`, commands in `docs/USAGE.md`, and remaining
integration/validation work in the canonical roadmap. No publication or
production-backend activation is part of this change.

## 2026-11-04 — finalize free-redshift/JAX verification report

Finished the saved comparison report and recorded final checks: 141 core tests
passed with three optional dependency skips; all five isolated JAX kernel unit
tests passed. The two numerical stress-case failures remain explicit blockers
for JAX production use. Rechecked that the original SLSN PID, controller and
plan remain active and unchanged. Completed classification experiments were
not rerun. Changes remain local to `perf/ngsf-five-spectrum-cache`.

## 2026-11-04 — guarded NGSF default and independent SAGE FFT decision

Added `jax`, `numpy` and `native` NGSF backend choices, defaulting future plans
to guarded CPU float64 JAX. Native NumPy rechecks ill-conditioned mixtures,
cancellation-sensitive/near-perfect fits and candidate contenders. Source and
JAX-version checks prevent applying the transformation to untested code;
`backend.json` records the effective implementation, fallback reason and counts.
Missing/unsupported JAX falls back to blocked NumPy; unknown NGSF source remains
native. Search grids, native scores, masks and table construction are retained.
The eight numerical stress cases pass, including both earlier JAX failures.

Fixed virtualenv Python path handling so symlinks retain their isolated
environment. Added the pinned `jax` extra to the fresh conda recipe and documented
an isolated overlay for future fits while campaigns remain active. The README
now explains the backend choices, dependencies and measured timing scope.

Twenty bounded NGSF fits on five copied spectra preserve every tested native
candidate/status/artifact comparison, including all 20,705 free-z grid points.
Fixed-z totals are 148.7 s native and 135.2 s guarded JAX: 13.5 s saved, 9.08%
less time (1.10×) in this trial under concurrent load. The older 5.78× arithmetic
ratio is not a full-fit performance claim. Historical free-z references support
equivalence but no paired speedup estimate.

Separately tested native versus experimental JAX FFTs in ten fixed-z SNID-SAGE
fits. All scientific comparisons are exact, but totals are 133.1 s native versus
138.1 s JAX. Native FFT calls take just 0.269 s across five fits. SAGE therefore
keeps its native default; the experimental hook is not exposed as a production
backend. Loading/initialization and downstream work need profiling first.

Validation: 149 core tests passed, 11 optional skips; all 21 isolated JAX
backend/kernel tests passed; CLI/example defaults and wheel contents verified.
The isolation audit verifies all 30 attempts and the unchanged live SLSN
controller/plan, source spectra and engine sources. Shared packages and active
campaigns remain untouched. PR #1 had been merged, so this follow-up uses
`perf/guarded-jax-default` based on the updated remote `main`.
