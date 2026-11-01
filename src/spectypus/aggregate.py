"""Uncalibrated support, with explicit abstention and evidence denominators."""
from __future__ import annotations

import math
from collections import defaultdict

from .adapters.engines import TERMINAL
from .taxonomy import TAXONOMY_VERSION

METHOD = "equal-engine-winner-per-unique-spectrum/1"


def engine_vote(record: dict | None) -> dict[str, float]:
    if not record or record.get("status") != "completed":
        return {}
    matches = [m for m in record.get("candidates", []) if m.get("qualified")]
    if not matches:
        return {}
    higher = matches[0]["metric_direction"] == "higher"
    best = (max if higher else min)(m["score"] for m in matches)
    top = [m for m in matches if math.isclose(m["score"], best, rel_tol=1e-12, abs_tol=1e-12)]
    if any(not m.get("class_label") for m in top):
        return {}
    labels = sorted({m["class_label"] for m in top})
    return {label: 1.0 / len(labels) for label in labels}


def assessment(support: dict[str, float], complete: bool) -> dict:
    ranked = [{"class_label": label, "support": score} for label, score in sorted(
        support.items(), key=lambda item: (-item[1], item[0])) if score > 0]
    if not ranked:
        status, proposed = "unclassified", None
    elif len(ranked) > 1 and math.isclose(ranked[0]["support"], ranked[1]["support"], abs_tol=1e-12):
        status, proposed = "ambiguous", None
    else:
        proposed = ranked[0]["class_label"]
        status = "contested" if len(ranked) > 1 else "proposed"
    return {"status": status, "proposed_class": proposed, "ranked_classes": ranked,
            "complete": complete, "support_mass": sum(support.values()),
            "abstention_mass": max(0.0, 1.0 - sum(support.values()))}


def aggregate(plan: dict, records: dict[str, dict]) -> dict:
    spectra = []
    by_spectrum = defaultdict(list)
    for run in plan["runs"]:
        by_spectrum[run["spectrum_id"]].append(run)
    engines = sorted(plan["config"]["engines"])
    for source in plan["spectra"]:
        sid = source["spectrum_id"]
        if source["duplicate_of"]:
            spectra.append({"spectrum_id": sid, "object_id": source["object_id"],
                            "duplicate_of": source["duplicate_of"], "status": "duplicate",
                            "included_in_object_support": False})
            continue
        support = defaultdict(float)
        details, diagnostics = [], []
        complete = True
        for run in by_spectrum[sid]:
            record = records.get(run["execution_id"])
            state = "blocked" if run["blocked_reason"] else record.get("status", "pending") if record else "pending"
            vote = engine_vote(record) if state == "completed" else {}
            detail = {"engine": run["engine"], "mode": run["mode"], "status": state,
                      "execution_id": run["execution_id"], "votes": vote,
                      "reason": run["blocked_reason"] or (record.get("reason", "") if record else "not executed")}
            if run["primary"]:
                details.append(detail)
                complete = complete and state in TERMINAL
                for label, value in vote.items():
                    support[label] += value / len(engines)
            else:
                diagnostics.append(detail)
        contributors = sum(bool(item["votes"]) for item in details)
        spectra.append({"spectrum_id": sid, "object_id": source["object_id"], "duplicate_of": "",
                        "included_in_object_support": True, "expected_engines": len(engines),
                        "contributing_engines": contributors, "engine_evidence": details,
                        "diagnostic_fits": diagnostics, "numeric_sha256": source.get("staging", {}).get("numeric_sha256"),
                        **assessment(dict(support), complete)})
    by_object = defaultdict(list)
    sources = {s['spectrum_id']: s for s in plan['spectra']}
    for spectrum in spectra:
        source = sources[spectrum['spectrum_id']]
        spectrum['frame_assumed'] = source.get('frame_assumed') in (True, 'true')
        spectrum['frame_review_required'] = source.get('frame_review_required') in (True, 'true')
        by_object[spectrum["object_id"]].append(spectrum)
    objects = []
    for object_id, rows in sorted(by_object.items()):
        unique = [row for row in rows if row["included_in_object_support"]]
        support = defaultdict(float)
        for row in unique:
            for candidate in row["ranked_classes"]:
                support[candidate["class_label"]] += candidate["support"] / len(unique)
        objects.append({"object_id": object_id, "spectrum_count": len(rows),
                        'frame_assumed': any(r['frame_assumed'] for r in rows),
                        'frame_review_required': any(r['frame_review_required'] for r in rows),
                        "unique_spectrum_count": len(unique), "duplicate_count": len(rows) - len(unique),
                        "contributing_spectra": sum(bool(r["ranked_classes"]) for r in unique),
                        "spectrum_ids": [r["spectrum_id"] for r in rows],
                        **assessment(dict(support), all(r["complete"] for r in unique))})
    return {"schema": "spectypus-summary/1", "tier": "exploratory", "method": METHOD,
            "taxonomy": TAXONOMY_VERSION, "score_kind": "uncalibrated_support_not_probability",
            "plan_id": plan["plan_id"], "objects": objects, "spectra": spectra}
