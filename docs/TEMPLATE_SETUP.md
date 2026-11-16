# Template banks and engine setup

Install the [Spectypus environment](USAGE.md#install) first. Classifier code and
template banks are separate assets; they are not bundled in the Spectypus wheel.
Keep banks outside the source repository so multiple projects can reuse them.

## Automated setup

```bash
conda activate spectypus
spectypus setup
spectypus doctor --config spectypus.local.json --plots
```

`setup` downloads SNID-SAGE 1.2.3 templates, NGSF source at revision
`b78cfe083fd79def6f6dcbcc9bf7f6b63825de31`, and the WISeREP NGSF bank. It uses
the active Python interpreter and writes a new `spectypus.local.json`. The bank
directories live under `~/.local/share/spectypus/`, with versioned names.
Choose another location with `--data-dir /path/to/assets`, or a shared user
configuration with `--config ~/.config/spectypus/config.json`. `night` finds that
user configuration when there is no local or explicitly selected config.

For just one classifier, use `--engine snid-sage` or `--engine ngsf`.
The other engine is disabled in the generated config. Check `free_redshift`
before fitting: the generated 0–1 range is an example, not a scientific choice.

Completed asset directories are reused on retry. Existing configurations are
never overwritten: use them directly or choose a new `--config` filename.
An invalid existing bank is reported rather than replaced. To acquire a fresh
bank, choose a new `--data-dir`; do not replace one serving active fits.
If a later download fails, completed assets remain available but no config is
written. Retry the same command after resolving the failure.

Downloads are staged and validated before installation. SAGE's release checksum
and the pinned NGSF source checksum are checked. WISeREP publishes no checksum
used by this installer; its downloaded SHA-256 is recorded for reproducibility,
not independently authenticated. `spectypus-download.json` records provenance
in each installed asset directory. ZIP entries cannot escape the staging tree;
links and special files are rejected. Limits are 2 GiB per download and 8 GiB
uncompressed per archive. Setup checks bank structure, not scientific quality.

Only `setup` provisions assets. Importing Spectypus, installing its wheel, and
running `night`, `run`, `init` or `doctor` do not download template banks.

## Use an existing installation

Register both existing banks without downloading or modifying them:

```bash
spectypus setup \
  --snid-templates /path/to/SNID-SAGE/templates \
  --ngsf-root /path/to/NGSF \
  --config spectypus.local.json
```

The SAGE directory must contain `template_index.json` and its referenced HDF5
files. NGSF must contain `run.py`, `NGSF/`, `parameters.json` and `bank/`.
For one existing classifier, also pass the corresponding `--engine` option.
You can mix an existing SAGE bank with a downloaded NGSF installation, or vice
versa, by supplying only one existing path. Setup never populates a missing
explicit path: it must already be a usable bank/source tree.

## Manual downloads and WISeREP failures

WISeREP can refuse automated downloads with HTTP 403. In that case, download
the bank using the [upstream NGSF instructions](https://github.com/oyaron/NGSF#to-run-one-object)
and their [WISeREP link](https://www.wiserep.org/content/wiserep-getting-started#supyfit).
Then let setup extract and configure the downloaded ZIP:

```bash
spectypus setup --ngsf-bank-archive /path/to/supyfit_bank.zip
```

This uses the same asset directory and config defaults as `setup`; repeat any
custom `--data-dir`, `--config` or `--snid-templates` arguments from the failed
attempt. It still downloads NGSF source if a managed installation is missing.
If WISeREP also refuses browser access, obtain the bank through its maintainers
or use an existing installation. Spectypus cannot bypass upstream access rules.

For entirely manual SAGE provisioning, use the downloader supplied by SAGE:

```bash
SNID_SAGE_TEMPLATE_DIR="$HOME/.local/share/spectypus/sage-templates" \
  snid-sage-download-templates
```

See the [SAGE installation guide](https://fiorenst.github.io/SNID-SAGE/installation/installation/)
for its own download behavior. Register that path with `--snid-templates`.

For entirely manual NGSF provisioning:

```bash
mkdir -p "$HOME/.local/share/spectypus"
git clone https://github.com/oyaron/NGSF.git "$HOME/.local/share/spectypus/NGSF"
git -C "$HOME/.local/share/spectypus/NGSF" checkout b78cfe083fd79def6f6dcbcc9bf7f6b63825de31
```

Extract the WISeREP ZIP so the installation has this layout, then register it
with `--ngsf-root`. Keep the supplied metadata, supernova and galaxy templates:

```text
NGSF/
├── run.py
├── NGSF/
├── parameters.json
└── bank/
    ├── original_resolution/{sne,gal}/
    └── binnings/
        ├── 10A/{sne,gal}/
        └── 30A/{sne,gal}/
```

NGSF needs the configured resolution and its 30-Angstrom fallback. Review
`temp_sn_tr` and `temp_gal_tr` in `parameters.json` against the installed bank.
Spectypus supplies per-attempt spectrum/output and redshift settings without
changing that base parameter file. A newer upstream revision is not
automatically validated by Spectypus's pinned dependencies.

## Manual configuration

For custom paths or separate engine environments:

```bash
spectypus init --config spectypus.local.json
python -c 'import sys; print(sys.executable)'
```

Edit the new JSON file:

| Field | Value |
| --- | --- |
| Each engine's `python` | Absolute path to its environment's Python executable |
| `engines.snid_sage.templates` | SAGE bank directory containing `template_index.json` |
| `engines.ngsf.root` | NGSF source directory containing `bank/` |
| `engines.ngsf.parameters` | NGSF's base `parameters.json` |
| `engines.ENGINE.enabled` | `false` to exclude an engine |
| `free_redshift` | Scientifically appropriate `min`, `max`, `step` |

Paths expand `~` and resolve relative to the config file; `$HOME` is not expanded
inside JSON. Validate with `spectypus doctor --config spectypus.local.json --plots`.
Install system `latex` and `dvipng` for new plot rendering. `doctor` does not run
a classification. Cite the engines and template collections as described in the
[README](../README.md#citation-and-acknowledgements).
