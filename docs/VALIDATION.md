# What has been validated

Spectypus is an exploratory classification pipeline. Software integration has
been exercised; classification accuracy, probabilities, and large-campaign
throughput have not been established.

Evidence paths under `results/` refer to local, ignored products and are not
distributed in the GitHub repository. Core tests run without those products;
real-engine checks additionally require the declared external inputs and banks.

## Existing baseline

The initial implementation passed 83 regression tests covering ingestion,
redshift routing, units/frames, native ranking, duplicates, support denominators,
timeouts, resume, tampering, provenance drift, and SAGE optical-profile limits.
The original local evidence is in `results/validation.json` in the original
development checkout; generated validation products are not distributed in Git.
This is a historical test count, not an automatically refreshed badge.

Its real-engine smoke used **two spectra of one supernova, SN 2022vxc**: both
engines at supplied redshift for both epochs (four attempts), and both engines
on one spectrum with redshift deliberately withheld (two attempts). All six
completed and were reused on exact rerun. The free NGSF grid was deliberately
coarse, 0–0.3 in steps of 0.05. These are integration checks, not six independent
classification successes or a representative accuracy sample.

## What the current outputs mean

- `completed` establishes that an engine produced parseable native evidence.
  It does not establish that the best template gives the correct class.
- Class support preserves disagreement and abstention. An engine winner has
  equal weight regardless of whether its advantage over second place is small.
  NGSF currently has no calibrated acceptance threshold in this package.
- Repeated observations, similar templates and engines may share errors.
  Duplicate removal does not make distinct epochs statistically independent.
- SAGE uses its optical profile: >=2000 Angstrom overlap in 2500–10000
  Angstrom and redshift at or below 1.0. Unsupported requests are blocked;
  absence of model support is not a negative classification result.
- Original error columns are recorded as ignored; engines use their native
  noise treatment. FITS input, line-derived redshifts and reduction are absent.
- The basic batch command is serial; the saved-campaign controller supports
  bounded parallel workers. No thousand-spectrum throughput or memory claim
  has been measured.
- `spectypus review` provides a local read-only results website: progress,
  suggested-class counts, searchable objects, top native matches, and input
  spectra with verified source hashes. New runs can save native template overlays;
  review notes remain unavailable. The older project's separate review websites are not
  part of this package.

## Dedicated-environment validation

The `spectypus` conda environment runs the package and both classifier
subprocesses using Python 3.10.22. All 83 tests passed there; both engines
completed the same six bounded fixed/free checks, and an exact rerun reused
all six without new fitting. Dependency and native-import checks also passed.
These repeat the same two-spectrum integration experiment, not an expanded
accuracy study.

Evidence is under `results/conda_validation/`: see the local
`results/conda_validation/validation.json` record, JUnit report,
interpreter paths, conda/pip inventories, input/config hashes, attempt states
and resume counts. The older
`.venv` and `classify` evidence remains intact. The environment recipe pins the
known scientific stack; full resolved versions are recorded locally because
the recipe is not an all-platform transitive lockfile.

The first pip SciPy 1.15.2 installation failed in both engines with a macOS
`_spropack` loader error (`__thread_bss` zero-fill section offset). Replacing
NumPy/SciPy with the same-version conda-forge builds restored native imports;
the recipe now installs these binaries before pip extras. This demonstrates
why passing core tests, package metadata checks, or `doctor` fingerprinting
alone is not proof that native classifier execution works. Keep the initial
failure attempts and the final conda/pip inventories for provenance. Runtime
package versions do not identify every same-version native-binary rebuild.

## Results viewer and first full local batch

On 2026-10-31, 91 tests passed, including read-only result verification,
corruption handling, input checksum changes, native-vote preservation when
compacting the review data, pagination of a synthetic 1,000-spectrum blocked
batch, and controller failure/concurrent-writer handling. JavaScript syntax,
desktop/mobile HTML previews and packaged wheel assets were checked. The test
client emits an upstream HTTPX deprecation warning; checks pass.

