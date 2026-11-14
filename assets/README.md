# Spectypus visual assets

- `spectypus-logo.png`: website/README wordmark; 2172 × 724 RGBA PNG with
  real transparency.
  The brighter azure-blue lettering is visible on dark backgrounds; the website
  uses the transparent asset directly. The spectrum-shaped platypus and supernova star
  represent many spectra contributing to one object-level interpretation.
- `workflow.svg`: editable, deterministic workflow diagram. Its labels describe
  the current classification pipeline, starting with already reduced spectra.
  The two engine branches are logical alternatives, not concurrent execution.

The source-distribution manifest includes these assets. Keep implementation and
scientific contracts in `docs/USAGE.md`, not in this asset record.

Reusable report CSS/JS is packaged in `src/spectypus/reporting/assets/`, shared
by installed nightly/batch reports and the source-checkout atlas exporters.

- All badges use the compact 20-pixel Shields flat style, lowercase labels,
  grey label panels and standard status colours, matching RiseTime and CINDER.
  Metric SVGs are rendered locally by `scripts/ci_metrics.py` on each CI run.
- `python.svg` and `license.svg`: static badges for the package's declared
  Python floor and existing GPLv3 license.
- `ci-build.svg`, `ci-tests.svg`, `ci-coverage.svg`: automatically generated
  from trusted default-branch GitHub Actions reports, with source SHA/run URLs inside the SVG.
  Do not hand-edit metric values. These are stored with the repository;
  no external badge endpoint is used. See [CI scope](../CONTRIBUTING.md#continuous-verification).
