# ePESSTO+ nightly typing

Put the night's reduced science `.txt` spectra in one folder, then run:

```bash
conda activate spectypus
spectypus night /path/to/spectra
```

Defaults: all top-level `.txt` files, observer-frame Å, filename stems as labels,
SNID-SAGE + NGSF with free z (fixed/free when z is supplied), saved fit curves.
Keep standards and duplicate reductions out; columns 1–2 must be finite wavelength/flux.

Results and automatic bookkeeping go in `spectra/spectypus/`; repeat the command
to resume. No per-night manifest or configuration needs preparing. Engine/template
paths are a [one-time installation setting](docs/USAGE.md#nightly-folder-command).

| Optional argument | Purpose |
| --- | --- |
| `--pattern '*.asci'` | Select another file extension |
| `--output /path/results` | Change the results folder |
| `--targets redshifts.csv` | Supply `object_id,redshift,redshift_source`; IDs match filename stems |
| `--z-max 0.3 --z-step 0.01` | Customize the configured redshift search |
| `--frame rest --unit nm` | Override input conventions; rest frame requires known z |
| `--config settings.json` | Use another installation configuration |
| `--plan-only` | Check inputs without fitting |

All options: `spectypus night --help`. Review `matches.csv` and `run_status.csv`.
Direct nightly HTML export is pending; the legacy `review` viewer still generates PDFs.
