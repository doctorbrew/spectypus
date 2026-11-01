# ZTF-priority overnight classification

The current batch is `results/slsn_ztf_overnight_20261031/`. It was launched in the
`spectypus` environment with sleep protection. The earlier unmasked batch was
stopped cleanly and retained; `selection.json` records the relationship.

## Open the results

```bash
cd /Users/avinash/Work/SupernovaeData/_Project_SpecTypus
conda activate spectypus
spectypus review --output results/slsn_ztf_overnight_20261031/run
```

Open http://127.0.0.1:8013. The default table selects ZTF objects in the confirmed
window **2018-03-17 ≤ date < 2026-01-01**. Turn off either filter to inspect the
rest. Sample membership comes from exact catalogue aliases and can include
multiple samples; the spectrum's source remains a separate filter. Names link
to Fritz and TNS.

Each object has NGSF and SNID-SAGE columns with Fixed-z and Free-z links. Green
(`#15b01a`, xkcd:green) means every requested fit for that engine/mode finished;
red (`#e50000`, xkcd:red) means unfinished, with queued/failed/blocked stated.
A completed no-good-match search is green but explicitly reports that outcome.
A mode that cannot be requested, such as fixed-z without supplied z, is grey.
Counts exclude repeated spectra. Website completion includes diagnostic free
fits; the combined class score still uses the primary mode only.

Review opens the object's spectrum/epoch selector and saved model overlays.
Engine/mode buttons open the same review filtered to that combination. A Python-generated top-ten collage precedes the scrollable individual matches;
each has JPG and PDF download links. Curves are captured from the native classifier run;
viewing does not refit. SAGE displays continuum-normalized residual flux; NGSF
displays its native normalized SN+host model. The scales are not interchangeable.
Missing or unverified curves are reported unavailable.

## Overnight launch or resume

The active batch continues independently of this chat. **Do not start a second
copy while it is running.** Check its log/status first:

```bash
tail -f results/slsn_ztf_overnight_20261031/campaign.log
cat results/slsn_ztf_overnight_20261031/campaign_status.json
```

After an interruption, resume from the project directory:

```bash
conda activate spectypus
nohup ./scripts/overnight.sh results/slsn_ztf_overnight_20261031 \
  --prioritize-batch chen \
  >> results/slsn_ztf_overnight_20261031/campaign.log 2>&1 &
```

The script uses the frozen runtime saved inside the batch. It invokes
`caffeinate -ims` on macOS, preventing idle/system sleep for the lifetime of the
job (the system-sleep assertion requires AC power). **Keep the Mac plugged in
and its lid open.** The display can turn off. No global power settings are
changed. Sleep protection ends when the job exits. Check it with:

```bash
pmset -g assertions
```

To stop cleanly, send SIGINT to the **controller PID in `campaign_status.json`**:
`kill -INT <controller-pid>`. The running engine process group is terminated,
prior completed attempts remain saved, and the same launch command resumes.
The output lock rejects a second writer.

The queue is finite: 5,194 eligible fits across 1,482 spectra. The first priority
is 1,854 fits for 118 eligible ZTF objects within the window; 203 catalogue
objects satisfy that priority filter when blocked inputs are included. Other
objects remain queued. Fixed-z runs precede free-z runs within each priority
group, and Chen spectra are preferred within that ordering. This can require
multiple nights; no next-morning completion is promised.

Execution is serial with numerical-library threads limited to one. Each fit has
a 900-second timeout. The controller stops below 20 GiB free disk or after six
consecutive execution failures. Completed and no-good-match attempts are reused
on resume; a new explicit retry batch is required to repeat completed no-match
searches. Do not modify the classifier environment or external banks mid-run.

## Masking and input repair

