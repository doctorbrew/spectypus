# ePESSTO+ nightly typing

Run on the EFOSpec nightly outputs:

```bash
conda activate spectypus
spectypus night /path/to/EFOSpec/runs/2026-10-28 \
  --output /path/to/EFOSpec/data/classifications/2026-10-28
```

This selects the current manifest's science exports, excluding standards and old
revisions. SNID-SAGE + NGSF run free-z fits, or fixed/free when z is supplied.
Nonfinite flux samples are excluded and their wavelength intervals masked in both
engines; exclusions are recorded and original spectra remain untouched.

Also accepts a flat science folder: `spectypus night /path/to/spectra` discovers
`.txt`, `.asci`, `.ascii` and `.dat`, defaulting to observer-frame Å and output
`spectra/spectypus/`. Repeat to resume. No per-night setup files are needed; engine/template
paths are a [one-time installation setting](docs/USAGE.md#nightly-folder-command).

| Optional argument | Purpose |
| --- | --- |
| `--pattern 'tSN*.asci'` | Restrict the input selection |
| `--output /path/results` | Change the results folder |
| `--targets redshifts.csv` | Supply `object_id,redshift,redshift_source`; use EFOSpec object names or flat-folder filename stems |
| `--z-max 0.3 --z-step 0.01` | Customize the configured redshift search |
| `--frame rest --unit nm` | Flat-folder conventions; rest frame requires known z |
| `--nonfinite reject` | Block spectra with nonfinite flux instead of masking |
| `--timeout 1800` | Seconds allowed per fit (default: 1800) |
| `--config settings.json` | Use another installation configuration |
| `--plan-only` | Check inputs without fitting |

Open `index.html`: six-panel JPGs, matches and an editable final log (JSON/CSV).
TNS discovery dates are fetched when its bot credentials are configured.
It updates automatically; no server is needed.
All options: `spectypus night --help`.
