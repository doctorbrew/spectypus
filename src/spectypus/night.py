"""Flat-folder nightly input with recorded defaults and no per-night setup."""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path

from .config import load_config
from .efosc import science_exports
from .io import atomic_text, digest


def installation_config(explicit: Path | None = None) -> Path:
    """Reuse installation settings without searching for external template banks."""
    if explicit is not None:
        path = explicit.expanduser().resolve()
    elif os.environ.get("SPECTYPUS_CONFIG"):
        path = Path(os.environ["SPECTYPUS_CONFIG"]).expanduser().resolve()
    else:
        candidates = [Path.cwd() / "spectypus.local.json",
                      Path.home() / ".config" / "spectypus" / "config.json"]
        path = next((p for p in candidates if p.is_file()), candidates[-1])
    if not path.is_file():
        raise ValueError(
            f"engine configuration not found: {path}. One-time setup: "
            "spectypus init --config ~/.config/spectypus/config.json; set engine/template paths. "
            "Or select existing settings with --config or SPECTYPUS_CONFIG.")
    return path


def prepare_night(folder: Path, *, config: Path | None = None, output: Path | None = None,
                  pattern: str | None = None, frame: str | None = None, unit: str | None = None,
                  mode: str = "both", z_min: float | None = None, z_max: float | None = None,
                  z_step: float | None = None, nonfinite: str = "mask",
                  timeout: float = 1800) -> tuple[Path, dict, Path]:
    """Create one immutable internal manifest; original spectra stay untouched.

    Filename stems are opaque object labels, never parsed astronomical identities.
    Frame/unit values are a declared nightly profile, not metadata inferred from flux.
    """
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise ValueError(f"input folder is not a directory: {folder}")
    if pattern is not None and (not pattern or pattern in {".", ".."} or "/" in pattern or "\\" in pattern or "**" in pattern):
        raise ValueError("--pattern must be a filename glob, e.g. '*.txt'; nightly input is nonrecursive")
    frame, unit = frame or "observer", unit or "angstrom"
    if frame not in {"observer", "rest"} or unit not in {"angstrom", "nm"}:
        raise ValueError("nightly input requires observer/rest frame and angstrom/nm units")
    output = output.expanduser().resolve() if output is not None else folder / "spectypus"
    if output == folder:
        raise ValueError("output must be separate from the input folder (default: FOLDER/spectypus)")
    if nonfinite not in {"mask", "reject"}:
        raise ValueError("nonfinite policy must be mask or reject")
    rows = science_exports(folder, pattern)
    if rows is not None:
        if frame != "observer" or unit != "angstrom":
            raise ValueError("EFOSpec exports declare observer/angstrom; frame/unit overrides conflict with their metadata")
    else:
        paths = sorted(p for p in (folder.glob(pattern) if pattern is not None else folder.iterdir())
                       if p.is_file() and not p.name.startswith(".") and
                       (pattern is not None or p.suffix.lower() in {".txt", ".asci", ".ascii", ".dat"}))
        if not paths:
            raise ValueError(f"no reduced ASCII spectra match {pattern or 'supported extensions'} in {folder}; use reduced outputs, not raw FITS")
        labels = [p.stem for p in paths]
        if len(labels) != len(set(labels)) or any(label != label.strip() for label in labels):
            raise ValueError("ambiguous filename stems; narrow --pattern or use an explicit manifest")
        rows = [{"spectrum_id": p.name, "object_id": p.stem, "path": str(p),
                 "wavelength_frame": frame, "wavelength_unit": unit,
                 "batch": folder.name, "object_id_source": "filename stem; no alias inference",
                 "frame_source": "spectypus night input profile (--frame)",
                 "unit_source": "spectypus night input profile (--unit)"} for p in paths]
    for row in rows:
        row["nonfinite_policy"] = nonfinite

    settings = load_config(installation_config(config))
    settings["redshift_mode"] = mode
    settings["save_fit_curves"] = True
    settings["timeout_seconds"] = timeout
    for key, value in (("min", z_min), ("max", z_max), ("step", z_step)):
        if value is not None:
            settings["free_redshift"][key] = value
    settings = load_config(settings)

    # Content addressing avoids overwriting earlier input selections on resume.
    manifest = output / ".inputs" / f"{digest(rows)}.csv"
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted({key for row in rows for key in row}))
    writer.writeheader()
    writer.writerows(rows)
    content = stream.getvalue()
    if manifest.exists():
        with manifest.open(newline="", encoding="utf-8") as handle:
            if handle.read() != content:
                raise ValueError(f"generated nightly manifest changed: {manifest}; use a new output directory")
    else:
        atomic_text(manifest, content)
    return manifest, settings, output
