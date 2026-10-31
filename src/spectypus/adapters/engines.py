from __future__ import annotations

import csv
import math
import os
import subprocess
from pathlib import Path

from ..io import digest, file_hash, read_json, tree_hash, write_json
from ..taxonomy import normalize_class

BRIDGE = Path(__file__).with_name("sage_bridge.py")
NGSF_BRIDGE = Path(__file__).with_name("ngsf_bridge.py")
TERMINAL = {"completed", "no_good_match"}


def finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fingerprint(name: str, cfg: dict) -> dict:
    """Hash engine source/bank/runtime once per plan; no automatic downloads."""
    python = Path(cfg["python"])
    if not python.is_file():
        raise ValueError(f"missing engine Python: {python}")
    probe = (
        "import importlib.util,importlib.metadata as m,json,sys,platform; "
        "spec=importlib.util.find_spec('snid_sage'); "
        "print(json.dumps({'python':platform.python_version(),'executable':sys.executable,"
        "'packages':sorted((d.metadata.get('Name',''),d.version) for d in m.distributions()),"
        "'sage_source':spec.origin if spec else None}))"
    )
    import json
    completed = subprocess.run([str(python), "-c", probe], check=True, capture_output=True,
                               text=True, timeout=30, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    runtime = json.loads(completed.stdout)
    result = {"python": str(python), "python_sha256": file_hash(python), "runtime": runtime}
    if name == "snid_sage":
        templates = Path(cfg["templates"])
        if not templates.is_dir() or not runtime["sage_source"]:
            raise ValueError("SAGE package and explicit nonempty template directory are required")
        source = Path(runtime["sage_source"]).parent
        result.update(source_sha256=tree_hash(source, suffixes={".py", ".json", ".yaml", ".yml"}),
                      bank_sha256=tree_hash(templates), templates=str(templates))
    else:
        root = Path(cfg["root"])
        if not (root / "run.py").is_file() or not (root / "bank").is_dir():
            raise ValueError(f"invalid NGSF checkout: {root}")
        result.update(source_sha256=digest({"run": file_hash(root / "run.py"),
                         "NGSF": tree_hash(root / "NGSF", suffixes={".py", ".csv", ".json"})}),
                      bank_sha256=tree_hash(root / "bank"),
                      parameters_sha256=file_hash(Path(cfg["parameters"])))
    return result


def parse_sage(path: Path) -> tuple[list[dict], str]:
    payload = read_json(path)
    if payload.get("capture_status") not in {"ok", "no_post_gating_candidates"}:
        raise ValueError(f"SAGE capture failed: {payload.get('capture_status')}")
    if not isinstance(payload.get("candidates"), list) or type(payload.get("classification_success")) is not bool:
        raise ValueError("malformed SAGE candidate payload")
    matches = []
    for raw in payload["candidates"]:
        score = finite(raw.get("score_value"))
        if score is None:
            continue
        if raw.get("metric_name") != "hsigma_lap_ccc":
            raise ValueError("unexpected SAGE metric")
        native, subtype = str(raw.get("type", "")), str(raw.get("subtype", ""))
        matches.append({"template": str(raw.get("template_name", "")),
                        "template_epoch_id": str(raw.get("template_epoch_id", "")),
                        "native_class": native, "native_subtype": subtype,
                        "class_label": normalize_class(native, subtype),
                        "phase_days": finite(raw.get("age_days")),
                        "redshift": finite(raw.get("redshift")),
                        "metric": "hsigma_lap_ccc", "metric_direction": "higher",
                        "score": score, "qualified": payload["classification_success"] and raw.get("passes_threshold") is True,
                        "native": raw})
    matches.sort(key=lambda row: (-row["score"], row["template"], row["template_epoch_id"], str(row["redshift"])))
    for rank, row in enumerate(matches, 1):
        row["rank"] = rank
    status = "completed" if payload["classification_success"] and any(m["qualified"] for m in matches) else "no_good_match"
    return matches, status


def parse_ngsf(path: Path) -> tuple[list[dict], str]:
    required = {"SN", "CHI2/dof2", "Z", "Phase", "GALAXY"}
    matches = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"NGSF CSV requires {sorted(required)}")
        for index, raw in enumerate(reader, 1):
            if None in raw or any(v is None for v in raw.values()):
                raise ValueError("ragged NGSF result row")
            score = finite(raw["CHI2/dof2"])
            if score is None or score < 0:
                continue
            native_key = raw["SN"].strip()
            parts = native_key.split("/", 2)
            native_class = parts[0] if len(parts) == 3 else ""
            matches.append({"template": native_key, "template_epoch_id": native_key,
                            "native_class": native_class, "native_subtype": "",
                            "class_label": normalize_class(native_class),
                            "phase_days": finite(raw["Phase"]), "redshift": finite(raw["Z"]),
                            "metric": "CHI2/dof2", "metric_direction": "lower", "score": score,
                            "qualified": True, "native": raw, "source_row": index})
    matches.sort(key=lambda row: (row["score"], row["template"], row["native"]["GALAXY"], row["source_row"]))
    for rank, row in enumerate(matches, 1):
        row["rank"] = rank
    return matches, "completed" if matches else "no_good_match"


