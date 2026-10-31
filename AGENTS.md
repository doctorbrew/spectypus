# Spectypus development guidance

Start with `docs/PROJECT_INDEX.md`. Use `conda activate spectypus` for development
and tests; `environment.yml` and the extras in `pyproject.toml` own installation.
Inspect the working tree before editing; preserve unrelated local changes.

- Keep the package standalone. External NGSF source and classifier template
  banks are independent assets; do not relocate, edit, or download them silently.
- Preserve native scores, score direction, class labels, wavelength units/frame,
  redshift provenance, and the distinction between unsupported input, engine
  failure, no good match, and a successful candidate result.
- Combined support is uncalibrated, dimensionless evidence, never a probability
  or secure classification. Keep duplicate/mode suppression and abstentions.
- Original spectra and completed attempts are evidence. New checks use new
  directories under `results/`; do not overwrite historical validation products.
- Run `python -m pytest -q` for relevant core changes. Real-engine checks must
  be explicitly bounded, with their manifest/config and limitations recorded.
- Follow the canonical roadmap. A results viewer must read verified saved
  evidence, not silently refit, reinterpret missing support as zero, or merge
  annotations into immutable engine results.
- Append consequential changes to `docs/DEVELOPMENT_LOG.md`; keep current status
  in the roadmap and evidence assessments in `docs/VALIDATION.md`.
- GitHub/PyPI publication and public badge endpoints require authorization.
  Never display a live badge or calibrated-accuracy claim without its evidence.
