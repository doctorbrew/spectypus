# Spectypus 0.2.1

This release preserves explicit SAGE SLSN-I/II subtypes, adds read-only external
label evaluation and loading profiles, and improves individual JPG download
fallback guidance. Scientific algorithms and historical native attempts are
unchanged. Browser and scientific limits are documented in [VALIDATION.md](VALIDATION.md).

## Installation

Download the wheel from the [GitHub release](https://github.com/doctorbrew/spectypus/releases/tag/v0.2.1)
and install with `python -m pip install spectypus-0.2.1-py3-none-any.whl`.
External classifiers and template banks remain independent; see [USAGE.md](USAGE.md).
PyPI publication is not part of this release.

## Public-source cleanup, 2026-11-14

Repository history and release artifacts were sanitized to remove internal
planning documents, stale campaign notes and generation prompts. Commit and tag
identifiers changed. Re-clone older checkouts rather than merging old history.
The release archives and checksums were rebuilt; package version and runtime
code remain unchanged. A retired one-use migration utility and its dedicated
regression test were removed; active reporting and numerical tests remain.

## Verification

The sanitized-source local suite passed 308 tests with 10 optional skips and
one dependency deprecation warning. Clean-wheel installation and distribution
content verification are recorded with the release. Software checks do not establish classification accuracy.

Versions follow major.minor.patch. During 0.x, minor releases may change public
interfaces; patch releases preserve interfaces and scientific evidence contracts.
