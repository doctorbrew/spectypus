# Results website and SLSN batch

**Current campaign:** see [OVERNIGHT.md](OVERNIGHT.md) for ZTF priorities, masked
fixed/free fits, native overlays, and the sleep-protected launch command. The
original unmasked batch below is retained as historical evidence.

From the project directory:

```bash
conda activate spectypus
spectypus review --output results/slsn_20261031/run
```

Open http://127.0.0.1:8013. For another batch, change `--output`; use `--port`
to choose another local port. Existing installs need `pip install -e '.[web]'`
once. The conda recipe now includes the viewer. The command runs in the
foreground; Ctrl-C stops the website without stopping a separate classifier run.

The website shows completion and input problems, suggested classes, searchable
and paginated objects, a needs-review filter, top matches for each spectrum and
classifier, and the input spectrum. Viewing never starts a fit. Fixed/free modes
and native score directions remain distinct. Scores are suggestions, not
classification probabilities. Missing model curves are explicitly unavailable.
New runs can save model curves with `save_fit_curves: true`; the current masked
campaign enables this. Older attempts without saved curves remain unavailable.
Saved review notes and interactive zoom controls are pending.

Only the frozen current plan and hash-verified attempt records supply class
scores. Tampered results are flagged and contribute no votes. Original input
hashes are checked before plotting. The reader keeps a 30-second in-memory
snapshot; the page refreshes every minute, and **Refresh results** forces a new
verification. A pending fit may be queued or executing; the batch controller's
`campaign_status.json` identifies the active attempt.

The viewer binds only to localhost. It exposes no arbitrary file route or
classification endpoint. It uses local assets, system font fallbacks and SVG;
no internet service is required to view a batch.

## Full local archive, 2026-10-31

The source atlas union contains 3,876 spectrum records for 344 catalogue objects:
2,684 Gomez, 78 Chen, and 1,114 expanded Fritz records. These are candidate
catalogue entries, not 344 confirmed SLSNe or a frozen rate numerator. Source
channels remain labelled. Thirty Fritz targets had no downloaded Fritz spectra;
their separate coverage list does not establish absence from the other archives.

The original unmasked dry plan contains 2,930 eligible fits on 1,481 spectra from 214 objects:
1,132 fixed/349 free NGSF fits and 1,112 fixed/337 free SNID-SAGE fits. Other
records remain visible as blocked or repeated. In particular, the downloaded
Fritz records do not explicitly establish wavelength frames/units; their
classification is blocked pending source metadata. In total, 2,378 records fail
input checks and 17 are exact numerical repeats; 32 otherwise eligible attempts
are outside SAGE's wavelength or redshift support. Chen wavelengths are rest
frame according to the delivered ReadMe and are converted once. Catalogue
redshift conflicts remain unknown; the pipeline uses free searches for eligible
observer-frame spectra without a consistent supplied redshift.

Preparation is reproducible with `scripts/prepare_slsn_campaign.py --help`.
It reads the original project's existing spectral-union implementation without
editing source data. The imported table, source hashes, loader snapshot, exact
alias/redshift evidence, configuration and plan are local under
`results/slsn_20261031/`. No spectra or classifier results are pushed to GitHub.

The controller `scripts/run_saved_campaign.py` starts with the shortest and
longest eligible fixed/free inputs, then continues through every eligible fit.
Those first attempts are real batch members, not extra votes. This initial
campaign ran serially; current bounded-worker operation is documented in
[OVERNIGHT.md](OVERNIGHT.md). In this initial setup, numeric-library threads
were limited to one, each fit had a 900-second
timeout, and the controller stops below 20 GiB free disk or after six consecutive
execution failures. Completed attempts remain resumable. A frozen runtime under
`results/slsn_20261031/runtime/` isolates the running batch from development edits.

Monitor the launched batch:

```bash
tail -f results/slsn_20261031/campaign.log
cat results/slsn_20261031/campaign_status.json
```

Resume an interrupted batch with its frozen runtime and environment:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
PYTHONPATH="$PWD/results/slsn_20261031/runtime" \
caffeinate -i python scripts/run_saved_campaign.py \
  results/slsn_20261031
```

On Linux omit `caffeinate -i`. Inspect status before resuming; the output lock
prevents two writers. Do not update the classifier environment or external banks
during the run. A changed classifier source, bank or environment fails its
provenance checks rather than silently mixing results.

The older project's SNID-SAGE status table reports 1,422 `ok`, 134
`no_good_match`, four failed and 1,289 ineligible attempts. Its NGSF registry
reports five completed attempts on one object. These historical states are not
relabelled as Spectypus results or measured classification accuracy. Older
review apps remain in the source project (`snid-review.sh dashboard`, port 8011;
`ngsf-review.sh serve`, port 8012), with their own saved-evidence requirements.
