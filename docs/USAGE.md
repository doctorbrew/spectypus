# Using Spectypus

This guide covers setup, a first batch, and how to interpret its results.
The [README](../README.md) provides the quick start.

Both `spectypus run` and `spectypus night` automatically write `index.html` in
the results folder: a continuous **Classification Report** with an inventory,
native match tables, fit statuses, Issues and an editable final night log.
It opens offline without a server or optional web/plot dependencies.
The source-checkout exporters in [RESULTS_VIEWER.md](RESULTS_VIEWER.md) also
provide **SpectralAtlas** navigation and reports embedding verified master JPGs.
Automatic reports include six-panel 300-dpi JPG grids when saved curves and the
plotting runtime are available. An installed atlas display selector remains
planned; see the [roadmap](roadmap/SPECTYPUS_ROADMAP.md).

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

## Nightly folder command

For a flat folder containing reduced science ASCII spectra:

```bash
conda activate spectypus
spectypus night /path/to/spectra
```

For EFOSpec, point to the **reduced nightly output**, not its raw `data/DATE`:

```bash
spectypus night /path/to/EFOSpec/runs/2026-10-28 \
  --output /path/to/EFOSpec/data/classifications/2026-10-28
```

Spectypus reads `nightly/current.json` and the selected reduction's `run.json`,
then uses only exported `role=science` products. It also recognizes the selected
revision, reduction or products directory directly. Standards, failed reductions,
archived and rescue revisions are not mixed into the selection. This supports the
version-1 `native_raw_calibration_daily_standards` export contract; unsupported or
provisional wavelength conventions fail explicitly. No EFOSpec imports or reductions
are executed. The source object name, MJD, air/topocentric wavelength convention,
reduction status and manifest hash are retained. A partial reduction remains a
partial source selection: successful typing does not recover its missing targets.

