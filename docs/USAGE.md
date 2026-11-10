# Using Spectypus

This guide covers setup, a first batch, and how to interpret its results.
The [README](../README.md) provides the quick start.

Reporting currently uses the source-checkout exporters documented in
[RESULTS_VIEWER.md](RESULTS_VIEWER.md). The next packaging step will expose two
display modes: **SpectralAtlas** for large samples and **Classification Report**
for a night's folder or small batch of spectra. Both will read the same saved
typing evidence. These packaged display selectors are planned, not current CLI
options; acceptance criteria live in the [roadmap](roadmap/SPECTYPUS_ROADMAP.md).

## Install

From the cloned repository on macOS or Linux:

```bash
conda env create -f environment.yml
conda activate spectypus
spectypus init --config spectypus.local.json
python -c 'import sys; print(sys.executable)'
```

The environment includes Python 3.10, SNID-SAGE 1.2.3, JAX and the viewer.
Supply NGSF (the `run.py PARAMETERS.json` interface) and both template banks
separately. Set these fields in `spectypus.local.json`:

| Field | Value |
| --- | --- |
| Each engine's `python` | Interpreter path printed above |
| `engines.snid_sage.templates` | SNID-SAGE template directory |
| `engines.ngsf.root` | NGSF source directory |
| `engines.ngsf.parameters` | NGSF parameter JSON with your template paths |
| `free_redshift` | Scientifically appropriate `min`, `max`, `step`; 0–1 is only an example |

Both engines are enabled by default; set an engine's `enabled` to `false` to
exclude it. Paths resolve relative to the configuration file. Check setup with:

```bash
spectypus doctor --config spectypus.local.json
```

If already configured, activate the environment and skip `init`, which refuses
to overwrite files. Keep environments serving active fits unchanged; prepare
updates in a separate environment. Dependencies live in [environment.yml](../environment.yml)
and [pyproject.toml](../pyproject.toml); other engine versions need verification.

## Inputs and a first batch

For reduced spectra arranged as `reduced/object/spectrum.dat`:

```bash
spectypus manifest reduced --layout object --frame observer --unit angstrom --output manifest.csv
```

Use `--layout batch-object` for `reduced/batch/object/spectrum.dat`. The scanner
accepts `.txt`, `.dat`, `.ascii`, and `.csv` files and uses each object directory
as the exact object ID. Inspect the table before fitting, particularly its
identities, units and frame. It refuses to overwrite an existing table.

A manually prepared CSV needs `spectrum_id,object_id,path,wavelength_frame,wavelength_unit`.
Spectrum IDs must be unique; resolve object aliases yourself. Paths are relative
to the CSV or absolute. Optional columns include `redshift`, `redshift_source`,
`batch`, `mjd`, `phase_rest_days`, and `instrument`; extra metadata is retained.
See the [example manifest](../examples/manifest.example.csv).

Add known redshifts and their sources to the manifest, or supply a
[targets CSV](../examples/targets.example.csv) using `--targets targets.csv`
on **both** `plan` and `run`. Blank redshifts remain unknown; zero is valid.

```bash
spectypus plan --manifest manifest.csv --config spectypus.local.json --output results/run1
spectypus run --manifest manifest.csv --config spectypus.local.json --output results/run1 --max-runs 2
spectypus run --manifest manifest.csv --config spectypus.local.json --output results/run1
spectypus review --output results/run1
```

`plan` checks inputs and provenance without fitting. `--max-runs 2` limits new
engine attempts, not objects; inspect those fits before running the full batch.
The viewer is served at **http://127.0.0.1:8013** and reads verified saved evidence.
Use `spectypus summarize --output results/run1` to rebuild summaries without fitting.

## Redshift and input conventions

- `redshift_mode: "auto"` fixes known redshifts and searches for unknown ones.
  `"both"` adds diagnostic free fits for known-redshift spectra; only fixed fits
  contribute to their support. `"free"` searches all; `"fixed"` blocks unknowns.
- A known redshift propagates across the same object. Conflicting redshifts,
  duplicate spectrum IDs and repeated target IDs are errors. Sources are retained.
- Units must be `angstrom` or `nm`; frames must be `observer` or `rest`.
  Rest-frame input requires a known redshift and is multiplied by `1+z` once
  in a staged copy. Original files are preserved.
- ASCII columns 1 and 2 are wavelength and flux. Blank/comment lines and a
  `wavelength flux` or `wave flux` header are allowed. Wavelengths must be positive
  and unique; sorting is recorded. Nonfinite/invalid samples block the spectrum.
  Negative flux is preserved; extra columns, including uncertainties, are ignored
  and recorded as such. Engines use their native noise models.
