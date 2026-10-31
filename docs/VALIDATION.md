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
- There is **no results website or batch visualization command yet**. Current
  products are CSV/JSON, logs and native artifacts. Diagnostic plotting is
  disabled in the adapters; a uniform spectrum/template-overlay product is
  not yet generated. Existing review websites in the source SLSN project have
  not been packaged into Spectypus.

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

## Next falsifiable evaluation

The [roadmap](roadmap/SPECTYPUS_ROADMAP.md#p1--measure-classification-quality)
owns the evaluation protocol and implementation tasks. It requires independent
labels, object-disjoint splits, an explicit template-leakage policy, per-class
precision/recall and confusion, coverage/abstention, and failure denominators.
Until that experiment is performed, no accuracy percentage is defensible.
