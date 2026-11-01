# Spectypus roadmap

## Goal and scope

Turn batches of reduced supernova spectra into inspectable per-spectrum and
per-object classification evidence, then support efficient human review of a
large campaign. Initial redshifts come from a user-supplied table; missing
redshifts trigger free fits. Automatic line/host redshifts follow later.

This is the canonical future-work plan. The [README](../../README.md) owns
the quick start; [USAGE.md](../USAGE.md) owns detailed commands/contracts;
[VALIDATION.md](../VALIDATION.md) owns evidence and
limitations. Probability calibration and remote CI remain unimplemented.

## Milestones

| ID | Outcome | State | Depends on |
| --- | --- | --- | --- |
| P0 | Package, reproducible execution and dedicated development environment | Complete for the bounded v0.1 validation scope | None |
| P1 | Measure classification quality against independent labels | Proposed; evaluation data required | P0 |
| P2 | Local results website for campaign and object review | Viewer, Python galleries and catalogue phases implemented; notes pending | P0; verified saved evidence |
| P3 | Measured, bounded execution at campaign scale | ZTF-priority masked fixed/free batch running; serial execution | P0; representative timing inputs |
| P4 | Improve and calibrate evidence combination | Deferred until benchmark exists | P1 |
| P5 | Line/host-assisted redshift hypotheses | Deferred | P1; redshift-labelled validation set |
| P6 | Reproducible release and verified GitHub badges | Later milestone | GitHub connection/authorization; release checks |

P1 and P2 can advance independently: a viewer is useful before accuracy is
measured, provided it labels all automated classifications as proposals.
Basic CI should start when repository hosting is established; public badge
polish and verification belong toward the end, as requested.

## P0 — package and environment

Already implemented: ASCII manifests; optional object/redshift table;
SNID-SAGE and NGSF adapters; top-ten native ranking; primary versus diagnostic
redshift modes; per-object support; duplicate suppression; immutable attempts;
hash-verified resume; explicit blocked/failure/no-match outcomes.

Environment acceptance:

- [x] Create `conda activate spectypus` with package, test tooling and engine dependencies.
- [x] Point both local classifier interpreters at that environment; preserve `classify`.
- [x] Run the full regression suite, dependency checks and bounded fixed/free engine fits.
- [x] Verify exact resume and record resolved runtime provenance under `results/`.
- [x] Establish documentation routing, history ownership and this roadmap.

The maintained recipe is `environment.yml` plus `pyproject.toml` extras. NGSF
code/parameters and both template banks remain explicit external assets.

## P1 — measure classification quality

**Scientific question:** how reliably does each engine and the combined rule
identify the class of a previously unseen object, and when should it abstain?

1. **Freeze an evaluation manifest.** Independently reviewed class/subtype,
   redshift and label provenance; physical object IDs; exposure/duplicate
   groups; phase, instrument, S/N definition and wavelength support. Represent
   ambiguous labels explicitly. Archive object counts and selection biases.
2. **Prevent leakage.** Split by physical object, never spectrum. Audit target
   objects and their epochs in template banks; exclude them for a declared
   held-out experiment or publish separate overlap/leakage strata. Keep
   threshold tuning objects out of the final test split.
3. **Evaluate fixed and blind redshift separately.** Compare each engine and
   combined support using the same held-out objects. Report top-1/top-3 class
   accuracy, per-class precision/recall and confusion, macro metrics, coverage,
   abstention, engine failures and unsupported-input fractions. Report redshift
   residuals with their definition, units and outlier criterion declared first.
4. **Audit difficult regimes.** Phase, wavelength support, S/N, redshift,
   instrument, host contribution and rare classes. Show sample sizes and
   uncertainty intervals. Object-level resampling must keep all epochs together.

Acceptance: a deterministic evaluation command and machine-readable report;
every input object remains in accounting; labelled count and class coverage
are explicit; aggregate metrics can be reproduced from predictions and labels;
software failures are never silently dropped. Define operating thresholds and
the desired precision/coverage tradeoff before opening the held-out results.
No arbitrary accuracy target or claimed sample size is assumed here.

## P2 — local results website

**User outcome:** open one campaign, see what ran and what needs attention,
then inspect why an object received its proposed class across epochs/engines.

### P2.1 — freeze review evidence and fit-curve exports

Read the current frozen plan and hash-verified attempt records. Distinguish
objects, unique spectra, engine/mode attempts and template candidates. Use
explicit `plan_id`, `execution_id`, spectrum identity and artifact hashes.
Do not discover stale historical attempts as current results.

For each displayed fit, define observed wavelength/flux, model wavelength/flux,
units/frame, masks/native support, normalization, template identity and
reconstruction provenance. Recover native fit curves where possible; otherwise
reconstruct only against the recorded engine/bank revisions and validate
agreement with native output. Missing model curves must display unavailable,
not fabricated zero flux. Viewing must never trigger classification.

Acceptance: saved-fit reconstruction checks for both engines, including
host/SN components for NGSF where available; explicit unsupported reconstruction
states; rerendering does not mutate classifier evidence or require refitting.

### P2.2 — campaign overview and review queue

Current runtime: optional `spectypus[web]` with FastAPI, vanilla JavaScript and
SVG input-spectrum plots, served on localhost with `spectypus review`. It uses
the Sample Atlas visual language and keeps core execution independent of web
dependencies. Verified current-plan records supply scores; summaries and
CSV exports are not trusted as classifier evidence. The first viewer covers
counts, source/class/name filters, pagination, a review filter, object fits,
and input spectra. ZTF/date-window and sample filters, fixed/free status links,
and saved native fit overlays are now implemented. Notes, native-score
distribution plots and further filters remain below.

