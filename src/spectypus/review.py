"""Read-only review of the current plan and verified classifier attempts."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
import math
import json
import re
import time

from .aggregate import aggregate
from .io import digest, read_json
from .manifest import spectrum_data
from .features import features
from .pipeline import SCHEMA, current_record


def fit_states(runs):
    result = {}
    for engine in ('ngsf', 'snid_sage'):
        result[engine] = {}
        for mode in ('fixed', 'free'):
            rows = [r for r in runs if r['engine'] == engine and r['mode'] == mode and r['status'] != 'duplicate']
            states = Counter(r['status'] for r in rows)
            done = sum(states[s] for s in ('completed', 'no_good_match'))
            status = ('no supplied z' if mode == 'fixed' and any(r.get('redshift') is None for r in runs) else 'not requested') if not rows else 'finished' if done == len(rows) else 'failed' if states['failed'] or states['invalid_evidence'] else 'blocked' if states['blocked'] else 'queued / active'
            result[engine][mode] = {'status': status, 'finished': bool(rows) and done == len(rows),
                                    'done': done, 'total': len(rows), 'no_good_match': states['no_good_match']}
    return result


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
        obj['primary_complete'] = obj['complete']
        obj['complete'] = all(r['status'] in {'completed', 'no_good_match', 'duplicate'}
                              for r in by_object[obj['object_id']])
        obj["run_counts"] = dict(Counter(r["status"] for r in by_object[obj["object_id"]]))
        obj["batches"] = sorted({sources[s].get("batch", "") for s in obj["spectrum_ids"]} - {""})
        obj["needs_review"] = obj["status"] != "proposed" or not obj["complete"]
        meta = [sources[s] for s in obj['spectrum_ids']]
        def items(value):
            try: return json.loads(value or '[]') if isinstance(value, str) else value or []
            except ValueError: return []
        obj['samples'] = sorted({x for m in meta for x in items(m.get('samples'))})
        obj['ztf_id'] = next((m.get('ztf_id') for m in meta if re.fullmatch(r'ZTF\d{2}[a-z]{7}', m.get('ztf_id', ''))), '')
        obj['tns_name'] = next((m.get('tns_name') for m in meta if re.fullmatch(r'SN\d{4}[A-Za-z]+', m.get('tns_name', ''))), '')
        obj['priority_ztf'] = any(m.get('priority_ztf') == 'true' for m in meta)
        obj['fit_states'] = fit_states(by_object[obj['object_id']])
    return {"output": output, "plan": plan, "records": records, "runs": runs, "summary": summary,
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
            "samples": sorted({x for o in summary['objects'] for x in o['samples']}),
            "priority_window": {"start": plan['spectra'][0].get('priority_start'),
                                "end": plan['spectra'][0].get('priority_end')},
            "note": "Automated suggestions for review. Scores are not classification probabilities.",
            "model_curves": "Native saved fit curves when available; no fitting on page requests."}


def fit_curve(snapshot, execution_id, rank=1):
    run = next((r for r in snapshot['runs'] if r['execution_id'] == execution_id), None)
    if run is None: raise KeyError(execution_id)
    record = current_record(snapshot['output'], run)
    if record is None: return {'available': False, 'reason': 'No verified saved fit'}
    path = Path(record['attempt_path']) / 'fit_curves.json'
    if 'fit_curves.json' not in record['artifacts']:
        return {'available': False, 'reason': 'This attempt has no saved model curves'}
    if rank > len(record['candidates']):
        return {'available': False, 'reason': 'No candidate at this rank'}
    candidate = record['candidates'][rank-1]
    payload = read_json(path)
    curve = next((c for c in payload['curves'] if c['template'] == candidate['template']
                  and math.isclose(c['score'], candidate['score'], rel_tol=1e-5, abs_tol=1e-8)
                  and (run['engine'] != 'ngsf' or c.get('galaxy') == candidate['native']['GALAXY'])), None)
    if not curve or not curve.get('available'): return {'available': False, 'reason': 'Native model curve unavailable for this candidate'}
    source = next(s for s in snapshot['plan']['spectra'] if s['spectrum_id'] == run['spectrum_id'])
    points = curve['observed']
    return {**{k: v for k, v in payload.items() if k != 'curves'}, **curve, 'rank': rank,
            'execution_id': execution_id, 'features': features(source['redshift'], points[0][0], points[-1][0],
                snapshot['plan']['config'].get('telluric_windows', []))}


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
            "features": features(source["redshift"], samples[0][0], samples[-1][0],
                                 snapshot["plan"]["config"].get("telluric_windows", [])),
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
                ztf: bool = False, priority: bool = False, sample: str = '',
                offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        rows = snapshot()["summary"]["objects"]
        rows = [o for o in rows if q.casefold() in ' '.join([o['object_id'], o['ztf_id'], o['tns_name']]).casefold()
                and (not ztf or o['ztf_id']) and (not priority or o['priority_ztf'])
                and (not sample or sample in o['samples'])
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

    @app.get('/api/fit')
    def fit(execution_id: str, rank: int = Query(1, ge=1, le=100)):
        try: return fit_curve(snapshot(), execution_id, rank)
        except KeyError as exc: raise HTTPException(404, 'Unknown fit') from exc

    return app