Both fixed and free searches apply conservative observer-frame telluric windows:
6860–6960, 7150–7350, 7550–7750, 8100–8400 and 8900–9900 Å. They are configurable
through `telluric_windows` and are not a transmission correction or a complete
near-infrared mask. The strong A/B and water-vapour regions are described in the
[MAKEE atmospheric documentation](https://sites.astro.caltech.edu/~tb/makee/Atmosphere/index.html)
and [ESO MUSE manual](https://www.eso.org/sci/facilities/paranal/instruments/muse/doc/ESO-261650_MUSE_User_Manual_P113.pdf).

SAGE uses native mask-aware logarithmic rebinning/continuum handling. The NGSF
subprocess excludes masked object samples and the corresponding template samples
from its normal equations and chi-square; simply dropping rows would interpolate
across the gaps. No external engine source is edited. Each attempt retains
`spectral_features.json`, `mask_applied.json`, and `fit_curves.json` when curves
are requested. Missing values are saved as null, never physical zero flux.

Gold bands show the telluric exclusions. Pink markers show expected host-line
positions at the supplied redshift, including during free-z diagnostics. Host
lines are marked, **not masked or claimed as detections**. The guides use
approximate air-wavelength references; input air/vacuum conventions may differ.
See [SDSS air/vacuum line references](https://www.sdss4.org/dr17/spectro/spectro_basics/).
No supplied redshift means no host-line markers.

All 78 Chen spectra now pass input validation. One file had 51 repeated identical
rows; only those exact repeats were removed in a derived copy. Original spectra
remain unchanged. Conflicting duplicate samples are not averaged. Unknown
wavelength frames/units, including the Fritz archive, remain blocked pending
metadata. Free-z searches on supplied rest-frame spectra still require their
catalogue redshift to recover observer wavelengths, so they are not a blind
redshift-recovery benchmark.

Both modes and masking change the protocol. Previous unmasked/fixed-only successes
remain archived but do not substitute for a new masked fit or a missing free-z
fit. Thus the new batch includes the full archive, including every unfinished or
no-good-match spectrum, rather than mixing incompatible scores.


## Python figure exports and phase references

The viewer now displays Matplotlib figures, using the bundled house `plot_style`
helper, SciencePlots, Hiroshige colours, inward ticks and mandatory LaTeX. Each
figure is saved as a vector PDF plus a 300-dpi JPG under `run/review_figures/`.
The top-ten collage and individual matches are generated on first review and
cached. One plotting subprocess runs at a time; no classifier is re-run. The
first view can take about a minute. Use Refresh results to reload the selected
spectrum after new fits finish; automatic count updates preserve gallery scroll.

For a fresh installation, install `pip install -e '.[web,plots]'` and a working
TeX installation providing `latex`, `dvipng`, `type1cm` and `cm-super`. During the
active campaign, do not modify the classifier environment. This checkout uses
`.venv-plots` with access to the existing scientific packages and separate
SciencePlots/pypalettes installations. `SPECTYPUS_PLOT_PYTHON` can select another
plotting interpreter. Missing plotting dependencies produce an explicit error;
there is no alternate browser-plot or non-LaTeX fallback.

Flux limits now use 50 observer-frame Angstrom Savitzky–Golay smoothing for
limits only, with 1.1× outward scaling. Positive lower bounds move down by division
by 1.1; negative upper bounds move up toward zero. A three-point median/MAD guard
suppresses isolated one/two-bin spikes only in the limit calculation. Masks,
missing values and large wavelength gaps are not bridged. Filter-edge samples
and unsupported short/coarse segments cannot set extrema; insufficient support
produces an explicit error rather than reverting to raw spikes. Three-point
windows use a linear polynomial because a quadratic would leave data unchanged.
Native spectra, model arrays and scores remain unchanged. Limit diagnostics stay
in `gallery.json`; they are no longer printed underneath figures.

Titles follow `SNNAME - MJD - NGSF (Fixed-z) (z=...)` or the Free-z equivalent
without a supplied-z suffix. Each plot has an internal matched-SN/phase box and
27-point tick labels (50% larger). There is no bottom text. Target phase details
remain available in the website and saved metadata. Existing figures are not
regenerated by editing the renderer or by resuming fitting; a new gallery is
made only when requested through review.

Each figure names the template SN and its native phase; scores and fit redshifts
remain in the review table. Target
phase references are separate: catalogue maximum (with band) or discovery, plus
source, reference MJD, observer days and rest-frame days when z is known. Rest
phase is `(spectrum MJD - reference MJD)/(1+z)`, using the supplied catalogue z.
Different bands can peak on different dates; conflicting dates within the same
reference type/band are retained and flagged, not averaged. Template phases retain
the native library reference and are not assumed to use the target's reference.
No dates are inferred from a template match or a filename, and discovery is not
explosion time. Existing local catalogue dates are used; this step does not query
live Fritz/TNS or fit light curves to determine new maxima.

The current `review_metadata.json` has references for 333 of 344 catalogue objects.
It records exact-alias joins and source file hashes without changing the frozen
classification plan. To prepare this optional sidecar for a new run:

```bash
python scripts/prepare_review_metadata.py --output results/YOUR_BATCH/run \
  --source-root /path/to/_ProjectG_VolumetricRatesSLSNe
```

Status buttons now separate finished, queued/active, blocked and failed counts.
For SN2018avk, NGSF fixed-z has four finished and ten blocked requests: nine lack
an explicit wavelength frame and one lacks a supported wavelength unit. These
are ingestion blocks, not ten rejected classifier matches. Hover over a button
or inspect the relevant epoch to see the reasons.


### Sample scope when resuming fits

The active batch contains Fritz, Chen and Gómez records and enables both NGSF
and SNID-SAGE. `--prioritize-batch chen` changes ordering only: it does not filter
out other sources. The fitting controller does not render Python galleries.
Fritz records remain blocked until their wavelength frame is established.
The SkyPortal spectrum model documents its wavelength array in Angstrom, while
its nullable `units` field refers to flux, not wavelength:
https://github.com/skyportal/skyportal/blob/main/skyportal/models/spectrum.py
No rest/observer-frame declaration was found in the 1,114 saved Fritz records.
One original header says nm and is flagged for separate review; headers must not
be substituted blindly for the API array's unit contract.