- Completion/failure/blocked/no-match counts with correct denominators.
- Search and filters by object, batch, class, engine, phase, instrument,
  redshift mode, completeness and disagreement.
- Linked counts/charts and paginated table; proposed-class distributions are
  observed classification outputs, not intrinsic population distributions.
- Separate native-score plots for each engine; never put HσLAP and chi-square
  on a shared interchangeable confidence scale.
- Queue contested, ambiguous, failed and low-support objects for human review.
- Compare engine agreement and support across epochs without counting
  duplicates or diagnostic redshift fits twice.

Acceptance: filters reproduce exported table counts, including empty/partial
campaigns; corrupted evidence is flagged; missing/no-match inputs remain
visible. Test with a clearly synthetic >=1000-spectrum fixture and a measured
local page-load/memory budget; report measurements before setting a scale claim.

### P2.3 — object and spectrum pages

Per-object epoch timeline, support contributions and disagreements; per-spectrum
top-ten matches; observed/template overlays with zoom, native scores, phase,
redshift, host contribution and evidence links. Show fixed/free results side
by side as separate fits. Support is labelled uncalibrated throughout.

Store human annotations separately from immutable fits, linked to evidence
identities, with author/time/version. Provide export of reviewed decisions and
their provenance; never replace machine labels silently.

Acceptance: navigable campaign → object → spectrum → match flow; consistent
selection across plots/tables; keyboard-readable controls; gap/mask and axis-unit
tests; notes survive restart and do not change an attempt hash. Native overlays
are now saved during fitting for both engines. Notes remain future work.

## P3 — campaign scale and operational reliability

First benchmark a bounded, declared sample of short/long spectra and fixed/free
searches. Record wall time, memory, bank size, candidate counts and failures
with hardware/runtime/grid provenance. Tiny smoke timings do not extrapolate
to thousands of spectra or fine free-redshift grids.

Then implement bounded workers, cancellation/checkpointing, incremental current
views and a resource-aware queue. Preserve private attempt workspaces and a
single authoritative writer for shared indices. Cache provenance safely to
avoid repeatedly scanning an unchanged bank while still detecting changes.
Expose active/running and retrying attempts explicitly for live progress;
current summaries only show saved terminal evidence or pending work and can
retain a previous failure while its replacement attempt is running.
Add an actual native-import preflight to readiness diagnostics and record
native build identities beyond Python package versions: the environment setup
demonstrated that a version-consistent SciPy installation can still fail to load.

Acceptance: serial and multi-worker scientific outputs agree for a frozen
fixture; no duplicate active attempt; interruption/resume and concurrent-reader
tests; demonstrated memory ceiling and explicit pending/failed work counts.

## P4 — evidence combination and calibration

Use P1 to compare the current equal-engine winner baseline with class-level
candidate evidence, quality-aware weights and correlated-epoch treatments.
Avoid template-count priors and treating many epochs as independent draws.
Tune only on development objects. If probabilities are introduced, measure
reliability/calibration and proper scoring rules on held-out objects and version
the model, taxonomy and training-set provenance. Keep the original native
matches and baseline reproducible.

## P5 — automatic redshift assistance

Generate candidate redshift hypotheses from multiple narrow lines and galaxy
matches with uncertainty, line IDs, wavelength convention and association
quality. Separate host, transient and chance-superposition evidence; a single
line cannot silently become an exact host redshift. Preserve supplied catalog
values and conflicts. Retain blind fits as diagnostics where appropriate.

Acceptance: labelled redshift experiment including noise, absent lines,
sky/telluric residuals, wrong associations and conflicting catalog values.
No silent rest-frame conversion using an unverified hypothesis. SAGE ONIR/
high-redshift support is a separate tested adapter capability, not an assumed
way around the current optical cap. Reduction and FITS ingestion are separate
extensions, not prerequisites for the existing ASCII workflow.

## P6 — release, CI and badges toward the end

Current state: this checkout is connected to the private repository
`git@github.com:sPaMFouR/spectypus.git`, using its existing `main` branch and
preserving its original GPLv3 LICENSE file. Repository access is verified and
source publication is authorized. No Actions workflow or badge endpoint is
configured; package-registry publication and formal releases remain pending.

1. Repository/branch access is established. Preserve the existing license and
   define release/versioning policy before package-registry publication.
2. Add basic CI using the package's own install extras, core tests and a wheel
   import check. Separate optional real-engine integration tests from tests
   that require no external data or bank access.
3. Add JUnit/test and coverage reports; preserve the real test exit status.
4. Apply the `github-badges` workflow: actual Python floor from packaging;
   real build status; automatically generated tests-passed count and coverage
   via an existing verified endpoint or an explicitly authorized user-controlled
   gist. No hand-maintained count badges or broken placeholder URLs.
5. Keep badge-update plumbing `continue-on-error: true`; use trusted events for
   secret-bearing updates; give build status and test-count badges distinct labels.
6. After an authorized push, inspect the actual step-level Actions logs and
   rendered badge values. Until a real run and endpoint are verified, report
   configuration as prepared/pending, never as working remote CI.

Acceptance: a green real build whose step logs were read, installed wheel smoke,
valid report-derived count/coverage, correct rendered values, and reproducible
release artifacts. Badge-only failure cannot mark successful tests as failing;
collection failure cannot produce a green zero-tests badge. Record verification
in the development log. Do not create public resources or request credentials
merely to write this roadmap.
