# Spectypus usage and scientific contracts

Detailed reference for configuration, inputs, outputs and evidence handling.
For the short installation/run guide, see the [README](../README.md).

Spectypus runs reduced supernova spectra through SNID-SAGE and NGSF, retains
native ranked matches, and combines evidence across engines and distinct
spectra of each object. Version 0.1 is an exploratory classification pipeline.
Its combined scores are transparent **uncalibrated support**, not class
probabilities or secure scientific classifications.

For current capabilities and evidence, read [validation](VALIDATION.md).
The [roadmap](roadmap/SPECTYPUS_ROADMAP.md) tracks further results review,
campaign-scale execution, scientific evaluation and later CI/badges.
The [project index](PROJECT_INDEX.md) routes development documentation.
The local results viewer is described in [RESULTS_VIEWER.md](RESULTS_VIEWER.md).

## Install

Python **3.10 or newer** is required. The package core has no third-party runtime
dependencies. Classifier interpreters are configured explicitly. The optional
`engines` extra installs the tested SAGE version and scientific dependencies
needed by both adapters; it does not download template banks or the NGSF
checkout. The maintained development environment is **`spectypus`**:

```bash
conda env create -f environment.yml
conda activate spectypus
spectypus --help
spectypus init --config spectypus.local.json
```

Run creation from this project directory. If the environment already exists,
activate it and use `python -m pip install -e '.[dev,engines,jax]'` to update the
local package. Skip `init` when a configured local JSON already exists: it
deliberately refuses to overwrite one. Find the active interpreter with
`python -c 'import sys; print(sys.executable)'` and use it for **both** engine
`python` fields when running everything in the dedicated environment.

Edit the JSON with the interpreter and template paths for SNID-SAGE,
and the interpreter, checkout and parameter-template paths for NGSF. Configure
the scientifically appropriate free-redshift search interval explicitly; the
example 0–1 interval is a starting configuration, not a universal prior.
Editable schema templates are also provided in [examples/](../examples/).

```bash
spectypus doctor --config spectypus.local.json
```

`environment.yml` chooses Python 3.10 for the tested engine stack; the core
package floor remains Python >=3.10. Engine requirements are declared in
`pyproject.toml` under `engines`. The conda recipe additionally pins the same
NumPy/SciPy versions so their native conda binaries are installed before pip;
the pip SciPy wheel failed to load on the tested macOS host. Keep these shared
pins consistent. The recipe is not a cross-platform complete
lockfile; local resolved inventories accompany validation under `results/`.
The previous `.venv` is retained, but new development uses conda. A minimal
core-only environment can still install `python -m pip install -e '.[dev]'`
and point the adapters at an external classifier environment.

The adapters target SNID-SAGE 1.2.3's candidate API and the legacy NGSF
`run.py PARAMETERS.json` interface. Other versions require verification.
Execution and file locks currently target macOS/Linux (POSIX), not Windows.

## Fitting backends

`engines.ngsf.backend` accepts `jax` (default for future plans), `numpy`, and
`native`. `native` retains the external engine's arithmetic. `numpy` reuses
normal-equation reductions and computes eight SN templates at a time without
changing the summation order. `jax` uses the tested float64 CPU kernel, then
recomputes ill-conditioned/cancellation-sensitive mixtures, near-perfect fits,
and candidate contenders with native NumPy. Contenders within a conservative
score margin are rechecked until the selected set is stable. Native table
construction, sorting, interpolation, full search grids and masks are retained.

Only the tested NGSF source hash is accelerated. Other versions use native
execution and record the reason. Missing/unsupported JAX falls back to NumPy;
JAX runtime exceptions are recorded and switch the remainder of that fit to
NumPy. These numerical/backend fallbacks do not convert an engine failure into
a successful match. The normal engine result parsing and error handling apply.

Every attempt saves `backend.json`. The configured backend, interpreter,
installed package versions and Spectypus source participate in execution
identity, so backend changes create new attempts. Existing saved attempts and
campaigns with frozen runtimes retain their original behavior. SAGE currently
accepts only `engines.snid_sage.backend: "native"`, its vectorized FFT path.

