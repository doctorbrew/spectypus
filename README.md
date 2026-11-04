<p align="center">
  <img src="assets/spectypus-logo.png" alt="Spectypus — spectral traces forming a platypus and a supernova star" width="600">
</p>

# Spectypus

Spectypus brings **SNID-SAGE and NGSF** into one workflow for classifying
collections of reduced supernova spectra. It organizes results by supernova,
so you can compare template matches across epochs and classifiers and inspect
the evidence behind each proposed classification.

## Why use it?

With several spectra of an object, a candidate list from one fit is only part
of the picture. Spectypus helps you review the full set:

- **Compare classifications across epochs.** See which classes receive support,
  where the classifiers disagree, and which spectra remain unclassified.
- **Inspect the underlying fits.** Keep native scores, redshift assumptions and
  the top ten matches per classifier and search mode by default, with saved
  fit overlays available in the local viewer.
- **Keep track of incomplete evidence.** Failed runs, unsupported inputs and
  searches with no good match remain distinct. Exact duplicate spectra do not
  receive extra weight in the combined assessment.

One input table drives the batch. Known redshifts can be held fixed; missing
redshifts trigger a search. Interrupted batches resume from verified completed
fits, keeping the results available for inspection as the campaign progresses.

## How it works

![Spectypus workflow: reduced spectra and optional redshifts pass through validation, either or both classifiers, native ranking and per-supernova evidence combination.](assets/workflow.svg)

## Choose your classifiers

| Choice | Use it for | Native ranking |
| --- | --- | --- |
| **Both** (default) | Compare engine agreement and disagreements | Separate rankings; combined class support |
| **SNID-SAGE** | Correlation-based spectral template matching | Higher HσLAP-CCC |
| **NGSF** | Supernova + host-galaxy template fitting | Lower `CHI2/dof2` |

Set `enabled: false` on an unwanted engine in `spectypus.local.json`.
SAGE currently uses its optical profile, limited to **z ≤ 1**; unsupported requests
are flagged. Combined support is **not a calibrated probability**.

## Install

Python 3.10 in conda; macOS/Linux.

```bash
git clone git@github.com:sPaMFouR/spectypus.git
cd spectypus
conda env create -f environment.yml
conda activate spectypus
spectypus init --config spectypus.local.json
```

Already set up? Activate `spectypus` and skip creation/init. In the JSON, set both
engines’ `python` paths to the interpreter printed by
`python -c 'import sys; print(sys.executable)'`; set SAGE’s `templates` and NGSF’s
`root`/`parameters`. **Template banks and the NGSF checkout are external.**

The conda recipe includes the tested engine stack and **JAX/jaxlib 0.6.2** for
CPU float64 fitting. Dependencies are declared in `pyproject.toml`: `engines`
for the classifiers, `jax` for NGSF acceleration, `web` for the viewer, and
`dev` for tests. The Spectypus core itself has no third-party runtime dependency.
For an existing idle environment, install `python -m pip install -e '.[engines,jax,web]'`.
While a campaign is active, use a separate environment as described in
[backend setup](docs/USAGE.md#fitting-backends).

## Fitting backends

NGSF defaults to **guarded JAX float64 on CPU**. Set `engines.ngsf.backend` to
`"native"` for the original core or `"numpy"` for exact NumPy arithmetic in
small template blocks. The JAX path recomputes unstable mixtures and candidate
contenders with native NumPy before writing native results. Missing JAX falls
back to NumPy; an unrecognized NGSF source retains the native core. Each attempt
saves its requested/effective backend and fallback reason in `backend.json`.

SNID-SAGE retains its **native vectorized FFT backend**: a separate five-spectrum
trial took **133.1 s natively versus 138.1 s with experimental JAX FFTs** (about
4% longer), with identical results. Its FFT stage is already a small part of
the total; switching it to JAX did not save time. GPU acceleration is untested.

**Measured complete-fit time:** five fixed-redshift spectra took **148.7 s with
native NGSF** and **135.2 s with guarded JAX** in the integration trial: **13.5 s
saved, about 9% less time (1.10× faster overall)**. This is one run per spectrum
and backend under concurrent load, not a guaranteed campaign speedup. The
earlier **5.78×** result measured warmed prototype arithmetic only; it excluded
startup, template loading, output construction and native rechecks. See
[validation and timing scope](docs/VALIDATION.md) for the full evidence.

## Run a batch

Arrange ASCII spectra as `reduced/<batch>/<object>/<spectrum>.dat`, then:

```bash
spectypus manifest reduced --layout batch-object --frame observer \
  --unit angstrom --output manifest.csv
spectypus plan --manifest manifest.csv --targets targets.csv \
  --config spectypus.local.json --output results/run1
spectypus run --manifest manifest.csv --targets targets.csv \
  --config spectypus.local.json --output results/run1 --max-runs 2
```

Inspect the manifest’s object IDs and wavelength frame before fitting. The optional
[targets table](examples/targets.example.csv) has `object_id,redshift,redshift_source`;
omit `--targets targets.csv` if unavailable. Known redshifts are fixed by default;
missing ones trigger free fits. Remove `--max-runs 2` for the full batch; rerun the
same command to resume.

Results: **`matches.csv`** → top candidates, **`spectra.csv`** → individual spectra,
**`objects.csv`** → combined supernova assessments, plus logs and native evidence.

## View results

```bash
spectypus review --output results/run1
```

Open **http://127.0.0.1:8013** for progress, searchable objects, top matches and
saved fit overlays. Existing environments need `pip install -e '.[web]'` once.
Choose an object’s Review button or its Fixed-z/Free-z classifier links.
[ZTF-priority overnight run and sleep protection](docs/OVERNIGHT.md).

[Detailed usage & score semantics](docs/USAGE.md) ·
[Examples](examples/) · [Validation](docs/VALIDATION.md) ·
[Roadmap](docs/roadmap/SPECTYPUS_ROADMAP.md)

**Scope:** reduced spectra, batch classification and local review. Raw-data
reduction and accuracy measurements against independent labels are future work.
