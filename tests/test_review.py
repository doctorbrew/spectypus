from pathlib import Path

import pytest

from spectypus.io import read_json, write_json, file_hash
from spectypus.pipeline import run_batch
from spectypus.review import read_snapshot, overview, object_detail, observed_spectrum, compact_record
from spectypus.aggregate import engine_vote


def test_compaction_preserves_winning_ties_beyond_display_limit():
    matches = [{"score": 20 - i, "qualified": False, "class_label": "Ia", "metric_direction": "higher"}
               for i in range(12)]
    matches += [{"score": 2, "qualified": True, "class_label": c, "metric_direction": "higher"}
                for c in ("Ia", "II", None)]
    record = {"status": "completed", "reason": "", "candidates": matches}
    assert engine_vote(compact_record(record, 10)) == engine_vote(record) == {}
    record["candidates"].pop()
    assert engine_vote(compact_record(record, 10)) == engine_vote(record) == {"Ia": .5, "II": .5}


def test_review_reads_verified_results_without_writing(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    out = tmp_path / "out"
    run_batch(manifest_factory([source_factory("good", z="0.1"), source_factory("blocked", "SN-B", frame="unknown", flux=3)]), config_factory(), out)
    before = {str(p): file_hash(p) for p in out.rglob("*") if p.is_file()}
    snap = read_snapshot(out)
    assert overview(snap)["runs"] == {"completed": 1, "blocked": 1}
    assert overview(snap)["classes"] == {"Ia": 1, "No suggestion": 1}
    detail = object_detail(snap, "SN-A")
    assert detail["spectra"][0]["fits"][0]["matches"][0]["native_class"] == "Ia"
    assert observed_spectrum(snap, "good")["points"][0] == [3000.0, 1.0]
    assert not observed_spectrum(snap, "blocked")["available"]
    assert before == {str(p): file_hash(p) for p in out.rglob("*") if p.is_file()}


def test_review_rejects_changed_evidence_and_inputs(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    out = tmp_path / "out"
    row = source_factory(z="0.1")
    run_batch(manifest_factory([row]), config_factory(), out)
    snap = read_snapshot(out)
    Path(row["path"]).write_text("3000 55\n5000 22\n9000 23\n")
    assert "changed" in observed_spectrum(snap, row["spectrum_id"])["reason"]
    next((out / "attempts").rglob("stdout.log")).write_text("tampered")
    snap = read_snapshot(out)
    assert overview(snap)["runs"] == {"invalid_evidence": 1}
    assert object_detail(snap, "SN-A")["object"]["proposed_class"] is None
    plan = read_json(out / "plan.json")
    plan["spectra"][0]["object_id"] = "wrong"
    write_json(out / "plan.json", plan)
    with pytest.raises(ValueError, match="integrity"):
        read_snapshot(out)


def test_review_api_filters_bounds_and_unknown_ids(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from spectypus.review import create_app
    out = tmp_path / "out"
    rows = [{**source_factory("a", z=".1"), "batch": "chen"}, {**source_factory("b", "SN-B", frame="unknown", flux=4), "batch": "gomez"}]
    run_batch(manifest_factory(rows), config_factory(), out)
    with TestClient(create_app(out, cache_seconds=0)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/api/objects", params={"label": "Ia"}).json()["total"] == 1
        assert client.get("/api/objects", params={"batch": "gomez", "review": True}).json()["rows"][0]["object_id"] == "SN-B"
        assert client.get("/api/objects", params={"q": "missing"}).json()["total"] == 0
        assert client.get("/api/objects?limit=1000").status_code == 422
        assert client.get("/api/object?object_id=../etc/passwd").status_code == 404
        assert client.get("/api/spectrum?spectrum_id=missing").status_code == 404
        assert client.post("/api/summary").status_code == 405


def test_repeated_spectrum_is_visible_but_counted_once(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    out = tmp_path / "out"
    a = source_factory("a", z=".1")
    b = {**a, "spectrum_id": "b"}
    run_batch(manifest_factory([a, b]), config_factory(), out)
    snap = read_snapshot(out)
    assert overview(snap)["runs"] == {"completed": 1, "duplicate": 1}
    assert object_detail(snap, "SN-A")["object"]["unique_spectrum_count"] == 1


def test_thousand_spectrum_partial_campaign_is_paginated(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from spectypus.review import create_app
    base = source_factory(frame="unknown")
    rows = [{**base, "spectrum_id": f"s{i:04d}", "object_id": f"SN-{i:04d}"} for i in range(1000)]
    out = tmp_path / "out"
    run_batch(manifest_factory(rows), config_factory(), out, execute=False)
    with TestClient(create_app(out)) as client:
        summary = client.get("/api/summary").json()
        assert summary["objects"] == summary["spectra"] == 1000
        assert summary["runs"] == {"blocked": 1000}
        assert summary["classes"] == {"No suggestion": 1000}
        page = client.get("/api/objects?offset=990&limit=50&review=true").json()
        assert page["total"] == 1000 and len(page["rows"]) == 10
        assert page["rows"][0]["object_id"] == "SN-0990"