Fresh environments created from `environment.yml` include the `jax` extra.
Do not install into an interpreter serving a live campaign: changing its
packages invalidates its frozen provenance. To prepare an isolated engine
environment while using the existing conda NumPy/SciPy binaries:

```bash
conda activate spectypus
python -m venv --system-site-packages .venv-future
.venv-future/bin/python -m pip install -e '.[jax]'
.venv-future/bin/python -c 'import sys; print(sys.executable)'
```

Set the NGSF `python` field to that printed path for future plans. Python
symlinks are preserved so the venv remains effective. The overlay reads shared
packages; retain the base environment unchanged until its campaigns complete.
Use a new independent conda environment instead if the base must change.

The README's complete-fit timing applies to the guarded backend. The older
arithmetic microbenchmarks below measure a different, unrestricted prototype;
their 5.78× ratio is not a future campaign speed estimate.

### Reproduce the bounded backend checks

With the five-spectrum reference experiment and isolated JAX interpreter
already prepared using the benchmark instructions below, create a **new**
output directory. The preparation command must import this checkout's source:

```bash
conda activate spectypus
PYTHONPATH="$PWD/src" python scripts/benchmarks/validate_ngsf_backend.py prepare \
  --reference results/ngsf_free_five_20261103 \
  --output results/ngsf_backend_check --python "$PWD/.venv/bin/python"
PYTHONPATH="$PWD/results/ngsf_backend_check/runtime" nice -n 15 python \
  results/ngsf_backend_check/run_experiment.py run results/ngsf_backend_check
python scripts/benchmarks/report_ngsf_backend.py results/ngsf_backend_check \
  --output results/ngsf_backend_check/report
```

This freezes the runtime and input copies, runs at most 20 fits with one worker
(15 fixed-z native/NumPy/JAX fits and five full free-z JAX fits), and verifies
native candidates and scientific artifacts. Each fit has a 1,800-second timeout;
dispatch stops below 8 GiB raw free disk. Completed experiments cannot be
overwritten. Free-z references are historical, so their timing is not paired.

`scripts/benchmarks/benchmark_sage_fft.py` separately compares native and JAX
complex128 FFTs in ten fixed-z fits on the same five spectra. Its `prepare`
command accepts `--reference`, `--output`, `--python`, and `--templates`; use the
same frozen-runtime launch pattern. The hook is confined to this experiment
and is **not an available production SAGE backend**. It records FFT-stage and
whole-attempt times separately, preserving evidence for the backend decision.
Use its `report ROOT --output ROOT/report` command to generate the comparison.

## Inputs and a first batch

Provide a CSV with these required columns:

```csv
spectrum_id,object_id,path,wavelength_frame,wavelength_unit,redshift,redshift_source,batch,mjd,instrument
SN-example-epoch1,SN-example,spectra/epoch1.dat,observer,angstrom,0.1,host_catalog,batch1,60000,instrument
SN-example-epoch2,SN-example,spectra/epoch2.dat,observer,angstrom,,,batch2,60005,instrument
SN-unknown-epoch1,SN-unknown,spectra/unknown.dat,observer,angstrom,,,batch2,60007,instrument
```

Paths are relative to the manifest file, or absolute. `spectrum_id` must be
unique. `object_id` is an exact physical-event identity supplied by you: aliases
must already be resolved. Object identity is never inferred from a filename.
Other CSV columns are preserved in the frozen plan; useful optional columns
include `phase_rest_days`, `mjd`, `instrument`, and `batch`.

For a directory organized as `root/object/spectrum.dat`, generate a draft:

```bash
spectypus manifest /path/to/reduced --layout object --frame observer --unit angstrom --output manifest.csv
```

Use `--layout batch-object` for `root/batch/object/spectrum.dat`. The object
directory is the exact object ID; the relative file path is the spectrum ID.
Inspect the generated manifest before fitting, especially mixed-frame batches.
The scanner supports `.txt`, `.dat`, `.ascii`, and `.csv` numeric files and
rejects files inconsistent with the declared directory depth. It never
overwrites an existing manifest.

