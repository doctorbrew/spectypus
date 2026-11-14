# Classification Report and SpectralAtlas

Both displays read saved evidence and retain native engine results. For normal
folder workflows, use the installed commands in the [usage guide](USAGE.md) or
[nightly guide](../README_ePESSTO+.md):

```bash
spectypus night /path/to/spectra --display report --output results/night
spectypus night /path/to/spectra --display atlas --output results/atlas
```

Classification Report is a continuous document with an inventory, spectrum
sections, Issues and an editable final night log. SpectralAtlas adds searchable
navigation and collapsible epochs. Both use the same match-grid and rank-table
contracts. Automatic drafts prioritize qualified native matches from NGSF free-z,
SNID free-z, NGSF fixed-z, then SNID fixed-z; scores are not compared across engines.
Unqualified candidates display as **Bad match**.

## Offline review and export

Open `index.html` directly. Save reviewer decisions with the log's JSON/CSV
controls; these annotations never replace native fits. **Make plots** extracts
selected panels from embedded master JPGs without a server or refitting. Exports
retain the original pixel scale and 300-dpi JPG metadata. If automatic downloads
are blocked, use the individual download links. No PDF plots are generated.

Each engine/configuration has a six-panel grid. Legends retain the matched
name, native type and phase; target labels use days since discovery only when
sourced. Rank tables retain full-precision evidence while displaying compact
scores and redshifts. Template links require verified local files and may not
resolve on another computer without those independent assets.

## Source-checkout exports

The source tools support existing verified browser snapshots. Use a new output
outside the source snapshot; retain checksums, saved attempts and input spectra.
For a continuous report from selected saved spectra:

```bash
python scripts/build_classification_report.py \
  --from-browser /path/to/verified-browser \
  --spectrum 'saved-spectrum-id' \
  --title 'Classification results' \
  --output results/new-report/index.html
```

`build_spectral_atlas.py` builds a saved-evidence atlas; `build_spectral_browser.py`
adds master plots. Their `--help` describes campaign and snapshot inputs.
`validate_spectral_atlas.py` and `validate_spectral_browser.py` check generated
products. Source refresh/preparation tools preserve scientific evidence and
require their documented frozen-input contracts. They are not classifier calls.

The generated report can be shared offline; local template links remain local.
Review the report's embedded scientific data and metadata before sharing it.
