# Backend development and benchmark procedures

These optional procedures require separately prepared local spectra, engine
checkouts and template banks. They are not part of first-time setup. Use new
`results/` directories; retain completed evidence and keep active environments
unchanged. See [usage](USAGE.md) to run a batch and [validation](VALIDATION.md)
for measured outcomes and limitations. Historical reference paths below are
local artifacts, not files shipped with Spectypus.

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

The validated complete-fit timing applies to the guarded backend. The older
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