Against the actual 3,876-record plan with four completed fits, loading and
verifying the review snapshot and one input curve took 0.315 seconds and the
process maximum RSS was about 117 MiB on this macOS host. This is an early,
mostly pending snapshot measurement, not a full-completion memory/latency claim.
The reader retains the top displayed candidates and all tied winning votes,
instead of retaining every native candidate in memory.

The full local batch was launched with 2,930 eligible fits. Its first four fixed
fits completed in 30.1–34.1 seconds each, spanning a 208-sample spectrum and a
107,973-sample spectrum. Fine free-redshift searches (NGSF 0–1 in 0.01 steps)
were still executing at this checkpoint. No whole-campaign runtime or accuracy
claim follows from those four fits. See [RESULTS_VIEWER.md](RESULTS_VIEWER.md)
for exact scope and the live local status paths.

Validation products are in `results/slsn_20261031/`: `viewer-tests.xml`,
`viewer-validation.json`, `viewer-preview.html`, `import.json`, `launcher.json`,
`campaign_status.json`, and immutable attempt directories below `run/`.

## Masked fits, native overlays and ZTF-priority rerun

The updated implementation passed **104 tests** in the dedicated environment.
Additional checks cover observer-frame masks, supplied-redshift host markers,
NGSF object/template exclusion from its normal equations, derived input repair,
engine/mode status buttons, catalogue filters, verified model-curve reads and
completion that waits for diagnostic free-redshift runs. The synthetic NGSF
check changes masked samples by a large amount and verifies unchanged fitted
coefficients; conflicting duplicate wavelengths remain rejected.

Six bounded native runs used two Chen spectra: SN2018avk at MJD 58,242 and the
repaired SN2018hti spectrum dated 2018-12-31. Both engines ran at supplied z on
both spectra, then both ran free-z on SN2018avk. Five produced accepted native
candidate results; SAGE returned no good match for SN2018hti. All six saved ten
overlays, including the rejected SAGE candidates, and all **60 overlays** passed
the viewer's candidate/artifact identity checks. A saved overlay is not proof
of a correct classification. The bounded free NGSF grid was 0.05–0.2 in steps
of 0.05; the overnight grid remains 0–1 in steps of 0.01.

Evidence is in `results/masking_validation_20261031/validation.json`, its fixed
and `free/` attempt directories, and the desktop/mobile viewer previews. The
JUnit report is `results/slsn_ztf_overnight_20261031/tests.xml`. JavaScript syntax
and the saved review page were checked; plots show actual saved native arrays.

The earlier unmasked batch was stopped cleanly and preserved. A new masked,
fixed-plus-free batch contains 5,194 eligible attempts on 1,482 spectra, with
1,854 attempts for 118 eligible ZTF-era objects first. The confirmed priority
window is **2018-03-17 inclusive to 2026-01-01 exclusive**. Catalogue date
proxies, with a name-year fallback, determine priority rather than scientific
sample inclusion. All 78 Chen spectra pass input validation after removing 51
identical rows from one derived copy; original files are unchanged. Inputs
without declared wavelength frame/unit, including Fritz spectra, remain blocked.

The new batch is running, not a completed accuracy or throughput experiment.
macOS sleep assertions were verified for its controller. See
[OVERNIGHT.md](OVERNIGHT.md) for the live status, exact protocol, viewing and
resume commands. No environment or frozen runtime was changed after launch.

## Next falsifiable evaluation

