from __future__ import annotations

import pytest

from spectypus.aggregate import aggregate, engine_vote


def candidate(label="Ia", score=5, *, qualified=True, direction="higher"):
    return {"class_label": label, "score": score, "qualified": qualified, "metric_direction": direction}


def record(*candidates, status="completed"):
    return {"status": status, "reason": "", "candidates": list(candidates)}


def plan_for(spectra, engines=("a", "b")):
    return {"plan_id": "test", "config": {"engines": {e: {} for e in engines}}, "spectra": spectra,
            "runs": [{"execution_id": f"{s['spectrum_id']}-{e}", "spectrum_id": s["spectrum_id"],
                      "object_id": s["object_id"], "engine": e, "mode": "fixed", "primary": True,
                      "blocked_reason": "duplicate_of:" + s["duplicate_of"] if s["duplicate_of"] else ""}
                     for s in spectra for e in engines]}


def source(sid, *, duplicate="", object_id="SN"):
    return {"spectrum_id": sid, "object_id": object_id, "duplicate_of": duplicate}


def test_repeated_templates_cannot_multiply_votes():
    evidence = record(*[candidate("Ia", 5) for _ in range(20)], candidate("II", 5))
    assert engine_vote(evidence) == {"Ia": .5, "II": .5}


def test_native_scores_never_averaged_across_engines():
    plan = plan_for([source("s")])
    summary = aggregate(plan, {"s-a": record(candidate("Ia", 50)), "s-b": record(candidate("II", .01, direction="lower"))})
    obj = summary["objects"][0]
    assert obj["status"] == "ambiguous" and obj["proposed_class"] is None
    assert {c["class_label"]: c["support"] for c in obj["ranked_classes"]} == {"II": .5, "Ia": .5}


def test_missing_failed_and_no_good_engines_remain_in_denominator():
    plan = plan_for([source("s")])
    summary = aggregate(plan, {"s-a": record(candidate("Ia"))})
    obj = summary["objects"][0]
    assert obj["ranked_classes"][0]["support"] == .5
    assert obj["abstention_mass"] == .5 and not obj["complete"]
    summary = aggregate(plan, {"s-a": record(candidate("Ia")), "s-b": record(status="no_good_match")})
    assert summary["objects"][0]["complete"]
    assert summary["objects"][0]["abstention_mass"] == .5


def test_multiple_spectra_equal_weight_duplicate_no_weight():
    plan = plan_for([source("s1"), source("s1copy", duplicate="s1"), source("s2")])
    records = {"s1-a": record(candidate("Ia")), "s1-b": record(candidate("Ia")),
               "s2-a": record(candidate("II")), "s2-b": record(status="failed")}
    summary = aggregate(plan, records)
    obj = summary["objects"][0]
    assert obj["unique_spectrum_count"] == 2 and obj["duplicate_count"] == 1
    assert obj["ranked_classes"] == [{"class_label": "Ia", "support": .5}, {"class_label": "II", "support": .25}]
    assert obj["status"] == "contested" and not obj["complete"]


def test_free_mode_diagnostic_cannot_double_vote():
    plan = plan_for([source("s")], engines=("a",))
    plan["runs"].append({**plan["runs"][0], "execution_id": "s-a-free", "mode": "free", "primary": False})
    summary = aggregate(plan, {"s-a": record(candidate("Ia")), "s-a-free": record(candidate("II"))})
    assert summary["objects"][0]["ranked_classes"] == [{"class_label": "Ia", "support": 1.0}]
    assert summary["spectra"][0]["diagnostic_fits"][0]["votes"] == {"II": 1.0}


def test_objects_with_no_results_are_retained():
    plan = plan_for([source("s", object_id="missing"), source("t", object_id="other")])
    summary = aggregate(plan, {})
    assert len(summary["objects"]) == 2
    assert all(o["status"] == "unclassified" and o["abstention_mass"] == 1 for o in summary["objects"])


def test_unknown_best_class_abstains_not_lower_known_class():
    assert engine_vote(record(candidate("", 8), candidate("Ia", 4))) == {}
    assert engine_vote(record(candidate("Ia", 8), candidate("", 8))) == {}


@pytest.mark.parametrize("status", ["failed", "no_good_match", "pending"])
def test_failed_or_unqualified_candidate_cannot_vote(status):
    assert engine_vote(record(candidate("Ia", 100), status=status)) == {}
    assert engine_vote(record(candidate("Ia", 100, qualified=False))) == {}
