# Spectypus 0.3.1

This patch updates spectral plots shared by nightly Classification Reports and
SpectralAtlas. Fixed-redshift titles now show the supplied value, for example
`fixed-z (z=0.132)`. Every displayed match carries its own saved fit redshift:
`SN2007S (-4.7d) - Ia at z=0.132`. Native subtype labels are retained. Candidate
redshifts use three decimals for display; full-precision evidence is unchanged.
Missing or non-finite fit redshifts remain unknown, and zero remains valid.
Standalone fit plots and the portable atlas use the same match wording.
Regenerate existing reports to update their embedded JPGs and selected-panel exports.

Updates since 0.3.0 also include thin grey observed spectra with stronger red
model curves, retained raw-spectrum layers, improved atlas object aliases and
source-link validation, and published pipeline/report documentation. Inputs
without a declared wavelength frame now default to observer frame with an explicit
warning; users must still declare rest-frame inputs correctly.

The release preserves scientific scoring, template assets, native fit evidence,
and the JPG-only 300-dpi atlas export contract. It does not rerun classifiers or
rewrite historical reports. Fixed input z is not an independent measurement.

## Installation

Use the [Conda source-checkout instructions](USAGE.md#install), or download the
wheel from the [GitHub release](https://github.com/doctorbrew/spectypus/releases/tag/v0.3.1).
For a Python 3.10 engine environment:

```bash
python -m pip install './spectypus-0.3.1-py3-none-any.whl[engines,jax,plots]'
spectypus setup
spectypus doctor --config spectypus.local.json --plots
```

A plain wheel installs only Spectypus core. Template banks remain independent
assets; installing the wheel does not download them. Plot rendering requires
system `latex` and `dvipng`. This release is distributed through GitHub, not PyPI
or a Conda channel. `SHA256SUMS` accompanies the wheel and source archive.

Setup introduced in 0.3.0 remains available for SNID-SAGE and NGSF.
See [template setup](TEMPLATE_SETUP.md) for existing installations and manual
archives. The WISeREP download previously returned HTTP 403; when blocked, use
`--ngsf-bank-archive /path/to/supyfit_bank.zip` or `--ngsf-root`.

## Verification

The local spectypus-environment suite passed 328 tests with 10 optional skips
and one dependency deprecation warning. Redshift-label tests cover separate
input/candidate values, zero, unknown values, grid titles and both atlas renderers.
A synthetic six-panel 300-dpi JPG was visually checked for title and legend fit.
The wheel and source archive were built and inspected. A clean core-wheel
installation outside the checkout passed 35 tests with one optional skip,
including reporting, template links, diagnostics and setup. These checks
validate software behavior, not classification accuracy.

Versions follow major.minor.patch. During 0.x, minor releases may change public
interfaces; patch releases preserve interfaces and scientific evidence contracts.