The [roadmap](roadmap/SPECTYPUS_ROADMAP.md#p1--measure-classification-quality)
owns the evaluation protocol and implementation tasks. It requires independent
labels, object-disjoint splits, an explicit template-leakage policy, per-class
precision/recall and confusion, coverage/abstention, and failure denominators.
Until that experiment is performed, no accuracy percentage is defensible.


## Python plot galleries (2026-11-01)

110 tests pass, including gap-aware 25-Angstrom smoothing for display limits,
unchanged input curves, explicit coarse/missing-segment behavior, phase time-system
conversion, observer/rest-frame distinctions, conflicting reference dates and the
4-finished/10-blocked status breakdown. NGSF and SAGE saved curves for SN2018avk
were exported as ten individual PDF/JPG pairs and one collage pair per engine.
The JPGs use 300 dpi; PDF curves are vector. Figures were visually inspected.
Evidence is in `results/python_figures_20261101/` and the current campaign's
`run/review_figures/`. This validates plotting, not classification accuracy.


## Revised limit calculation (2026-11-01)

114 tests pass in the plotting environment. New checks cover isolated-spike
amplitude invariance, preservation of broad features, mask/gap separation,
coarse three-point smoothing, filter-edge exclusion, the exact title and match
label formats, 27-point ticks and removal of all figure footer text. Layout was
inspected in memory with export disabled; no saved galleries were regenerated.
An initial SciPy native median-filter path crashed in this environment; the
three-sample median guard now uses explicit NumPy neighbours instead. The full
suite passes without changing the running classifier environment.


## Provisional Fritz execution (2026-11-01)

123 tests pass. Assumption-specific tests cover original unit conflicts, explicit
rest-frame indicators, avoiding false positives from camera frame numbers, lossless
finite JSON-array extraction, refusing missing samples, and keeping frame-review
flags after successful classification. One Fritz spectrum completed in both native
engines; exact execution IDs and saved artifacts were verified before reuse in the
full batch. Results are conditional on the observer-frame assumption. Neither
these tests nor fixed/free agreement establishes an individual spectrum's frame.
See [FRITZ_BATCH.md](FRITZ_BATCH.md) and local `preflight.json` for the run scope.

## Bounded parallel execution (2026-11-01)

130 tests pass in the `spectypus` environment; one optional plotting-dependency
test is skipped. Controller regressions cover serial/parallel candidate equality,
verified resume without duplicate execution, dispatch limits, simultaneous worker
bounds, engine-process cleanup on cancellation, disk and repeated-failure guards,
worker crashes, corrupt-artifact retry, plan-drift rejection, and the single-writer
lock. Full exports are now periodic rather than rebuilt after every fit. Native
artifact and external-runtime verification remain enabled.

`results/parallel_benchmark_20261101_124929/validation_contract.json` declares two
spectra (1,642 and 5,956 samples), selected as the shortest/longest among spectra
with all four engine/mode serial results already available. Eight native fits
ran with two workers while the two original serial campaigns continued. All
eight execution IDs, statuses and candidate values matched the verified serial
baselines exactly; staged spectra, redshift-grid records, mask reports and saved
fit curves also matched byte for byte where present. `check_results.py` reproduces
the comparisons; `comparison.json` records them. The final controller's resume
reused all eight attempts without a new fit (`resume_verification.json`).

The bounded batch took 794.81 seconds, versus 1,135.77 seconds summed over the
saved serial engine timings (which exclude serial controller overhead). This is
not a controlled whole-campaign speed measurement: machine load differs, and
parallel free-redshift fits took longer individually. Sampled peak combined RSS
for the benchmark controller/workers/engines was 1.12 GiB, excluding the original
campaigns and startup before resource sampling began. `resource_samples.json`
retains the samples. Start with two workers per campaign, four fits total, rather
than assuming all eleven CPU cores yield linear speedup.

The handover retains the scientific package, inputs, settings and plan identities.
`handover.json` records old/new controller PIDs and preexisting result pointers;
completed evidence is preserved. This validates scheduling and reproducibility
for the declared cases, not classification accuracy or a calibrated finish-time
forecast. Further worker increases require a measured timeout/memory/throughput
check under the intended total campaign load.

### Synchronization verification (2026-11-03)

`python -m pytest -q` in `spectypus`: 130 passed, one optional plotting-dependency
test skipped, and one Starlette/httpx deprecation warning. An initial run had
seven controller failures caused by the host's free space falling below the
production 20 GiB guard. Controller tests now mock available capacity, with the
low-space regression explicitly overriding it to verify blocked dispatch. This
isolates scheduling checks from host capacity without changing the real guard.
`bash -n scripts/overnight.sh` and `git diff --check` also passed. The existing
native comparison and resume records were inspected, but no native fits were
rerun for this synchronization.

## Five-spectrum NGSF optimization experiment (2026-11-03)

Development is isolated on `perf/ngsf-five-spectrum-cache` in the sibling
`_Project_SpecTypus_ngsf_perf` worktree. Production code and the external NGSF
checkout/bank are unchanged. The experiments use subprocess-local hooks and
copied inputs, one background-priority worker (`taskpolicy -b`, nice 15), and
single-thread numerical libraries. The active SLSN campaign is not restarted
or reconfigured. Shared CPU/disk activity remains a timing confounder.

Five unique Chen spectra were copied directly from the SLSN project using
input-length quantiles among eligible spectra with catalogue redshifts:
SN2018bgv, SN2019cwu, SN2019gqi, SN2020dlb and SN2020jii. They span 1,642–6,685
input samples. Original hashes, rest-frame Angstrom declarations and catalogue
redshift provenance are retained. Each trial uses the supplied fixed redshift,
all 41 native extinction points (`-4..4`, step `0.2`), 947 selected SN template
entries, 11 host templates, original overlap rules, telluric masks and native
`CHI2/dof2` scoring. No grid thinning or template pruning is applied.

Twenty full fits compare four stages. All 15 comparisons to the five native
baselines preserve statuses and candidate records exactly, with byte-identical
native CSVs, staged spectra, mask reports and saved fit curves. Each stage has
two completed-match results and three no-good-match results.

| Stage | Change | Observed total core time, five fits | Recorded attempt time, five fits |
| --- | --- | ---: | ---: |
| 0 | Native reference | 141.57 s | 498.38 s |
| 1 | Cache the object-error array | 95.75 s | 448.49 s |
| 2 | Also cache host interpolation at each redshift | 98.89 s | 443.22 s |
| 3 | Also reuse native reductions and residuals | 68.39 s | 400.15 s |

These totals are **observations under varying concurrent load**, not controlled
causal speedup estimates. Stage ordering rotates for the first three stages;
stage 3 follows them. One native spectrum's core took 52.42 s, whereas its cache
variants took about 17 s; the small cached error calculation cannot account for
that difference. Stage 1 reduces error computations from 205 to five across the
sample, but the first native fit spent only 0.088 s of 21.14 s in that function.
Stage 2 similarly reduces galaxy interpolation evaluations from 205 to five.
Large end-to-end gains from those caches alone are not established. Attempt
time includes runtime verification and engine startup but excludes planning
and final artifact hashing. Stage 3 also saves a numerical replay fixture.

Stage 3 reuses five identical native reductions and the residual array: 13
`nansum` calls become seven per grid point, with no changed summation order or
score formula. A source-shape check rejects unsupported transformations. Tests
cover masks, cache mutation isolation, redshift/grid invalidation, singular
mixtures and overflow; full native result comparisons cover the real fits.

To separate arithmetic from startup/load effects, the masked arrays at `A_v=0`
were replayed for each spectrum. Five measured pairs per case alternate native
and optimized order after one excluded warm-up pair. Every native table column
and returned score remains exactly equal. The median of the five per-spectrum
paired CPU-time ratios is **1.546×**, with per-spectrum medians **1.51–1.57×**
(about **35% less arithmetic CPU time**). This excludes interpolation, error
estimation, template loading, provenance checks and disk I/O; it is not a
whole-campaign speedup, free-redshift validation or classification-accuracy claim.

Evidence in the development worktree:

- `results/ngsf_cache_five_20261103/`: input provenance, frozen code/configuration,
  15 native/cache attempts, component timings and ten exact comparisons.
- `results/ngsf_core_reuse_five_20261103/`: five stage-3 attempts, numerical
  fixtures, five exact full-fit comparisons and `paired_replay.json`.
- `results/ngsf_core_reuse_five_20261103/report/`: machine-readable totals,
  per-spectrum CSV and an HTML comparison.

The first runner inherited a relative `PYTHONPATH`; its editable-install
fallback package was checked byte-for-byte against the worktree and matched.
`package_source_check.json` retains this check. Subsequent runners explicitly pin
the worktree's absolute package path. Code snapshots record the executed versions.
Final automated checks: 138 passed, one optional plotting-dependency test skipped,
one existing Starlette/httpx deprecation warning. Free-redshift searches, other
NGSF versions, JAX and production integration remain unvalidated by this trial.

## Free-redshift and JAX follow-up (2026-11-03)

The follow-up keeps the same isolated worktree and five copied spectra.
`results/ngsf_free_five_20261103/` freezes the package, scripts, input/configuration
and verified historical native free-z reference attempts. Each new fit retains
the complete 101-redshift by 41-extinction grid, 947 SN entries and 11 hosts,
with original masks, overlap rules, scores and curve capture. The bounds are
five fresh attempts, one nice-15 worker, one numerical thread, and 2,400 seconds
per attempt. Unlike the preceding fixed-z trial, this runner does not request
macOS background I/O policy. It leaves the production campaign's settings and
900-second timeout unchanged. Historical native wall times are unpaired;
different scheduling and concurrent load preclude a causal speed comparison.

All five full free-z fits passed exact comparison against their copied native
references: statuses, candidates, staging metadata, effective parameters,
native CSVs, saved curves, masks, staged spectra and redshift-grid records.
The result remains two completed-match cases and three no-good-match cases.
Each fit executed all 4,141 core calls, with one error-array computation and
101 host-interpolation computations. Across the sample that is 20,705 grid
points, five error computations and 505 host interpolations. No grid point or
template was removed. `comparison.json` retains every comparison and timing.

| Spectrum | Native outcome preserved | New attempt time |
| --- | --- | ---: |
| SN2018bgv | Completed match | 812.96 s |
| SN2019cwu | No good match | 742.61 s |
| SN2019gqi | Completed match | 699.19 s |
| SN2020dlb | No good match | 773.59 s |
| SN2020jii | No good match | 798.29 s |

These checks extend intermediate-reuse equivalence to this full free-z setup.
They do not establish classification accuracy, other engine versions or a
whole-search speed factor. Production integration remains separate.

JAX is installed only in the worktree's `.venv` overlay. The shared `spectypus`
environment retains its existing engine packages and no JAX installation.
The optional `benchmark-jax` extra pins JAX/jaxlib 0.6.2 for this Python 3.10
experiment. All JAX work uses the CPU backend and explicitly enabled float64;
float32 is a negative precision control. Following the
[JAX benchmarking guidance](https://docs.jax.dev/en/latest/benchmarking.html),
the runner synchronizes device work, separates first-call/transfer costs, and
compares warmed operations on the same saved numerical arrays. It does not
patch the production engine or measure a GPU.

The initial 32-template-chunk pilot in `results/jax_fixed_five_20261103/` stopped
after its first float64 fixture: measured warm process CPU/wall was 1.624,
above the declared 1.5 resource guard despite single-thread environment flags.
Its apparent wall-speed ratio is therefore not an accepted single-core result.
Top-ten identities agreed, but finite/invalid score masks did not. The first
fixture has 44 template/host combinations exactly at the strict 70% overlap
boundary. Small reproductions in `results/jax_boundary_probe_20261103/` show
that using a runtime sample-count divisor restores the native cutoff decision,
including an actual template from that fixture. The compiled-code probe in
`results/jax_overlap_lowering_20261103/` confirms reciprocal multiplication for
a constant divisor: `364/520` becomes `0.7000000000000001`, whereas native and
runtime division give `0.7`. That last-bit change crosses the strict cutoff.
JAX documents how compiler rewrites can alter
[floating-point results](https://docs.jax.dev/en/latest/faq.html#jit-changes-the-exact-numerics-of-outputs).

The updated probe in `results/jax_positive_mixture_probe_20261103/` also tests
a nearly singular mixture with positive coefficients. It exposes coefficient
and residual-statistic differences, in addition to a coefficient difference
on a rejected near-singular mixture. The ordinary, negative-coefficient,
strict-overlap, exactly singular, zero-error and tiny-error cases agree after
the overlap correction. These findings are reasons to retain numerical gates,
not to loosen them or silently change the native scoring method.

The follow-up replay uses eight-template chunks, `NPROC=1`, disabled asynchronous
CPU dispatch and the same measured resource guard. Float64 acceptance requires
identical NaN/Inf masks, exact sample counts and ordered top-ten indices, and
all finite coefficients/statistics within `rtol=1e-9`, `atol=1e-10`. An edge-case
failure blocks overall numerical acceptance even when real-spectrum fixtures
pass. Alternating-order timing pairs compare native NumPy, reused NumPy,
reused NumPy in the same small blocks, and JAX. Both NumPy variants must remain
bit-for-bit equal to native arithmetic. The block control separates memory
locality from compilation benefits. All replay timings exclude interpolation,
template loading, native-table reconstruction and whole-search ranking.

The completed replay in `results/jax_fixed_free_twenty_20261103/` covers all
20 fixtures: five supplied-redshift points and `z=0, 0.5, 1` for each spectrum,
all at `A_v=0`. Float64 passes all 20 numerical/ranking checks; float32 passes
zero. Six of eight synthetic cases pass, but both nearly singular cases fail,
so **overall JAX numerical acceptance is false**. Both NumPy reuse variants
remain bit-for-bit equal to native arithmetic on all 20 real fixtures.

| Arithmetic implementation | Median paired CPU speed ratio to native | Native-equivalence evidence |
| --- | ---: | --- |
| Reuse NumPy reductions/residuals | 1.766× | Exact on 20 fixtures; full-fit checks separately pass |
| Also process eight SN templates per block | 2.034× | Exact on 20 fixtures; full-fit block implementation untested |
| JAX float64, eight-template blocks | 5.779× | 20/20 real fixtures within tolerance; two stress cases fail |

The JAX CPU ratio spans 5.25–6.64× across fixtures. Its median paired ratio is
3.32× against unblocked NumPy reuse and 2.83× against blocked NumPy reuse.
These are warmed arithmetic CPU measurements, not full-classifier acceleration
factors. They also differ in scope from the earlier 1.546× replay, which included
native table reconstruction. The float64 first compiled-shape call took
0.179 seconds, with that shape reused across all 20 fixtures. The maximum
observed warm process CPU/wall ratio across both precision modes was 1.135,
below the 1.5 stop threshold; this measures the resource controls' effect
without asserting perfectly single-threaded JAX execution.

`report/comparison.html`, `report/per_fixture.csv` and `report/summary.json`
provide the interactive comparison and underlying figures. The isolation audit
in `results/ngsf_free_five_20261103/audit/isolation.json` verifies original and
copied input hashes, reference/new attempts, frozen files, cache/grid counts,
unchanged native source, and the same live SLSN PID, controller and plan.
The shared environment still has no JAX installation. No production backend,
campaign configuration, template bank or scoring rule was changed.

Follow-up before a JAX backend: preserve native behavior for ill-conditioned
mixtures (for example through a tested native fallback), then expand beyond
`A_v=0` fixtures to full-search and additional-version comparisons. Blocking
NumPy arithmetic is a separate promising option requiring full-fit validation.

Automated verification: the core suite passed 141 tests with three optional
dependency skips and one existing Starlette/httpx deprecation warning. The
isolated JAX environment passed all five kernel unit tests, including the
strict decimal-overlap regression (rechecked on 2026-11-04). These unit-test
passes do not override the two failed numerical stress cases above.

## Guarded backend integration (2026-11-04)

The installed NGSF adapter now offers `native`, `numpy`, and JAX-preferred
`jax` execution for future plans. This is a different implementation from the
unrestricted JAX replay above: it falls back on numerical risk and recomputes
candidate contenders with native NumPy before native table construction.
SNID-SAGE continues to use its native vectorized FFT implementation; no SAGE
JAX speed claim is made.

The numerical guards cover determinant conditioning, coefficient cancellation,
near-perfect residuals, extreme inputs and zero/tiny errors. Candidates within
`1e-6 * abs(cutoff) + 1e-10` of the current cutoff are rechecked, including all
ties, until the selected set is stable. This margin is deliberately wider than
the earlier `rtol=1e-9`, `atol=1e-10` fixture criteria. Unknown NGSF source
hashes retain the native core. Missing/unsupported JAX uses NumPy; a JAX runtime
exception records its reason and switches the rest of the fit to NumPy.

All eight synthetic numerical stress cases now agree exactly, including the
two previously failing nearly singular cases. On the 20 saved real fixtures,
all six output arrays satisfy the earlier numerical criteria and the selected
top-ten numerical values are bit-for-bit native. Evidence:
`results/ngsf_guarded_replay_20261104/results.json`. Tests also exercise backend
identity separation, missing/runtime-failing JAX, source-version fallback,
near-tie reordering and preservation of virtualenv Python symlinks.

The bounded real-engine experiment in `results/ngsf_backend_integration_20261104/`
uses a new frozen runtime, the same five copied spectra, one nice-15 worker and
single-thread numerical settings. Fifteen fixed-z fits rotate the order of
`native`, `numpy`, and `jax` across spectra. Five additional JAX full free-z
fits compare to copied, verified historical native references. Each fit has a
1,800-second timeout and dispatch requires 8 GiB raw free disk. No active
campaign, external engine source, template bank or shared environment is edited.

The ten fixed-z comparisons to native are exact for statuses, candidates,
native CSVs, fit curves, masks and staged inputs. Their recorded attempt totals
are 148.67 s native, 153.28 s NumPy and 135.17 s guarded JAX. The JAX total is
13.50 s lower (9.08% less time, a 1.100× ratio); the median per-spectrum ratio
is 1.078×. This is one rotated timing pair per spectrum under changing shared
load, not a controlled throughput estimate. A NumPy attempt took 46.63 s while
the same spectrum's native/JAX attempts took about 29 s, illustrating that
startup/load variation can dominate these short fits. Recorded attempt time
includes startup and runtime verification but excludes planning/final hashing.

All five full free-z fits also agree exactly with verified native references
for statuses, candidates, native CSVs, curves, masks, staged inputs and redshift
grid records. Every fit executed 101 redshifts × 41 extinction values: **20,705
JAX grid calls** in total, with no backend-level fallback. Risky/candidate SN
columns were rechecked against every host using native NumPy. No template or
search-grid pruning was introduced. The five JAX times were 275.60, 249.41,
248.38, 249.29 and 254.08 s. Historical native references establish equivalence,
not a paired free-z speedup. `complete.json` records all 15 comparisons.

The frozen integration runtime precedes a metadata-only correction that marks
`native_candidate_rechecks` true only when JAX is loaded, plus rejection of
unsupported backend names; the tested arithmetic is unchanged. The final core
suite passes **149 tests**, with 11 optional skips and one existing dependency
deprecation warning. All **21 backend/kernel tests** pass in the isolated JAX
environment. CLI-generated defaults and the normalized example config agree.

These checks cover five spectra, one native source hash, CPU float64 and the
recorded library versions. They do not establish universal numerical equivalence,
calibrated classification accuracy, GPU behavior or a guaranteed speedup.

## SNID-SAGE FFT decision (2026-11-04)

`results/sage_fft_five_20261104_v2/` contains ten new fixed-z fits on the same
five copied spectra, alternating native and experimental JAX complex128 FFT
order. A frozen subprocess-only hook replaces the three cross-power/filter/
inverse-FFT assignments in SNID-SAGE 1.2.3's vectorized correlator. Template
selection, preprocessing, peak finding, redshift logic, thresholds, clustering
and output construction remain native. The hook verifies the integration
source hash; it does not edit installed SAGE or its template bank. The bound
is one nice-15 worker, 600 seconds per fit, and an 8 GiB raw disk reserve.

All five comparisons preserve status and parsed candidates exactly; full
candidate JSON, fit curves, masks and staged spectra are byte-identical.
However, JAX **does not improve this workload**:

| Stage, total for five fits | Native FFT | Experimental JAX FFT |
| --- | ---: | ---: |
| Complete recorded attempts | 133.139 s | 138.081 s |
| Correlation FFT calls, including first-shape compilation | 0.269 s | 2.039 s |
| Backend initialization/import | <0.001 s | 1.333 s |

Each side ran 95 correlation calls. Native FFT arithmetic accounts for about
0.20% of its complete attempt time. The observed full-fit difference is 4.94 s
(3.71% more time with JAX). These are one alternating observation per spectrum
under shared load; they establish no general slowdown factor. They provide no
reason to promote this JAX substitution as a time-saving default. **Production
SAGE remains native**; the experimental hook is confined to the benchmark
script. Free-z SAGE, persistent-process JIT reuse and GPU FFTs are untested.
Profiling initialization, template loading and downstream analysis is a better
next step than substituting this small FFT stage.

The initial preparation directory without `_v2` is retained but was never run:
it imported the main checkout through the editable installation. Preparation
now rejects a source checkout mismatch before creating an experiment. The
corrected trial explicitly freezes this worktree's source.

The final isolation audit in `results/backend_audit_20261104/isolation.json`
verifies all 30 new attempts and five native references, original/copied input
hashes, frozen experiment files, unchanged engine source, and the same live
SLSN PID, controller and plan. JAX remains absent from the shared conda
environment. The package wheel includes the guarded module and pinned JAX extra;
no package installation or campaign restart was performed.

## GitHub CI and housekeeping verification (2026-11-04)

The [first real CI run](https://github.com/sPaMFouR/spectypus/actions/runs/41868058808)
tested commit `dad5e50` on Python 3.10/Linux. Its actual step logs report
**167 passed, one skipped** (optional plot-style dependencies) and **72.1% line
coverage** for `spectypus`. Both source distribution and wheel built successfully;
the wheel imported from a fresh virtualenv's `site-packages` outside the checkout
and its CLI help ran. The unit suite includes synthetic JAX checks, not access
to real external template banks. Coverage includes unexercised bridge paths;
it is not a classification-accuracy measure.

The publisher generated build/test/coverage SVGs from this run's JUnit and
coverage reports and committed them as `c515d34`. All three SVGs identify the
tested SHA and Actions run. No public metrics resource or extra secret was
created. Missing/malformed/failed/all-skipped reports, nested-suite counting
and SVG escaping/provenance have dedicated regression checks. Badge-only
failures are isolated from the test job's real result.

Local housekeeping checks passed 157 tests with 11 optional dependency skips.
All local Markdown file links and heading anchors were checked; two references
to ignored historical products are now explicitly labelled local evidence.
Only disposable build/pytest/bytecode caches in the isolated worktree were
removed. The six established content folders remain, plus `.github/` for CI;
all scientific products remain under ignored `results/`. Benchmarks, frozen
attempts, active campaigns, environments and the main checkout's six pre-existing
edits were preserved. Detailed audit/log/report copies are saved under
`results/housekeeping_20261104/`.