def build_command(run: dict, config: dict, directory: Path) -> tuple[list[str], Path, Path]:
    name = run["engine"]
    cfg = config["engines"][name]
    input_path = directory / "spectrum.txt"
    output = directory / "native"
    output.mkdir()
    if name == "snid_sage":
        result = directory / "sage_candidates.json"
        command = [cfg["python"], str(BRIDGE), "--candidate-json", str(result), "--", "identify",
                   str(input_path), cfg["templates"], "--output-dir", str(output), "--minimal",
                   "--no-plots", "--no-progress", "--profile", "optical", "--max-output-templates", str(config["top_n"]),
                   "--hsigma-lap-ccc-threshold", str(cfg["threshold"])]
        if run["mode"] == "fixed":
            command += ["--forced-redshift", str(run["redshift"])]
        else:
            grid = config["free_redshift"]
            command += ["--zmin", str(grid["min"]), "--zmax", str(grid["max"])]
        return command, directory, result
    params = read_json(Path(cfg["parameters"]))
    params.update(object_to_fit=str(input_path), saving_results_path=str(output) + os.sep,
                  show_plot=0, show_plot_png=False, how_many_plots=0)
    if run["mode"] == "fixed":
        z = run["redshift"]
        params.update(use_exact_z=1, z_exact=z, z_range_begin=z, z_range_end=z, z_int=0)
    else:
        grid = config["free_redshift"]
        # Legacy NGSF truncates this floating ratio before linspace. Preserve
        # the requested number of intervals even for 0.3 / 0.05 ~= 5.99999.
        interval_count = round((grid["max"] - grid["min"]) / grid["step"])
        native_step = grid["step"]
        if int((grid["max"] - grid["min"]) / native_step) < interval_count:
            native_step = math.nextafter(native_step, 0.0)
        if int((grid["max"] - grid["min"]) / native_step) != interval_count:
            raise ValueError("cannot represent requested NGSF redshift grid")
        params.update(use_exact_z=0, z_exact=0, z_range_begin=grid["min"], z_range_end=grid["max"],
                      z_int=native_step, mask_galaxy_lines=0)
        write_json(directory / "redshift_grid.json", {"requested": grid, "native_z_int": native_step,
                   "points": interval_count + 1, "effective_step": (grid["max"] - grid["min"]) / interval_count})
    write_json(directory / "parameters.json", params)
    root = Path(cfg["root"])
    command = [cfg["python"], str(NGSF_BRIDGE), str(root / "run.py"), str(directory / "parameters.json")]
    return command, root, output / "spectrum.csv"


def parse_result(engine: str, path: Path) -> tuple[list[dict], str]:
    return parse_sage(path) if engine == "snid_sage" else parse_ngsf(path)
