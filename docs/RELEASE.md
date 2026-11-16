# Spectypus 0.3.0

This release adds **`spectypus setup`** for downloading classifier template banks
and configuring their paths. It downloads SNID-SAGE 1.2.3 templates and pinned
NGSF source with its WISeREP bank, or registers existing installations. Assets
remain outside the repository; existing configurations and banks are preserved.
Fitting and imports never trigger these downloads. Scientific algorithms and
historical native attempts are unchanged.

Setup supports single-engine installations, a custom asset directory and a
manually downloaded NGSF ZIP. Completed assets are reused after a later download
fails. Archives are staged and checked for unsafe paths, size limits and bank
structure; checksums are verified for SAGE and pinned NGSF source. The WISeREP
bank's hash is recorded without an independently supplied upstream checksum.

The README now provides a shorter quick start and direct SNID-SAGE/NGSF
citations. [Template setup](TEMPLATE_SETUP.md) covers manual alternatives and
existing paths; [VALIDATION.md](VALIDATION.md) records the scientific limits.

## Installation

Use the [Conda source-checkout instructions](USAGE.md#install), or download the
wheel from the [GitHub release](https://github.com/doctorbrew/spectypus/releases/tag/v0.3.0).
For a Python 3.10 engine environment, install the wheel with its extras:

```bash
python -m pip install './spectypus-0.3.0-py3-none-any.whl[engines,jax,plots]'
spectypus setup
spectypus doctor --config spectypus.local.json --plots
```

A plain wheel installs only the Spectypus core. Classifiers and template banks
remain independent assets; installing the wheel does not download banks. New
plot rendering also needs system `latex` and `dvipng`. Neither PyPI nor a Conda
channel is used for this release. Download checksums are provided in `SHA256SUMS`.

**Known upstream limitation:** WISeREP returned HTTP 403 during verification.
If its automated download is blocked, use
`spectypus setup --ngsf-bank-archive /path/to/supyfit_bank.zip`, or register an
existing NGSF installation with `--ngsf-root`. Full fresh NGSF-bank download
could not be verified from this environment.

## Public-source cleanup, 2026-11-14

Repository history and release artifacts were sanitized to remove internal
planning documents, stale campaign notes and generation prompts. Commit and tag
identifiers changed. Re-clone older checkouts rather than merging old history.
The release archives and checksums were rebuilt; package version and runtime
code remain unchanged. A retired one-use migration utility and its dedicated
regression test were removed; active reporting and numerical tests remain.

## Verification

The local suite passed 322 tests with 10 optional skips and one existing
dependency deprecation warning. Live SAGE download, its checksum and `doctor`
check passed. Pinned NGSF source extraction and registration of existing local
banks passed; offline tests cover the manual ZIP fallback and failed-download
recovery. Clean-wheel installation and distribution content were checked.
Software checks do not establish classification accuracy.

Versions follow major.minor.patch. During 0.x, minor releases may change public
interfaces; patch releases preserve interfaces and scientific evidence contracts.
