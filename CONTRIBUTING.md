# Contributing

Report bugs or suggest changes through [GitHub Issues](https://github.com/doctorbrew/spectypus/issues).
For bugs, include the command, Spectypus version/commit, operating system,
relevant configuration and logs, and a small shareable example. Remove private
paths, credentials and unpublished data before posting.

## Development setup

From the checkout, use the environment in [environment.yml](environment.yml):

```bash
conda env create -f environment.yml
conda activate spectypus
python -m pytest -q
python -m build
```

If the environment exists, activate it instead of recreating it. Dependency
changes belong in [pyproject.toml](pyproject.toml) and the conda recipe; keep
shared pins consistent. Use a separate environment for updates while fits run.
The recipe uses conda NumPy/SciPy binaries because the tested macOS pip SciPy
wheel failed to load. It is not a complete cross-platform lockfile.

Keep changes focused and describe the behavior changed and checks performed in
your pull request. Add regression coverage for substantive behavior changes.
Preserve native scores, units, provenance, failure states and saved evidence.
Never bundle or modify external classifier sources/template banks. Real-engine
checks need an explicit sample, configuration, resource bounds and a new results
directory. Automated tests do not measure scientific classification accuracy.

See the [usage guide](docs/USAGE.md) for scientific/software contracts and
[validation](docs/VALIDATION.md) for evidence and limitations.

## Local development files

Keep personal settings, internal planning notes, caches and scratch work out of
Git and distribution archives. Use `.ai-local/` or `*.local.md` for local notes.
Inspect staged changes and built archives before publishing. Ignore rules do
not remove files from existing commits or previously published artifacts.

## Python API

```python
from pathlib import Path
from spectypus import make_plan, run_batch, summarize_output

plan = make_plan(Path("manifest.csv"), Path("spectypus.local.json"))
summary = run_batch(Path("manifest.csv"), Path("spectypus.local.json"),
                    Path("results/run1"), max_runs=2)
summary = summarize_output(Path("results/run1"))
```

Configuration dictionaries are validated and copied; their relative paths use
the working directory. File-based configuration uses its own directory.

## Continuous verification

The [CI workflow](.github/workflows/ci.yml) runs Python 3.10 on Linux with
`.[dev,webtest,engines,jax,ci]`, tests using synthetic data, builds both package
formats, and smoke-tests an installed wheel outside the checkout. Real-engine
and optional plot-style checks are separate.

[Actions](https://github.com/doctorbrew/spectypus/actions/workflows/ci.yml) provides
JUnit, coverage and distributions in `ci-reports` artifacts (14-day retention).
Build/test/coverage badges update from trusted default-branch reports; each SVG
records its source commit and run URL. They represent the last published report,
not an in-flight or newer untested commit. Coverage is not classification accuracy.
Python/license badges reflect package metadata and the license.

Pull-request checks are read-only. Badge publication uses repository assets,
needs no external endpoint, skips an advanced branch and cannot fail passing
checks. Missing/failed reports cannot produce a passing-count badge. See the
[benchmark procedures](docs/BENCHMARKS.md) for optional engine experiments.
