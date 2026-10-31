"""Object identity, redshift routing, explicit units, and immutable input staging."""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

from .io import digest, file_hash, read_csv, write_csv

FIELDS = ["spectrum_id", "object_id", "path", "wavelength_frame", "wavelength_unit",
          "redshift", "redshift_source", "batch", "mjd", "phase_rest_days", "instrument"]


def redshift(value: object, context: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        z = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid redshift for {context}: {value!r}") from exc
    if not math.isfinite(z) or z < 0:
        raise ValueError(f"redshift must be finite and nonnegative for {context}")
    return z


def read_manifest(path: Path, targets: Path | None = None) -> list[dict]:
    path = Path(path).expanduser().resolve()
    rows = read_csv(path)
    if not rows:
        raise ValueError("manifest contains no spectra")
    required = set(FIELDS[:5])
    if not required.issubset(rows[0]):
        raise ValueError(f"manifest requires columns {sorted(required)}")
    target_map = {}
    if targets is not None:
        for target in read_csv(Path(targets).expanduser().resolve()):
            key = target.get("object_id", "")
            if not key or key in target_map:
                raise ValueError(f"missing or repeated target object_id: {key!r}")
            if "redshift" not in target:
                raise ValueError("targets requires redshift column")
            target_map[key] = (redshift(target["redshift"], key),
                               target.get("redshift_source") or "targets_csv")
    seen = set()
    object_z = defaultdict(list)
    output = []
    for raw in rows:
        row = dict(raw)
        sid, oid = row["spectrum_id"], row["object_id"]
        if not sid or not oid or sid in seen:
            raise ValueError(f"empty object_id or missing/repeated spectrum_id: {sid!r}")
        seen.add(sid)
        z = redshift(row.get("redshift"), sid)
        source = row.get("redshift_source") or ("manifest" if z is not None else "")
        target_z, target_source = target_map.get(oid, (None, ""))
        if z is not None and target_z is not None and not math.isclose(z, target_z, rel_tol=0, abs_tol=1e-10):
            raise ValueError(f"conflicting manifest/target redshift for {oid}: {z} vs {target_z}")
        if target_z is not None:
            z, source = target_z, target_source
        row["redshift"], row["redshift_source"] = z, source
        if z is not None:
            object_z[oid].append((z, source))
        p = Path(row["path"]).expanduser()
        row["path"] = str((path.parent / p).resolve() if not p.is_absolute() else p.resolve())
        row["wavelength_frame"] = row["wavelength_frame"].lower()
        row["wavelength_unit"] = row["wavelength_unit"].lower()
        output.append(row)
    for oid, values in object_z.items():
        if any(not math.isclose(z, values[0][0], rel_tol=0, abs_tol=1e-10) for z, _ in values):
            raise ValueError(f"conflicting redshifts across spectra of {oid}")
    for row in output:
        if row["redshift"] is None and object_z[row["object_id"]]:
            row["redshift"], row["redshift_source"] = object_z[row["object_id"]][0]
    return sorted(output, key=lambda r: (r["object_id"], r["spectrum_id"]))


def spectrum_data(row: dict) -> tuple[str, dict]:
    """Strict numeric input: invalid data blocks a spectrum, never becomes zero."""
    source = Path(row["path"])
    if source.suffix.lower() in {".fits", ".fit", ".fts"}:
        raise ValueError("FITS ingestion is not implemented; provide reduced ASCII")
    if row["wavelength_frame"] not in {"observer", "rest"}:
        raise ValueError("wavelength_frame must explicitly be observer or rest")
    units = {"angstrom": 1.0, "nm": 10.0}
    if row["wavelength_unit"] not in units:
        raise ValueError("wavelength_unit must be angstrom or nm")
    scale = units[row["wavelength_unit"]]
    if row["wavelength_frame"] == "rest":
        if row["redshift"] is None:
            raise ValueError("rest-frame wavelengths require a known redshift")
        scale *= 1 + row["redshift"]
    samples = []
    extra_columns = set()
    header_lines = 0
    for line_no, line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith(("#", "%", ";", "@")):
            continue
        data = text.split("#", 1)[0]
        # CSV missingness must survive parsing: collapsing commas into
        # whitespace would turn a missing flux into the uncertainty column.
        if "," in data:
            try:
                columns = [part.strip() for part in next(csv.reader([data], strict=True))]
            except csv.Error as exc:
                raise ValueError(f"invalid CSV sample at line {line_no}") from exc
        else:
            columns = data.split()
        if not samples and [s.lower() for s in columns[:2]] in (["wavelength", "flux"], ["wave", "flux"]):
            header_lines += 1
            continue
        try:
            wave, flux = float(columns[0]), float(columns[1])
        except (IndexError, ValueError) as exc:
            raise ValueError(f"invalid numeric sample at line {line_no}") from exc
        if not math.isfinite(wave) or not math.isfinite(flux) or wave <= 0:
            raise ValueError(f"nonfinite sample or nonpositive wavelength at line {line_no}")
        samples.append((wave * scale, flux))
        extra_columns.add(max(0, len(columns) - 2))
    if len(samples) < 2:
        raise ValueError("need at least two numeric samples")
    original_order = samples[:]
    samples.sort()
    if any(b[0] <= a[0] for a, b in zip(samples, samples[1:])):
        raise ValueError("duplicate wavelengths are unsupported")
    content = "".join(f"{wave:.17g} {flux:.17g}\n" for wave, flux in samples)
    report = {
        "source_sha256": file_hash(source), "numeric_sha256": digest(samples),
        "source_frame": row["wavelength_frame"], "source_unit": row["wavelength_unit"],
        "staged_frame": "observer", "staged_unit": "angstrom", "wavelength_scale": scale,
        "flux_treatment": "unchanged shape in input units; no flux-density Jacobian applied",
        "uncertainty_treatment": "not passed to engines; no uncertainty invented",
        "ignored_extra_column_counts": sorted(extra_columns), "recognized_header_lines": header_lines,
        "samples": len(samples), "sorted_wavelengths": samples != original_order,
        "min_angstrom": samples[0][0], "max_angstrom": samples[-1][0],
    }
    return content, report


def prepare_spectra(rows: list[dict]) -> list[dict]:
    output, by_hash = [], defaultdict(list)
    for row in rows:
        value = {**row, "blocked_reason": "", "duplicate_of": "", "identity_conflict": False}
        try:
            _, value["staging"] = spectrum_data(row)
            by_hash[value["staging"]["numeric_sha256"]].append(value)
        except (ValueError, OSError, UnicodeError) as exc:
            value["blocked_reason"] = str(exc)
        output.append(value)
    for copies in by_hash.values():
        if len({r["object_id"] for r in copies}) > 1:
            for row in copies:
                row["blocked_reason"] = "identical numeric spectrum assigned to multiple objects"
                row["identity_conflict"] = True
        else:
            for row in copies[1:]:
                row["duplicate_of"] = copies[0]["spectrum_id"]
    return output


def discover(root: Path, destination: Path, *, layout: str, frame: str, unit: str) -> int:
    """Only explicit object/file or batch/object/file layouts; no filename guessing."""
    root, destination = root.expanduser().resolve(), destination.expanduser().resolve()
    if destination.exists():
        raise ValueError(f"refusing to overwrite existing manifest: {destination}")
    if not root.is_dir():
        raise ValueError(f"input root is not a directory: {root}")
    depth = 2 if layout == "object" else 3
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".txt", ".dat", ".ascii", ".csv"}:
            continue
        relative = path.relative_to(root)
        if len(relative.parts) != depth:
            raise ValueError(f"file does not match declared {layout} layout: {relative}")
        rows.append({"spectrum_id": relative.as_posix(), "object_id": relative.parts[-2],
                     "path": str(path), "wavelength_frame": frame, "wavelength_unit": unit,
                     "batch": relative.parts[0] if depth == 3 else ""})
    if not rows:
        raise ValueError("no ASCII spectra found")
    write_csv(destination, rows, FIELDS)
    return len(rows)