An optional targets CSV provides externally measured redshifts:

```csv
object_id,redshift,redshift_source
SN-example,0.1,host_catalog
```

```bash
spectypus plan --manifest manifest.csv --targets targets.csv --config spectypus.local.json --output results/run1
spectypus run --manifest manifest.csv --targets targets.csv --config spectypus.local.json --output results/run1 --max-runs 2
spectypus run --manifest manifest.csv --targets targets.csv --config spectypus.local.json --output results/run1
spectypus summarize --output results/run1
```

`plan` inspects spectra and engine provenance without fitting. `run` retries
failed/unverified attempts and reuses verified terminal attempts. `--max-runs`
limits newly launched engine attempts, not objects. Partial summaries retain
pending spectra and requested engines. `summarize` verifies saved evidence and
rebuilds tables for the current frozen plan without launching classifiers.

## Redshift and input conventions

- Default `redshift_mode: "auto"`: fixed redshift when known, free otherwise.
  A missing target-table entry is a free-redshift object. Redshift zero is valid.
- `"both"` fits known-redshift spectra in fixed and free modes. Fixed results
  contribute to combined support; free fits remain diagnostic. Unknown-redshift
  spectra receive one free fit. `"free"` uses free fits for all spectra;
  `"fixed"` blocks spectra lacking redshift.
- A known redshift propagates to every spectrum of the same exact object.
  Conflicting measurements, duplicate spectrum IDs and duplicate target IDs
  are errors, not silent last-row-wins overrides.
- Supported wavelength units are `angstrom` and `nm`; frames are `observer`
  and `rest`. Rest wavelengths are multiplied by `1+z` once, in a private staged
  copy. Rest-frame input without known redshift is blocked.
- ASCII first/second columns are wavelength and flux. Blank/comment lines and
  an explicit `wavelength flux` or `wave flux` header are allowed. Invalid or
  nonfinite samples block the spectrum. Wavelengths must be positive and unique;
  sorting is recorded. Negative flux is preserved. Additional columns are
  recorded as ignored: the engines use their native noise models, not supplied
  per-pixel uncertainties. No uncertainty or missing flux is fabricated.
- Staging retains flux shape in its original units. It does not perform a
  physical flux-density transformation, extinction correction, flux calibration,
  or air/vacuum conversion. These conventions must already be appropriate for
  the input and template comparisons. SAGE v0.1 uses the optical profile and
  requires at least 2000 Angstrom overlap within 2500–10000 Angstrom.
  This profile is limited to redshifts at or below 1.0: fixed fits above 1.0
  and free searches extending above 1.0 are explicitly blocked for SAGE.
  NGSF remains eligible. An unsupported SAGE search is never recorded as
  evidence that no good match exists. ONIR support needs separate validation.

