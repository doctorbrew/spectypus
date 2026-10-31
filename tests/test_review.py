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


def test_engine_mode_buttons_distinguish_finished_no_match_and_pending():
    from spectypus.review import fit_states
    runs=[{'engine':'ngsf','mode':'fixed','status':'completed'},
          {'engine':'ngsf','mode':'fixed','status':'no_good_match'},
          {'engine':'ngsf','mode':'free','status':'failed'},
          {'engine':'snid_sage','mode':'fixed','status':'pending'}]
    s=fit_states(runs)
    assert s['ngsf']['fixed']['finished'] and s['ngsf']['fixed']['no_good_match']==1
    assert not s['ngsf']['free']['finished'] and s['ngsf']['free']['status']=='failed'
    assert s['snid_sage']['free']['status']=='not requested'


def test_ztf_sample_and_date_filters_use_explicit_membership(tmp_path,source_factory,manifest_factory,config_factory,fake_engine):
    pytest.importorskip('fastapi');pytest.importorskip('httpx')
    from fastapi.testclient import TestClient
    from spectypus.review import create_app
    from spectypus.io import write_csv
    base=source_factory(z='.1');row={**base,'samples':'["chen", "fritz"]','ztf_id':'ZTF18abcdefg','tns_name':'SN2018abc','priority_ztf':'true'}
    path=tmp_path/'sources.csv';write_csv(path,[row],list(row));out=tmp_path/'out';run_batch(path,config_factory(),out)
    with TestClient(create_app(out)) as c:
        assert c.get('/api/objects?ztf=true&priority=true&sample=chen&q=ZTF18').json()['total']==1
        assert c.get('/api/objects?sample=gomez').json()['total']==0
        assert c.get('/api/fit?execution_id=unknown').status_code==404


def test_fit_curve_requires_verified_matching_candidate(tmp_path,source_factory,manifest_factory,config_factory,fake_engine):
    from spectypus.review import fit_curve
    out=tmp_path/'out';run_batch(manifest_factory([source_factory(z='.1')]),config_factory(),out)
    path=next((out/'attempts').rglob('record.json'));record=read_json(path)
    curve=path.with_name('fit_curves.json')
    write_json(curve,{'schema':'spectypus-fit-curves/1','engine':'snid_sage','flux_unit':'normalized','curves':[
        {'template':'template-A','score':5.,'available':True,'observed':[[3000,1],[9000,2]],'model':[[3000,1],[9000,2]]}]})
    record['artifacts']['fit_curves.json']=file_hash(curve);write_json(path,record);path.with_name('record.sha256').write_text(file_hash(path)+'\n')
    snapshot=read_snapshot(out);run=snapshot['runs'][0]
    assert fit_curve(snapshot,run['execution_id'])['available']
    curve.write_text('{}')
    assert not fit_curve(snapshot,run['execution_id'])['available']


def test_viewer_completion_waits_for_diagnostic_free_fits(tmp_path,source_factory,manifest_factory,config_factory,fake_engine):
    out=tmp_path/'out';run_batch(manifest_factory([source_factory(z='.1')]),config_factory(redshift_mode='both'),out,max_runs=1)
    obj=read_snapshot(out)['summary']['objects'][0]
    assert obj['primary_complete'] and not obj['complete'] and obj['needs_review']