- Flux values remain unchanged: no flux-density Jacobian, calibration, extinction
  correction, or air/vacuum conversion is applied. Prepare compatible inputs.
- SNID-SAGE requires at least 2000 Å overlap within 2500–10000 Å and redshift
  at most 1. Searches extending above 1 are blocked for SAGE; NGSF remains eligible.
  NGSF uses `min/max/step`; SAGE uses `min/max` with its own search algorithm.
  NGSF's effective grid and floating-point step adjustments are recorded.

## Outputs and score meaning

| Product | Contents |
| --- | --- |
| `matches.csv` | Top native candidates per engine/mode; ten by default |
| `spectra.csv`, `objects.csv` | Spectrum and object support, coverage and completeness |
| `run_status.csv` | Completed, no-good-match, failed, pending and blocked attempts |
| `summary.json` | Structured evidence, denominators and run counts |
| `plan.json`, `plan.csv`, `plans/` | Current/archived plan identities, inputs and provenance |
| `attempts/` | Staged inputs, parameters, logs, native results and checksums |

SNID-SAGE ranks **descending `hsigma_lap_ccc`**; NGSF ranks **ascending finite,
nonnegative `CHI2/dof2`**. Neither is SNID RLAP. Native scores, class labels,
subtypes, phases and redshifts are retained, not averaged between engines.
NGSF classes come from native template keys; SAGE captures post-gating `all_matches`.

Combined support uses `equal-engine-winner-per-unique-spectrum/1`:

1. Each engine's primary mode gives one vote to its best qualified normalized
   class; exact ties split the vote across distinct classes, not templates.
   SAGE requires success and threshold passage. NGSF has no calibrated acceptance
   threshold: its vote means best available match. Unknown class labels abstain.
2. Divide by **all requested engines**, including failures and abstentions;
   average over **all distinct spectra**, including unclassified ones. Missing
   evidence remains explicit; support can total less than one.
3. Identical staged numerical spectra within an object count once, retaining
   duplicate links. Identical spectra across different objects block those inputs.
   Numerically different reductions of the same exposure need manual curation.

`proposed` means one class has support; `contested`, multiple classes;
`ambiguous`, a tied lead; `unclassified`, no support. `complete` separately
indicates terminal primary attempts, so a complete batch can remain unclassified.
The [taxonomy](../src/spectypus/taxonomy.py) preserves native labels while mapping
known classes conservatively. **Support is dimensionless, uncalibrated evidence,
not a probability.** Template imbalance and correlated errors remain limitations;
classification accuracy awaits independent evaluation. See [validation](VALIDATION.md).

## Resume and troubleshooting

Rerun the same `run` command to reuse verified terminal attempts and retry failed
or interrupted ones. Inputs, configuration, source, runtime and template hashes
identify attempts. Changes create new identities; earlier attempts stay on disk.
Runtime/source/bank drift is checked before and after fits; a detected change
fails that attempt. Summaries use only the current plan and verified artifacts.

| Problem | Action |
| --- | --- |
| Engine unavailable | Run `doctor`; check interpreter, source and template paths, then inspect attempt logs |
| Input blocked | Check frame, units, redshift, IDs and numeric samples |
| No good match | Inspect native results; this differs from an engine failure |
| Batch still pending | Resume; inspect `all_runs_terminal` and `complete`, not only the exit code |
| Viewer dependencies missing | In an inactive environment, run `python -m pip install -e '.[web]'` from the checkout |

Exit codes: 0 successful invocation (including limited runs), 1 run failures or
nonduplicate input blocks, 2 invalid command/configuration/input, 130 interrupted.
The CLI runs serially with private attempt workspaces and a single-writer lock.
For bounded parallel campaigns, see [operation notes](OVERNIGHT.md).

## Fitting backends

NGSF defaults to guarded float64 CPU `jax`; `numpy` and `native` are alternatives.
Only the tested NGSF source is accelerated; other versions use native execution.
Unavailable/unsupported JAX or JAX runtime exceptions fall back to NumPy, recorded
in `backend.json`. Native rechecks protect unstable mixtures and candidate ranking.
Backend changes create new attempts; frozen campaigns retain their configuration.
SNID-SAGE supports only `native`. See [backend experiments](BENCHMARKS.md) for details.

Optional `telluric_windows` are observer-frame Angstrom `[lower, upper]` pairs;
`save_fit_curves: true` saves native model curves for review. Both default off.
Host-line markers use supplied redshifts without masking lines. See the
[viewer guide](RESULTS_VIEWER.md), [Python API and CI](../CONTRIBUTING.md), or
`spectypus <command> --help` for further details.
