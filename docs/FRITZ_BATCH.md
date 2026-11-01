# Provisional Fritz classification batch

Current output: `results/fritz_assumed_observer_20261101/run`.

The user clarified that downloaded Fritz spectra should almost always be in the
observer frame, but a small unspecified fraction may be rest-frame. This is a
working assumption, **not individual verification** and not a calibrated numerical
probability. All rows record `frame_assumed=true` and `frame_review_required=true`.
Successful classification does not clear those flags. Object/spectrum JSON and CSV
summaries retain them; the website labels these results provisional and keeps them
in the review filter. A header scan cannot identify every wrongly declared frame.

## Scope and exclusions

The batch contains 1,114 Fritz records for 195 objects, with 2,851 eligible fits:
1,427 NGSF and 1,424 SNID-SAGE; 1,047 fixed-z and 1,804 free-z. Known-z spectra
request both modes; unknown-z spectra request free-z only. The confirmed ZTF date
priority is retained. Telluric masks, host markers, native curve capture, the
900-second timeout and existing free-z grid are inherited from the earlier batch.
No Python plot galleries are generated during fitting.

Fifteen complete, finite JSON wavelength/flux arrays were extracted into derived
ASCII files. No input samples were imputed or silently removed. Original downloads
remain unchanged. The plan retains 128 records whose JSON arrays contain missing
or nonfinite samples, five with duplicate wavelengths, and one with a conflicting
original wavelength-unit header as blocked. Seventy-seven repeated records do not
contribute twice. Classifier-specific support exclusions remain separate.

The [SkyPortal spectrum model](https://github.com/skyportal/skyportal/blob/main/skyportal/models/spectrum.py)
defines the API wavelength array in Angstrom; its nullable `units` field is for
flux/errors. Fritz spectrum 50170 has an original `CUNIT1=nm` header and remains
flagged rather than receiving an automatic conversion. Camera `FRAMENO` and
`FRAMEID` identifiers are not wavelength-frame declarations.

`frame_assumptions.json` records the user clarification, metadata checksums,
contradictions and derived-file hashes. `preflight.json` records the counts and
reused validation attempts. The two bounded native tests (one spectrum, both
engines) completed successfully and were copied/reverified by exact execution ID
for reuse. This establishes integration, not the correctness of the frame assumption.

## Run or resume

This is a separate campaign alongside the existing Chen/Gómez queue, with one
worker each (two classification workers in total). Both use single-thread
numerical libraries and macOS sleep protection. Keep the Mac plugged in with the
lid open. Do not start another copy of either running campaign.

After interruption, from the project directory:

```bash
conda activate spectypus
nohup ./scripts/overnight.sh results/fritz_assumed_observer_20261101 \
  >> results/fritz_assumed_observer_20261101/campaign.log 2>&1 &
```

Check `campaign_status.json` and `campaign.log` in that directory. The previous
all-source campaign remains unchanged; its Fritz rows still show their original
blocks. Do not add counts from the two campaigns or combine their object scores:
this supplementary run has not been merged into a cross-campaign review table.
To inspect Fritz results separately:

```bash
spectypus review --output results/fritz_assumed_observer_20261101/run --port 8014
```

The frozen runtime lives inside the campaign. Do not change its inputs, engine
environment or template banks mid-run. To prepare a future batch with an explicit
assumption note, use `scripts/prepare_fritz_campaign.py --help`.
