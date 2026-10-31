"""Read-only review of the current plan and verified classifier attempts."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
import math
import time

from .aggregate import aggregate
from .io import digest, read_json
from .manifest import spectrum_data
from .pipeline import SCHEMA, current_record


def compact_record(record: dict, top_n: int) -> dict:
    """Keep displayed rows and every tied winning vote without retaining banks of candidates."""
    candidates = record["candidates"]
    qualified = [m for m in candidates if m.get("qualified")]
    best = None
    if qualified:
        best = (max if qualified[0]["metric_direction"] == "higher" else min)(m["score"] for m in qualified)
    keep = candidates[:top_n] + [m for m in candidates[top_n:] if m.get("qualified") and
                                math.isclose(m["score"], best, rel_tol=1e-12, abs_tol=1e-12)]
    fields = ("rank", "template", "native_class", "native_subtype", "class_label", "phase_days",
              "redshift", "metric", "metric_direction", "score", "qualified")
    return {"status": record["status"], "reason": record["reason"],
            "candidates": [{k: m.get(k) for k in fields} for m in keep]}


def read_snapshot(output: Path) -> dict:
    output = Path(output).resolve()
    plan = read_json(output / "plan.json")
    identity = plan.pop("plan_id")
    if plan.get("schema") != SCHEMA or digest(plan) != identity:
        raise ValueError("current plan integrity check failed")
    plan["plan_id"] = identity
    records, runs = {}, []
    for run in plan["runs"]:
        record = None if run["blocked_reason"] else current_record(output, run)
        state = "blocked" if run["blocked_reason"] else "pending"
        reason = run["blocked_reason"] or "Queued or active; no saved result yet"
        if run["blocked_reason"].startswith("duplicate_of:"):
            state = "duplicate"
        if record:
            records[run["execution_id"]] = compact_record(record, plan["config"]["top_n"])
            state, reason = record["status"], record["reason"]
        elif not run["blocked_reason"] and (output / "attempts" / run["execution_id"] / "current.json").exists():
            state, reason = "invalid_evidence", "Saved result failed verification; excluded from scores"
        runs.append({**run, "status": state, "reason": reason})
    summary = aggregate(plan, records)
    sources = {s["spectrum_id"]: s for s in plan["spectra"]}
    by_object = defaultdict(list)
    for run in runs:
        by_object[run["object_id"]].append(run)
    for obj in summary["objects"]:
        obj["run_counts"] = dict(Counter(r["status"] for r in by_object[obj["object_id"]]))
        obj["batches"] = sorted({sources[s].get("batch", "") for s in obj["spectrum_ids"]} - {""})
        obj["needs_review"] = obj["status"] != "proposed" or not obj["complete"]
    return {"plan": plan, "records": records, "runs": runs, "summary": summary,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def overview(snapshot: dict) -> dict:
    summary, plan = snapshot["summary"], snapshot["plan"]
    counts = dict(Counter(r["status"] for r in snapshot["runs"]))
    by_engine = {name: dict(Counter(r["status"] for r in snapshot["runs"] if r["engine"] == name))
                 for name in plan["config"]["engines"]}
    return {"schema": "spectypus-review/1", "plan_id": plan["plan_id"],
            "checked_at": snapshot["checked_at"], "objects": len(summary["objects"]),
            "spectra": len(summary["spectra"]), "runs": counts, "engines": by_engine,
            "classes": dict(Counter(o["proposed_class"] or "No suggestion" for o in summary["objects"])),
            "complete_objects": sum(o["complete"] for o in summary["objects"]),
            "batches": sorted({s.get("batch", "") for s in plan["spectra"]} - {""}),
            "note": "Automated suggestions for review. Scores are not classification probabilities.",
            "model_curves": "Not available in this viewer; saved rankings and input spectra are shown."}


def object_detail(snapshot: dict, object_id: str) -> dict:
    obj = next((o for o in snapshot["summary"]["objects"] if o["object_id"] == object_id), None)
    if obj is None:
        raise KeyError(object_id)
    rows = []
    spectra = {s["spectrum_id"]: s for s in snapshot["summary"]["spectra"]}
    for source in snapshot["plan"]["spectra"]:
        if source["object_id"] != object_id:
            continue
        fits = []
        for run in snapshot["runs"]:
            if run["spectrum_id"] != source["spectrum_id"]:
                continue
            record = snapshot["records"].get(run["execution_id"])
            # Native candidates may contain absolute paths; expose only review fields.
            matches = [{k: m.get(k) for k in ("rank", "template", "native_class", "native_subtype",
                        "class_label", "phase_days", "redshift", "metric", "metric_direction", "score", "qualified")}
                       for m in (record["candidates"][:snapshot["plan"]["config"]["top_n"]] if record else [])]
            fits.append({**run, "matches": matches})
        rows.append({**spectra[source["spectrum_id"]],
                     "metadata": {k: source.get(k) for k in ("batch", "mjd", "instrument", "redshift",
                                  "redshift_source", "wavelength_frame", "wavelength_unit", "phase_rest_days")},
                     "fits": fits})
    return {"object": obj, "spectra": rows, "plan_id": snapshot["plan"]["plan_id"],
            "checked_at": snapshot["checked_at"]}


def observed_spectrum(snapshot: dict, spectrum_id: str) -> dict:
    source = next((s for s in snapshot["plan"]["spectra"] if s["spectrum_id"] == spectrum_id), None)
    if source is None:
        raise KeyError(spectrum_id)
    if source["blocked_reason"]:
        return {"available": False, "reason": source["blocked_reason"], "spectrum_id": spectrum_id}
    try:
        text, staging = spectrum_data(source)
        if staging != source["staging"]:
            raise ValueError("Input spectrum changed since this batch was planned")
    except (ValueError, OSError) as exc:
        return {"available": False, "reason": str(exc), "spectrum_id": spectrum_id}
    samples = [list(map(float, line.split())) for line in text.splitlines()]
    return {"available": True, "spectrum_id": spectrum_id, "points": samples,
            "wavelength_unit": "angstrom", "wavelength_frame": "observer",
            "flux_unit": "input units", "flux_treatment": staging["flux_treatment"],
            "source_sha256": staging["source_sha256"], "model_available": False}


def create_app(output: Path, *, cache_seconds: float = 30):
    """Optional web dependencies are imported only when the viewer is requested."""
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    output = Path(output).expanduser().resolve()
    static = Path(__file__).parent / "web"
    app = FastAPI(title="Spectypus results", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=static), name="static")
    cached, lock = {}, RLock()

    def snapshot(refresh=False):
        with lock:
            if refresh or not cached or time.monotonic() - cached["time"] >= cache_seconds:
                try:
                    value = read_snapshot(output)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    cached.clear()
                    raise HTTPException(409, "Results unavailable: " + str(exc)) from exc
                cached.update(value=value, time=time.monotonic())
            return cached["value"]

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/api/summary")
    def summary(refresh: bool = False):
        return overview(snapshot(refresh))

    @app.get("/api/objects")
    def objects(q: str = "", batch: str = "", label: str = "", review: bool = False,
                offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        rows = snapshot()["summary"]["objects"]
        rows = [o for o in rows if q.casefold() in o["object_id"].casefold()
                and (not batch or batch in o["batches"])
                and (not label or (o["proposed_class"] or "No suggestion") == label)
                and (not review or o["needs_review"])]
        return {"total": len(rows), "offset": offset, "rows": rows[offset:offset + limit]}

    @app.get("/api/object")
    def detail(object_id: str):
        try:
            return object_detail(snapshot(), object_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown object") from exc

    @app.get("/api/spectrum")
    def spectrum(spectrum_id: str):
        try:
            return observed_spectrum(snapshot(), spectrum_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown spectrum") from exc

    return app
