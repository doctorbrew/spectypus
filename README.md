# Spectypus

**Many spectra. Multiple classifiers. One supernova.**

Spectypus runs reduced supernova spectra through SNID-SAGE and NGSF, retains
native ranked matches, and combines evidence across engines and distinct
spectra of each object. Version 0.1 is an exploratory classification pipeline.
Its combined scores are transparent **uncalibrated support**, not class
probabilities or secure scientific classifications.

For current capabilities and evidence, read [validation](docs/VALIDATION.md).
The [roadmap](docs/roadmap/SPECTYPUS_ROADMAP.md) tracks the planned results
website, campaign-scale execution, scientific evaluation and later CI/badges.
The [project index](docs/PROJECT_INDEX.md) routes development documentation.
There is no results website in v0.1 yet.

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
activate it and use `python -m pip install -e '.[dev,engines]'` to update the
local package. Skip `init` when a configured local JSON already exists: it
deliberately refuses to overwrite one. Find the active interpreter with
`python -c 'import sys; print(sys.executable)'` and use it for **both** engine
`python` fields when running everything in the dedicated environment.

Edit the JSON with the interpreter and template paths for SNID-SAGE,
and the interpreter, checkout and parameter-template paths for NGSF. Configure
the scientifically appropriate free-redshift search interval explicitly; the
example 0–1 interval is a starting configuration, not a universal prior.
Editable schema templates are also provided in [examples/](examples/).

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
