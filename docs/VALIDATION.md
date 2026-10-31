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
The original evidence is in [results/validation.json](../results/validation.json).
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
- Execution is serial within a batch. No thousand-spectrum throughput or
  memory claim has been measured.
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
[validation record](../results/conda_validation/validation.json), JUnit report,
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
