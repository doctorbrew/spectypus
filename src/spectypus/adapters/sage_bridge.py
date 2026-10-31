#!/usr/bin/env python3
"""Run SAGE preserving candidates before CLI thresholding.

Adapted from Avinash Singh's SLSN classification development
scripts/snid_sage_candidate_adapter.py; no source-project runtime dependency.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any


MINIMUM_TESTED_VERSION = (1, 2, 3)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _version_tuple(text: str) -> tuple[int, ...]:
    values: list[int] = []
    for part in text.split("."):
        digits = "".join(character for character in part if character.isdigit())
        if not digits:
            break
        values.append(int(digits))
    return tuple(values)


def _template_value(template: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = template.get(key)
        if value is not None and str(value).strip():
            return value
    return ""


def _candidate_key(match: dict[str, Any]) -> tuple[str, str, str, str]:
    template = match.get("template") or {}
    return (
        str(_template_value(template, "name", "template_name", "sn")),
        str(_template_value(template, "age", "epoch", "phase")),
        str(match.get("redshift", "")),
        str(match.get("hsigma_lap_ccc", "")),
    )


def candidate_payload(result: Any, threshold: float) -> dict[str, Any]:
    all_matches = getattr(result, "all_matches", None)
    if not isinstance(all_matches, list):
        raise RuntimeError("SNID-SAGE result has no list-valued all_matches capability")

    best_cluster_matches: list[dict[str, Any]] = []
    clustering = getattr(result, "clustering_results", None)
    if isinstance(clustering, dict):
        cluster = clustering.get("user_selected_cluster") or clustering.get("best_cluster") or {}
        if isinstance(cluster, dict) and isinstance(cluster.get("matches"), list):
            best_cluster_matches = cluster["matches"]
    cluster_keys = {_candidate_key(match) for match in best_cluster_matches if isinstance(match, dict)}

    raw_candidate_count = len(all_matches)
    candidates: list[dict[str, Any]] = []
    for match in all_matches:
        if not isinstance(match, dict):
            continue
        score = match.get("hsigma_lap_ccc")
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(score):
            continue
        template = match.get("template") or {}
        if not isinstance(template, dict):
            template = {}
        age = _template_value(template, "age", "epoch", "phase")
        template_name = _template_value(template, "name", "template_name", "sn")
        epoch_id = _template_value(template, "template_id", "epoch_id", "filename", "path")
        if not epoch_id:
            epoch_id = f"{template_name}@{age}"
        passed = score >= threshold
        candidates.append(
            {
                "template_name": template_name,
                "template_epoch_id": epoch_id,
                "type": _template_value(template, "type", "sn_type"),
                "subtype": _template_value(template, "subtype"),
                "age_days": age,
                "redshift": match.get("redshift", ""),
                "sigma_z": match.get("sigma_z", ""),
                "lap": match.get("lap", ""),
                "metric_name": "hsigma_lap_ccc",
                "score_value": score,
                "threshold": threshold,
                "passes_threshold": passed,
                "quality": "above_threshold" if passed else "below_threshold",
                "scope": "global_candidates",
                "source": "snid_sage_result.all_matches",
                "in_best_cluster": _candidate_key(match) in cluster_keys,
            }
        )
    candidates.sort(
        key=lambda row: (
            -float(row["score_value"]),
            str(row["template_name"]),
            str(row["template_epoch_id"]),
            str(row["redshift"]),
        )
    )
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
    return {
        "schema_version": "1.0",
        "capture_status": "ok" if candidates else "no_post_gating_candidates",
        "candidate_scope": "global_candidates_after_peak_overlap_redshift_gating",
        "candidate_count": len(candidates),
        "raw_candidate_count": raw_candidate_count,
        "unrankable_nonfinite_metric_count": raw_candidate_count - len(candidates),
        "classification_success": bool(getattr(result, "success", False)),
        "threshold_metric": "hsigma_lap_ccc",
        "threshold": threshold,
        "candidates": candidates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-json", type=Path, required=True)
    parser.add_argument("--fit-curves", type=Path)
    parser.add_argument("sage_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    sage_args = list(args.sage_args)
    if sage_args[:1] == ["--"]:
        sage_args = sage_args[1:]
    if not sage_args:
        parser.error("SNID-SAGE CLI arguments are required after --")

    try:
        import snid_sage
        import snid_sage.interfaces.cli.identify as identify
        import snid_sage.interfaces.cli.main as sage_main
    except Exception as exc:
        _atomic_json(args.candidate_json, {"schema_version": "1.0", "capture_status": "import_error", "error": str(exc)})
        print(f"SNID-SAGE candidate adapter import failed: {exc}", file=sys.stderr)
        return 64

    version = str(getattr(snid_sage, "__version__", "unknown"))
    if _version_tuple(version) < MINIMUM_TESTED_VERSION or not callable(getattr(identify, "run_snid_analysis", None)):
        message = f"unsupported SNID-SAGE API/version {version}; require run_snid_analysis and >=1.2.3"
        _atomic_json(args.candidate_json, {"schema_version": "1.0", "capture_status": "unsupported_api", "error": message})
        print(message, file=sys.stderr)
        return 64

    original = identify.run_snid_analysis
    original_preprocess = identify.preprocess_spectrum
    captured = False

    def preprocessing_with_report(*call_args, **call_kwargs):
        result, trace = original_preprocess(*call_args, **call_kwargs)
        import numpy as np
        mask = np.asarray(trace.get("mask_logbins", []), dtype=bool)
        _atomic_json(args.candidate_json.with_name("mask_applied.json"), {
            "schema": "spectypus-sage-mask/1",
            "requested_observer_angstrom_windows": call_kwargs.get("wavelength_masks") or [],
            "effective_ranges_including_native_masks": trace.get("pending_mask_ranges", []),
            "masked_log_bins": int(mask.sum()), "log_grid_samples": int(mask.size),
            "treatment": "native mask-aware log rebinning and continuum fitting"})
        return result, trace

    def capturing_run(*call_args: Any, **call_kwargs: Any) -> Any:
        nonlocal captured
        result, trace = original(*call_args, **call_kwargs)
        threshold = float(call_kwargs.get("hsigma_lap_ccc_threshold", 1.5))
        payload = candidate_payload(result, threshold)
        payload["snid_sage_version"] = version
        _atomic_json(args.candidate_json, payload)
        if args.fit_curves:
            curves = []
            import numpy as np
            for candidate in payload["candidates"][:10]:
                match = next((m for m in result.all_matches
                              if str(_template_value(m.get('template') or {}, 'name', 'template_name', 'sn')) == candidate['template_name']
                              and str(_template_value(m.get('template') or {}, 'age', 'epoch', 'phase')) == str(candidate['age_days'])
                              and m.get('hsigma_lap_ccc') == candidate['score_value']), None)
                item = {"rank": candidate["rank"], "template": candidate["template_name"],
                        "score": candidate["score_value"], "redshift": candidate["redshift"],
                        "available": False}
                try:
                    processed = result.processed_spectrum
                    wave = np.asarray(processed['log_wave'], dtype=float)
                    observed = np.asarray(processed['flat_flux'], dtype=float)
                    native = (match.get('display_spectra') or match.get('spectra') or {}).get('flat')
                    model_wave = np.asarray(native['wave'] if native else wave, dtype=float)
                    model = np.asarray(native['flux'] if native else match['processed_flux'], dtype=float)
                    if wave.shape != observed.shape or model_wave.shape != model.shape:
                        raise ValueError('native curve array shapes differ')
                    item.update(available=True, observed=list(zip(wave.tolist(), observed.tolist())),
                                model=list(zip(model_wave.tolist(), model.tolist())))
                except (KeyError, TypeError, AttributeError, ValueError) as exc:
                    item['reason'] = str(exc)
                curves.append(item)
            _atomic_json(args.fit_curves, {"schema": "spectypus-fit-curves/1", "engine": "snid_sage",
                "wavelength_frame": "observer", "wavelength_unit": "angstrom",
                "flux_unit": "continuum-normalized residual flux",
                "origin": "Native SAGE result.processed_spectrum and candidate display/processed arrays",
                "curves": curves})
        captured = True
        return result, trace

    identify.run_snid_analysis = capturing_run
    identify.preprocess_spectrum = preprocessing_with_report
    try:
        returncode = int(sage_main.main(sage_args))
    except Exception as exc:
        if not captured:
            _atomic_json(
                args.candidate_json,
                {"schema_version": "1.0", "capture_status": "adapter_error", "snid_sage_version": version, "error": str(exc)},
            )
        print(f"SNID-SAGE candidate adapter failed: {exc}", file=sys.stderr)
        return 65
    finally:
        identify.run_snid_analysis = original
        identify.preprocess_spectrum = original_preprocess

    if not captured:
        _atomic_json(
            args.candidate_json,
            {
                "schema_version": "1.0",
                "capture_status": "analysis_not_reached",
                "snid_sage_version": version,
                "candidate_count": 0,
                "classification_success": False,
                "candidates": [],
            },
        )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