No per-night configuration or manifest is required. The command reuses engine
settings in this order: `--config PATH`, `SPECTYPUS_CONFIG`,
`spectypus.local.json` in the working directory, then
`~/.config/spectypus/config.json`. An explicit missing path is an error; it does
not silently fall back. For a new installation, run
`spectypus init --config ~/.config/spectypus/config.json` once and fill the engine
paths described under [Install](#install). Existing checkout settings already
work. Classifiers and template banks remain external; nothing is downloaded.

The nightly profile declares observer-frame Angstrom input, `redshift_mode: both`
and `save_fit_curves: true`, with 1800 seconds allowed per fit (`--timeout`). Other settings, including enabled engines and the
free-z grid, come from the installation configuration (the initial grid is
0–1 in steps of 0.01). Both engines are enabled in the example configuration.
These frame/unit defaults are a user-selected workflow convention, not inferred
metadata; override them for differently prepared spectra. Known redshifts receive
fixed/free fits; unknown redshifts receive free fits only.

For flat input, `.txt`, `.asci`, `.ascii` and `.dat` are selected without an extension
flag; hidden files and subdirectories are excluded. Keep standards, logs and alternate reductions out.
Filename stems serve as opaque object labels: `SN-A_001.txt` becomes `SN-A_001`,
not a guessed `SN-A` identity. Use the explicit-manifest workflow below to group
multiple epochs under one physical object or supply richer per-spectrum metadata.
Known z can be supplied with `--targets`: its `object_id` must match the full
filename stem for flat input or the saved object name for EFOSpec input.
Frame/unit provenance is recorded; absent metadata stays absent. EFOSpec's declared
observer/Angstrom conventions cannot be overridden with conflicting CLI values.

Nightly input defaults to `--nonfinite mask`: finite positive wavelengths are
required, but nonfinite **flux** rows are excluded from the private staged spectrum.
Every excluded line, flux token and wavelength is saved in `input_staging.json`.
Intervals at the original wavelength-cell midpoints are passed separately from
telluric masks to both engines: SAGE mask-aware rebinning/continuum fitting and
NGSF object/template grid exclusion. This prevents interpolated internal gaps
from entering the scored samples. No replacement flux or zero filling is written.
Finite negative flux is retained. Malformed rows, missing/nonpositive/nonfinite
wavelengths, duplicates and fewer than two usable samples still block the input.
Use `--nonfinite reject` for the original strict behavior. Explicit-manifest runs
remain strict unless a row declares `nonfinite_policy=mask`.

| Argument | Default / behavior |
| --- | --- |
| `--pattern GLOB` | Optional filter; default supported ASCII extensions or EFOSpec science selection |
| `--output PATH` | `FOLDER/spectypus`; cannot be the input folder itself |
| `--config PATH` | Select installation settings explicitly |
| `--targets CSV` | Optional `object_id,redshift,redshift_source` table |
| `--frame observer\|rest` | `observer`; rest requires a known z |
| `--unit angstrom\|nm` | `angstrom` |
| `--nonfinite mask\|reject` | `mask`; recorded nonfinite-flux exclusions and native wavelength masks |
| `--mode auto\|both\|free\|fixed` | `both`; overrides the installation redshift mode |
| `--z-min`, `--z-max`, `--z-step` | Override individual configured grid values |
| `--plan-only` | Write plan and input checks without fitting |
| `--max-runs N` | Limit new engine attempts, not spectra; repeat without it to finish |
| `--timeout SECONDS` | 1800 per attempt for nightly searches; overrides installation timeout |

Results use the standard CSVs, `summary.json` and `attempts/` described below.
An automatically generated, content-addressed manifest lives inside the output's
`.inputs/` directory; resolved configuration is already saved in the plan, so no
extra nightly configuration is written. Earlier selections and fit evidence are
retained. Repeating the command reuses verified completed attempts; changed inputs
or settings receive new execution identities. Original spectra are not rewritten.

Open `index.html` in the output folder. Both nightly and manifest-based batches
write it before fitting and refresh it after each attempt and on resume. A plan
or `--plan-only` produces a report with pending/blocked fits. Only verified current
attempts appear; retained trials do not enter current totals. Invalid evidence is
labelled explicitly and excluded from matches. Reports show the first six native
matches per fit (up to configured `top_n`); CSV/data downloads retain precise
saved values. The title is the common input batch/folder name, otherwise the
output folder name. Automatic summary priority and redshift provenance follow
the shared atlas contract; native scores from different engines are not compared.

Edit the final log and use **Save log** (JSON), **Download CSV**, or **Load log**.
Browser drafts are keyed to the exact spectra/fit records; files from a different
selection are rejected. Reviewer files remain separate from native evidence and
automatic summaries. Downloaded files go to the browser's selected destination.

To refresh an existing report without fitting, source inputs or engine installs:

```bash
spectypus summarize --output /path/to/results
```

Each engine/configuration with saved curves gets one six-panel master JPG,
embedded with enlargement and downloads. All JPGs are 300 dpi; no PDFs are
generated. Grids have three rows and two columns, 1000-Å major wavelength ticks,
22-pt axis labels, tick labels and rank text, with 19.8-pt legends. Rank text is
inset at 7% of the panel width. Legends sit above each panel; the matched name,
native type and phase stay on one line. Target legends show discovery
phase as `Name(+2.1d since discovery)`.
Flux labels use declared `flux_unit`
metadata (EFOSpec's physical-flux export contract supplies erg s⁻¹ cm⁻² Å⁻¹);
unspecified inputs say “input units” without assuming physical calibration.
New configurations save curves by default; explicit
`save_fit_curves=false` gives tables only. Install `spectypus[plots]` and LaTeX
for rendering (included in the updated conda recipe). `SPECTYPUS_PLOT_PYTHON`
optionally selects a separate plotting interpreter. Verified existing JPGs
can be reused without plotting dependencies. Native templates and engine Python
may be needed for the first display preparation; no classifier search is run.
Saved numerical requests are cached independently of figures, so metadata/style
updates do not replay preprocessing. Missing models remain explicitly unavailable.
The legacy `review` viewer still uses PDF/JPG; prefer this automatic report.

In the final night log, **Copy text** copies the current edited Name / Type / z /
Phase / Survey table for pasting into Slack or messages. Restricted offline
browsers offer selected text for manual copy. **Download CSV** exports those edits
as `night-log.csv` for spreadsheets. **Save log** saves a reloadable JSON file;
**Load log** restores that JSON for the same spectra/fits, not a CSV or new spectra.
These controls never alter native fit results.
Candidates that fail the acceptance checks are labelled **Bad match** in tables
and selectors; their saved `qualified` flags and automatic-summary rules remain unchanged.

Open `index.html` directly. In the final log, choose one configuration/rank
under **SNID-SAGE match** and/or **NGSF match** for each spectrum, then **Make plots**.
Each selector lists available ranks 1–6 across fixed/free-z fits, with the matched
name, native type and phase. Nothing is selected automatically; `None` skips that
tool. Each selection extracts a single-panel 300-dpi JPG from the existing embedded
master image, retaining its original plot pixels, legend, ticks, labels and units:
`PLOT_Classification_SNID-SAGE_<SNName>.jpg` or
`PLOT_Classification_NGSF_<SNName>.jpg`. Repeated object names receive a stable
spectrum suffix. In browsers with folder access, choose the folder containing
this report's `index.html` and allow saving. Other browsers prepare ordinary JPG
downloads, with links for individual saves; choose the report folder in the save
dialog. No server, terminal command or network access is needed for HTML export.
Folder access is browser-dependent; Chrome/Edge support the directory picker.

Direct folder saves record hashes/selections in `classification-plot-selections.json`
and protect edited or unrelated existing files. Changing a rank replaces the
tool/spectrum's prior managed export. Deselecting does not delete saved files.
Browser downloads follow the browser's normal naming/overwrite behavior.

**Save log / Load log** also retain these choices in JSON. CSV and copied text
remain the five-column classification table. For optional scripted export through
the Python renderer, a saved JSON log can also be used with:

```bash
spectypus plot-log --output /path/to/results --log /path/to/night-log.json
```

Neither path refits or replays preprocessing. Editing the classification table
does not relabel native template evidence. Old reports need one
`spectypus summarize --output /path/to/results` refresh: plotting dependencies
measure the existing master layout once and cache a small pixel map. Master JPGs
and numerical requests are reused; no collection of individual JPGs is generated
in advance. Subsequent cached refreshes require no plotting runtime.

### Discovery and host metadata

With `TNS_API_KEY`, `TNS_BOT_ID` and `TNS_BOT_NAME` configured in the environment,
`night` and `run` fetch discovery metadata once for exact TNS names. Responses
and hashes live under `metadata/`, separately from immutable fits. Credentials
are never saved there. Without credentials, existing metadata is used. To refresh:

```bash
spectypus summarize --output /path/to/results --refresh-tns
```

The name alone is the spectrum heading. Smaller lines give Discovery MJD and
Observed MJD to three decimals, phase as **observer-frame days since discovery**
(no time-dilation correction), a sourced host cross-match and a link to the
original spectrum. Exact dates remain in data/tooltips. The inventory's Phase
remains the native spectral-match phase; these have different reference epochs.
TNS object redshift is never implicitly used as host redshift or fit input.
API contract: [TNS Getting started](https://www.wis-tns.org/node/20752).

### EFOSpec typing metadata

Spectypus accepts an optional `typing-metadata.json` beside the selected
EFOSpec `reduction/run.json`. EFOSpec should generate and revision this file;
users need not author per-night inputs. The file, reduction and ASCII product
hashes must agree. Stale metadata is rejected. Minimal example:

```json
{
  "schema": "efospec-typing-metadata/1",
  "night": "2026-10-28",
  "reduction_manifest_sha256": "<SHA256 of run.json>",
  "spectra": [{
    "object_id": "AT2024afzf",
    "path": "products/tAT2024afzf_20261028_Gr13_Free_slit1.0_1_f.asci",
    "source_sha256": "<SHA256 of ASCII spectrum>",
    "host_name": "<reviewed galaxy name>",
    "host_redshift": 0.03,
    "host_status": "accepted",
    "host_source": "<catalogue record/reference>",
    "adopted_redshift": 0.03,
    "adopted_redshift_kind": "host_catalogue",
    "redshift_status": "accepted",
    "adopted_redshift_source": "<reviewed catalogue record/reference>"
  }]
}
```

Those values are placeholders, not a host identification for AT2024afzf. Optional
fields are `tns_name`, `discovery_mjd`, `discovery_source`, `discovery_survey`,
`instrument` and `spectrum_url` (a real repository/product URL). Without a URL the
filename links to the original local file. Keep catalogue candidates, separation,
method, uncertainty, reference frame and review identity/time in the same record;
the full record is retained in report provenance. Supported adopted-redshift kinds
are `host_catalogue`, `narrow_lines` and `transient_spectral`. Host adoption needs
an accepted host and identical host/adopted z; a nearest candidate alone is not
accepted. New typing runs use the accepted z for fixed/free fits. Report-only
refresh can show revised host metadata but never changes the z supplied to an
already completed fit. EFOSpec producer/editor implementation is still separate.

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
  and unique; sorting is recorded. Strict manifest input blocks nonfinite/invalid
  samples; the nightly mask policy above handles nonfinite flux explicitly.
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

## Installed offline displays (0.2)

Choose the presentation when typing or refreshing saved results:

```sh
spectypus summarize --output RESULTS --display report
spectypus summarize --output RESULTS --display atlas
spectypus night FOLDER --display atlas
```

Both choices write `RESULTS/index.html`. `report` (the default) is the continuous
Classification Report; `atlas` adds a searchable object sidebar and collapsible
epochs. `plan` and `run` accept the same option. Python callers use
`summarize_output(path, display="atlas")` or `run_batch(..., display="atlas")`.
Choosing a display does not change fit identity, native results, automatic
summary priority or saved reviewer-log identity. No server is needed.
The installed exporter handles one saved plan, including its objects/epochs;
the source campaign exporter still owns combining multiple historical campaigns.

Template names link to original local files only after provenance verification.
SNID links open the HDF5 container and identify its native group/epoch in the
tooltip; install `spectypus[links]` in the reporting interpreter for HDF5 inspection.
NGSF links use verified saved display-model provenance. Changed/missing banks
leave plain text; the downloadable evidence records the reason. Banks are never
bundled or downloaded. Local file links require access to the original bank paths.

Installing the built wheel without extras supports cached reporting. For a source checkout,
use `python -m pip install -e '.[dev,plots,links]'`; engine setup still follows
`environment.yml` and explicit external bank/NGSF paths. First plot preparation
needs the original configured runtime; fresh rendering needs the plots extra and
TeX (`latex`, `dvipng`). Cached plots need neither. Run:

```sh
spectypus doctor --config spectypus.local.json --plots
```

Doctor now actually imports native dependencies in each configured interpreter,
reports individual import times, and measures the source/bank fingerprint step.
It does not classify spectra. The optional plots check uses
`SPECTYPUS_PLOT_PYTHON` when set. An import failure must be repaired in the named
interpreter; installing packages in a different Python will not fix it.