NGSF's free-redshift grid uses the configured min/max/step; SAGE uses min/max
with its native search algorithm (the NGSF step does not change SAGE's grid).
NGSF's effective grid is recorded, including any floating-point step adjustment
needed to preserve the requested number of grid points.

## Outputs and score meaning

Every output directory contains:

| Product | Contents |
| --- | --- |
| `plan.json`, `plan.csv`, `plans/` | Current and archived immutable plan identities, inputs, config, provenance and blocked reasons |
| `matches.csv` | Top `top_n` (default ten) native candidates per current engine/mode attempt |
| `run_status.csv` | Completed, no-good-match, failed, pending and blocked attempts |
| `spectra.csv` | Individual-spectrum support, engine coverage and diagnostic fits |
| `objects.csv` | Combined object support, duplicate counts and completeness |
| `summary.json` | Structured spectrum/object evidence, denominators and run counts |
| `attempts/<identity>/<trial>/` | Staged spectrum, parameters, logs, native outputs, normalized candidates and checksums |

SNID-SAGE candidates rank by **descending `hsigma_lap_ccc`**. NGSF candidates rank
by **ascending finite, nonnegative `CHI2/dof2`**. These scores are not averaged
or converted to one another. Neither is called SNID RLAP. Native fields remain
available in each candidate's `native` record and the native output files.
NGSF template classes come from its native `<type>/<object>/...` keys, not a
guess from the object name. Native subtype/phase/redshift values remain intact.
SAGE's capture covers its post-gating `all_matches`, not every attempted template.

The combined rule is versioned `equal-engine-winner-per-unique-spectrum/1`:

1. Select the primary redshift mode for each spectrum and engine.
2. A successful engine contributes one vote to its best qualified normalized
   class. Equal best native scores split that vote across distinct tied classes.
   Repeated templates or epochs of the same class never multiply the vote.
   SAGE must report classification success and threshold passage. NGSF has no
   calibrated acceptance threshold; its vote means only best available match.
   Unknown best-class labels cause abstention rather than a fallback winner.
3. Divide votes by the **number of requested engines**, including abstentions,
   failures and missing results. Then average over **all distinct spectra** of
   the object, including spectra that could not be classified. Total support
   can be less than one; the remainder is explicit abstention mass.
4. Identical staged numerical spectra within one object contribute once; every
   source row and duplicate link remains visible. Identical spectra assigned to
   different objects block those inputs as an identity conflict.

`proposed` means one class has support, `contested` means another class also
has support, `ambiguous` means the leading support is tied, and `unclassified`
means no class has support. `complete` independently reports whether all
primary attempts reached a terminal state. A complete no-good-match outcome
is still unclassified. Repeated reductions that differ numerically are not
automatically recognized as the same exposure; curate such duplicates in the
input manifest before interpreting epoch counts.

The explicit mapping in `spectypus/taxonomy.py` harmonizes common engine labels
(e.g. Ia-norm → Ia), retaining native labels. It is intentionally conservative:
unknown labels abstain. Source codes and all template files are fingerprinted,
but template-bank composition and correlated errors across epochs/engines
remain scientific limitations. These support fractions are **not probabilities**.

## Reproducibility and safety of reruns

Attempt identities bind the spectrum and staging metadata, configuration,
external engine Python/runtime packages, engine source and bank hashes, and
Spectypus source hash. Resume verifies the attempt record and all recorded
artifacts; tampered or interrupted results are not reused. Each retry gets a
new directory, retaining earlier evidence. Summaries only use the current plan.
Configuration/input changes create new identities; old attempts stay on disk.
Engine source, bank, runtime and Spectypus source fingerprints are checked again
immediately before and after every new fit. Drift fails that attempt with no
classification support; the observations and original plan provenance remain
recorded. This detects changes at the checks rather than creating an immutable
filesystem snapshot of external engines.

Classifiers execute serially with streamed logs and a configurable timeout.
Each has private parameters, staged input, output and cache directories. The
shared NGSF configuration and original spectra are never edited. A process
lock prevents simultaneous writers to the same output directory. Exit codes:
0 successful invocation (possibly deliberately limited), 1 run failures or
nonduplicate input blocks, 2 invalid configuration/input command, 130 interrupted.
Inspect `all_runs_terminal` and `complete` before treating a batch as finished.

## Python API and development

```python
from pathlib import Path
from spectypus import make_plan, run_batch, summarize_output

plan = make_plan(Path("manifest.csv"), Path("spectypus.local.json"))
summary = run_batch(Path("manifest.csv"), Path("spectypus.local.json"),
                    Path("results/run1"), max_runs=2)
summary = summarize_output(Path("results/run1"))
```

The `config` argument also accepts a configuration dictionary. It is validated
and copied before planning; relative paths in dictionaries resolve against the
current working directory. File-based configuration paths resolve relative to
the configuration file instead.

```bash
conda activate spectypus
python -m pytest -q
python -m build
```

The package is standalone. Its adapters derive from the existing SLSN
classification workflow in `_ProjectG_VolumetricRatesSLSNe`, but do not import
that project at runtime. Automated tests use temporary synthetic spectra and
controlled subprocesses; these validate software behavior, not scientific
classification accuracy. Local real-engine smoke results, when available,
are kept under ignored `results/` directories.

Deferred work: line/host-based redshift inference, spectrum reduction, FITS
readers, classification calibration on held-out objects, treatment of correlated
epochs and template-bank imbalance, and a review UI. No PyPI publication or
GitHub push is performed by local installation.


## Telluric masks, model curves and overnight priority

Set `telluric_windows` to a list of observer-frame Angstrom `[lower, upper]`
pairs, and `save_fit_curves: true` to retain native model curves for review.
Both default to disabled for existing configurations. `redshift_mode: "both"`
runs fixed and free fits for known-z targets, and free fits for unknown-z targets.
Host-line markers use supplied redshifts and do not mask the lines. See
[OVERNIGHT.md](OVERNIGHT.md) for the current protocol and restart instructions.

## Isolated NGSF optimization experiments

The scripts in `scripts/benchmarks/` are opt-in experiments, outside the installed
pipeline. Use a separate Git worktree while campaigns are active. They read the
external NGSF checkout and bank, and install trial functions only inside each
benchmark subprocess. They never update a campaign's controller or saved fits.

Prepare five copied spectra from the existing SLSN campaign. Selection uses
input-length quantiles among eligible unique Chen spectra with known redshifts;
frame metadata, redshift provenance and input hashes are retained. Choose a new
output directory for each experiment:

```bash
conda activate spectypus
PYTHONPATH=src python scripts/benchmarks/benchmark_ngsf.py prepare \
  --campaign /path/to/original/results/slsn_ztf_overnight_20261031 \
  --output results/ngsf_cache_trial
PYTHONPATH=src /usr/sbin/taskpolicy -b nice -n 15 python \
  results/ngsf_cache_trial/experiment/benchmark_ngsf.py \
  run results/ngsf_cache_trial --mode fixed
PYTHONPATH=src /usr/sbin/taskpolicy -b nice -n 15 python \
  scripts/benchmarks/benchmark_core_reuse.py \
  --reference results/ngsf_cache_trial --output results/ngsf_core_trial
```

`taskpolicy -b` is macOS-specific; on Linux omit it and retain `nice -n 15`.
Both runners use one worker and one numerical-library thread. The first runs
15 fits: native, error-array cache, and error plus galaxy-interpolation caches
for five spectra, with rotated stage ordering. The second runs five additional
fits with repeated native reductions and residuals reused. Fixed-z tests retain
the full native extinction grid, template selection, masks and curve capture.
Each fit has a 900-second timeout. The experiment stops dispatch below 8 GiB raw
free space or above 512 MiB of experiment files; this small bounded experiment's
reserve does not change the production campaign's 20 GiB guard.

Each experiment saves its contract, copied inputs/configuration, code snapshots,
distinct stage plans, verified attempts, inclusive component timings and exact
candidate/artifact comparisons. Re-invocation verifies completed attempts;
incomplete evidence requires a new output directory. Concurrent campaigns and
background scheduling confound wall-clock comparisons. See [VALIDATION.md](VALIDATION.md)
for measured outcomes and scope. Free-z trials are separately selectable in the
first runner, but fixed-z results do not establish free-z speed or equivalence.

Stage 3 also saves the masked numerical arrays at `A_v=0`. A paired replay can
compare the original and optimized arithmetic on those identical arrays, using
five alternating-order measured pairs per spectrum after one warm-up pair:

```bash
PYTHONPATH=src /usr/sbin/taskpolicy -b nice -n 15 python \
  scripts/benchmarks/replay_ngsf_core.py results/ngsf_core_trial \
  --output results/ngsf_core_trial/paired_replay.json
PYTHONPATH=src python scripts/benchmarks/report_ngsf.py \
  --cache-root results/ngsf_cache_trial --core-root results/ngsf_core_trial \
  --paired results/ngsf_core_trial/paired_replay.json \
  --output results/ngsf_core_trial/report
```

The replay verifies each saved attempt and compares every native table column
and returned score exactly. It excludes interpolation, error estimation,
template loading and disk I/O; its speed ratio is specific to arithmetic at
those five grid points. It is not an end-to-end or free-redshift speed claim.

### Full free-redshift check

The separate free-z runner copies verified historical native results for the
same five spectra and compares five new intermediate-reuse fits against them.
It retains all 101 redshifts (`0..1`, step `0.01`) and 41 extinction values,
giving 4,141 grid points per spectrum. The frozen package path is required:

```bash
conda activate spectypus
PYTHONPATH="$PWD/src" python scripts/benchmarks/benchmark_free_redshift.py prepare \
  --campaign /path/to/original/results/slsn_ztf_overnight_20261031 \
  --output results/ngsf_free_trial
PYTHONPATH="$PWD/results/ngsf_free_trial/runtime" nice -n 15 python \
  results/ngsf_free_trial/experiment/benchmark_free_redshift.py \
  run results/ngsf_free_trial --max-new-runs 5
```

This trial permits at most five fresh attempts, one worker, one numerical
thread, and 2,400 seconds per fit. It retains the benchmark's 8 GiB raw-free
reserve and 512 MiB output limit. Historical timings are unpaired and cannot
establish speedup. `--max-new-runs 1` allows a checkpoint after each fit; a later
invocation verifies and reuses completed attempts. It saves numerical arrays at
`A_v=0`, `z=0`, `0.5` and `1` without thinning the search. Source campaigns,
external engine/template assets and completed reference attempts are read-only.

### Isolated JAX arithmetic test

Create the optional overlay in the development worktree, using the existing
engine environment's NumPy/SciPy without installing JAX into that environment:

```bash
conda activate spectypus
python -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e '.[benchmark-jax]'
PYTHONPATH="$PWD/src" python scripts/benchmarks/benchmark_jax.py prepare \
  --fixed results/ngsf_core_trial --free results/ngsf_free_trial \
  --output results/jax_trial
PYTHONPATH="$PWD/src" nice -n 15 .venv/bin/python \
  results/jax_trial/experiment/benchmark_jax.py run results/jax_trial
PYTHONPATH="$PWD/src" python scripts/benchmarks/report_free_jax.py \
  --free-root results/ngsf_free_trial --jax-root results/jax_trial \
  --output results/jax_trial/report
```

Wait for the free-z worker to finish before the full JAX replay. The default
trial covers 20 saved grid-point fixtures (five fixed-z and 15 free-z), using
eight-template chunks, CPU-only JAX and five alternating-order timing pairs.
It records transfer and first-call costs separately, synchronizes device work,
and includes NumPy reuse with the same chunk size as a memory-locality control.
Both NumPy variants must agree bit-for-bit with the extracted native arithmetic.
The runner stops if measured warm CPU/wall exceeds 1.5. `NPROC=1`, disabled asynchronous
CPU dispatch and single-thread flags limit work; the measured guard checks
their effect. If it stops, retain that evidence and prepare a new trial with
smaller `--chunk-templates`; do not overwrite the stopped trial.

Float64 acceptance requires identical NaN/Inf masks, exact sample counts and
ordered top-ten template/host indices, and finite coefficients/scores within
`rtol=1e-9`, `atol=1e-10`. Float32 is a negative precision control. Synthetic
cases also check strict overlap boundaries, negative coefficients, singular
and nearly singular mixtures, and zero/tiny errors. The corrected prototype
passes the sample count as a runtime divisor to preserve native overlap
decisions; this does not make reduction ordering identical. A failed edge case
blocks overall numerical acceptance even when real fixtures pass.

This is arithmetic replay, not a JAX classifier or production configuration.
It excludes interpolation, template loading, native-table reconstruction and
whole-search ranking. The `benchmark-jax` extra pins the tested JAX release for
the project's Python 3.10 runtime; it does not promise other backends or GPUs.
