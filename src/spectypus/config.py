"""Explicit external-engine configuration; no engine installation side effects."""
from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path

from .io import read_json


EXAMPLE = {
    "redshift_mode": "auto",
    "top_n": 10,
    "timeout_seconds": 600,
    "telluric_windows": [],
    "save_fit_curves": False,
    "free_redshift": {"min": 0.0, "max": 1.0, "step": 0.01},
    "engines": {
        "snid_sage": {"enabled": True, "python": "/path/to/classify/bin/python",
                      "templates": "/path/to/SNID-SAGE/templates", "threshold": 1.5},
        "ngsf": {"enabled": True, "python": "/path/to/classify/bin/python",
                 "root": "/path/to/NGSF", "parameters": "/path/to/NGSF/parameters.json"},
    },
}


def load_config(path: Path | dict) -> dict:
    """Validate a detached config; dictionary-relative paths use current cwd."""
    if isinstance(path, dict):
        data = deepcopy(path)
        base = Path.cwd()
    else:
        path = Path(path).expanduser().resolve()
        data = read_json(path)
        base = path.parent
    if not isinstance(data, dict):
        raise ValueError("configuration must be a JSON object")
    unknown = set(data) - set(EXAMPLE)
    if unknown:
        raise ValueError(f"unknown configuration keys: {sorted(unknown)}")
    result = {**deepcopy(EXAMPLE), **data}
    if type(result["save_fit_curves"]) is not bool:
        raise ValueError("save_fit_curves must be boolean")
    if result["redshift_mode"] not in {"auto", "both", "free", "fixed"}:
        raise ValueError("redshift_mode must be auto, both, free, or fixed")
    if type(result["top_n"]) is not int or result["top_n"] < 1:
        raise ValueError("top_n must be a positive integer")
    timeout = float(result["timeout_seconds"])
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    result["timeout_seconds"] = timeout
    windows = result["telluric_windows"]
    if not isinstance(windows, list):
        raise ValueError("telluric_windows must be a list of observer-frame Angstrom pairs")
    checked = []
    for pair in windows:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("telluric window requires lower and upper wavelengths")
        lo, hi = map(float, pair)
        if not math.isfinite(lo) or not math.isfinite(hi) or not 0 < lo < hi:
            raise ValueError("telluric window bounds must be finite, positive and ordered")
        checked.append([lo, hi])
    result["telluric_windows"] = sorted(checked)
    grid = result["free_redshift"]
    if not isinstance(grid, dict) or set(grid) != {"min", "max", "step"}:
        raise ValueError("free_redshift requires min, max, step")
    grid = {key: float(value) for key, value in grid.items()}
    if (not all(math.isfinite(v) for v in grid.values()) or grid["min"] < 0
            or grid["max"] <= grid["min"] or grid["step"] <= 0
            or grid["step"] > grid["max"] - grid["min"]):
        raise ValueError("invalid free_redshift grid")
    # NGSF uses linspace: reject silently different spacing from requested step.
    intervals = (grid["max"] - grid["min"]) / grid["step"]
    if not math.isclose(intervals, round(intervals), rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("free_redshift interval must be an integer multiple of step")
    result["free_redshift"] = grid
    if not isinstance(result["engines"], dict) or set(result["engines"]) - {"snid_sage", "ngsf"}:
        raise ValueError("engines must contain snid_sage and/or ngsf")
    engines = {}
    for name, original in result["engines"].items():
        cfg = dict(original)
        allowed = {"enabled", "python", "templates", "threshold"} if name == "snid_sage" else {
            "enabled", "python", "root", "parameters"}
        if set(cfg) - allowed:
            raise ValueError(f"unknown {name} configuration keys: {sorted(set(cfg) - allowed)}")
        if type(cfg.get("enabled", True)) is not bool:
            raise ValueError("engine enabled must be boolean")
        if not cfg.get("enabled", True):
            continue
        required = {"python", "templates"} if name == "snid_sage" else {"python", "root"}
        if not required.issubset(cfg):
            raise ValueError(f"{name} requires {sorted(required)}")
        for key in required | ({"parameters"} if "parameters" in cfg else set()):
            p = Path(cfg[key]).expanduser()
            cfg[key] = str((base / p).resolve() if not p.is_absolute() else p.resolve())
        if name == "snid_sage":
            cfg["threshold"] = float(cfg.get("threshold", 1.5))
            if not math.isfinite(cfg["threshold"]) or cfg["threshold"] < 0:
                raise ValueError("SAGE threshold must be finite and nonnegative")
        else:
            cfg.setdefault("parameters", str(Path(cfg["root"]) / "parameters.json"))
        engines[name] = cfg
    if not engines:
        raise ValueError("enable at least one engine")
    result["engines"] = engines
    return result
