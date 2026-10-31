from __future__ import annotations

import json
from pathlib import Path

import pytest

from spectypus.io import read_json
from spectypus.pipeline import current_record, make_plan, output_lock, run_batch, summarize_output
from conftest import sage_payload


def test_routing_auto_both_missing_and_zero(source_factory, manifest_factory, config_factory, fake_engine):
    manifest = manifest_factory([source_factory("a", z="0"), source_factory("b", "SN-B", flux=2)])
    plan = make_plan(manifest, config_factory())
    assert [(r["spectrum_id"], r["mode"]) for r in plan["runs"]] == [("a", "fixed"), ("b", "free")]
    plan = make_plan(manifest, config_factory(redshift_mode="both"))
    assert [(r["spectrum_id"], r["mode"], r["primary"]) for r in plan["runs"]] == [
        ("a", "fixed", True), ("a", "free", False), ("b", "free", True)]


@pytest.mark.parametrize("z,mode,maximum,blocked", [
    ("1.2", "auto", 1.0, True),
    ("1.0", "auto", 1.0, False),
    ("0", "auto", 1.0, False),
    ("", "auto", 1.5, True),
    ("", "auto", 1.0, False),
    ("0.5", "auto", 1.5, False),  # unused free range must not block fixed fits
])
def test_sage_optical_redshift_support_preserves_ngsf(
        z, mode, maximum, blocked, source_factory, manifest_factory,
        config_factory, fake_engine, tmp_path):
    config = read_json(config_factory(redshift_mode=mode,
                       free_redshift={"min": 0, "max": maximum, "step": 0.01}))
    config["engines"]["ngsf"] = {"python": config["engines"]["snid_sage"]["python"],
                                  "root": str(tmp_path)}
    plan = make_plan(manifest_factory([source_factory(z=z)]), config)
    runs = {r["engine"]: r for r in plan["runs"]}
    assert bool(runs["snid_sage"]["blocked_reason"]) is blocked
    if blocked:
        assert "redshift" in runs["snid_sage"]["blocked_reason"]
    assert not runs["ngsf"]["blocked_reason"]


def test_dictionary_config_validated_disabled_engine_ignored_and_plan_detached(
        source_factory, manifest_factory, config_factory, fake_engine):
    manifest = manifest_factory([source_factory()])
    config = read_json(config_factory())
    config["engines"]["ngsf"] = {"enabled": False}
    plan = make_plan(manifest, config)
    assert [r["engine"] for r in plan["runs"]] == ["snid_sage"]
    assert "ngsf" not in plan["config"]["engines"]
    config["free_redshift"]["max"] = 2.0
    config["engines"]["snid_sage"]["threshold"] = 999
    assert plan["config"]["free_redshift"]["max"] == 1.0
    assert plan["config"]["engines"]["snid_sage"]["threshold"] == 1.5
    config["top_n"] = -2
    with pytest.raises(ValueError, match="top_n"):
        make_plan(manifest, config)


def test_plan_never_executes_and_retains_blocked(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    manifest = manifest_factory([source_factory("a"), source_factory("b", frame="unknown", flux=2)])
    output = tmp_path / "out"
    summary = run_batch(manifest, config_factory(), output, execute=False)
    assert summary["run_counts"] == {"blocked": 1, "pending": 1}
    assert not (output / "attempts").exists()
    assert len(summary["spectra"]) == 2


def test_execute_resume_and_artifact_tamper(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    manifest, cfg, out = manifest_factory([source_factory(z="0.1")]), config_factory(), tmp_path / "out"
    first = run_batch(manifest, cfg, out)
    assert first["invocation"]["executed"] == 1 and first["all_runs_terminal"]
    assert first["objects"][0]["proposed_class"] == "Ia"
    second = run_batch(manifest, cfg, out)
    assert second["invocation"] == {"executed": 0, "reused": 1, "execution_requested": True, "max_runs": None}
    plan = read_json(out / "plan.json")
    prior = current_record(out, plan["runs"][0])
    native = Path(prior["attempt_path"]) / "candidates.json"
    native.write_text("tampered")
    assert current_record(out, plan["runs"][0]) is None
    third = run_batch(manifest, cfg, out)
    assert third["invocation"]["executed"] == 1
    assert native.read_text() == "tampered"  # prior evidence is retained, never overwritten


def test_record_tampering_is_rejected(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    manifest, cfg, out = manifest_factory([source_factory()]), config_factory(), tmp_path / "out"
    run_batch(manifest, cfg, out)
    plan = read_json(out / "plan.json")
    record = current_record(out, plan["runs"][0])
    path = Path(record["attempt_path"]) / "record.json"
    payload = read_json(path)
    payload["candidates"][0]["class_label"] = "SLSN-I"
    path.write_text(json.dumps(payload))
    summary = summarize_output(out)
    assert summary["run_counts"] == {"pending": 1}
    assert summary["objects"][0]["status"] == "unclassified"


def test_failed_attempt_retry_retains_old_trial(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    fake_engine.write_text("import sys\nprint('deliberate engine failure',file=sys.stderr)\nsys.exit(7)\n")
    manifest, cfg, out = manifest_factory([source_factory()]), config_factory(), tmp_path / "out"
    first = run_batch(manifest, cfg, out)
    assert first["run_counts"] == {"failed": 1}
    payload = sage_payload()
    fake_engine.write_text(f"import sys,json\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps({payload!r}))\n")
    second = run_batch(manifest, cfg, out)
    assert second["run_counts"] == {"completed": 1}
    plan = read_json(out / "plan.json")
    assert len(list((out / "attempts" / plan["runs"][0]["execution_id"]).glob("*/record.json"))) == 2


def test_timeout_is_failure_not_no_match(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    fake_engine.write_text("import time\ntime.sleep(30)\n")
    manifest = manifest_factory([source_factory()])
    out = tmp_path / "out"
    summary = run_batch(manifest, config_factory(timeout_seconds=.05), out)
    assert summary["run_counts"] == {"failed": 1}
    record = current_record(out, read_json(out / "plan.json")["runs"][0])
    assert record["reason"] == "timeout" and record["elapsed_seconds"] < 5


def test_semantic_sage_no_good_match_reusable(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    payload = sage_payload(success=False, score=.1)
    fake_engine.write_text(f"import sys,json\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps({payload!r}))\nprint('No good matches found')\nsys.exit(1)\n")
    manifest, cfg, out = manifest_factory([source_factory()]), config_factory(), tmp_path / "out"
    summary = run_batch(manifest, cfg, out)
    assert summary["run_counts"] == {"no_good_match": 1}
    assert summary["objects"][0]["status"] == "unclassified"
    assert summary["objects"][0]["complete"]
    assert run_batch(manifest, cfg, out)["invocation"]["reused"] == 1


def test_partial_run_and_current_plan_no_stale_evidence(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    a, b = source_factory("a"), source_factory("b", "SN-B", flux=2)
    manifest, cfg, out = manifest_factory([a, b]), config_factory(), tmp_path / "out"
    limited = run_batch(manifest, cfg, out, max_runs=1)
    assert limited["run_counts"] == {"completed": 1, "pending": 1}
    assert not limited["all_runs_terminal"]
    manifest_factory([b])
    second = run_batch(manifest, cfg, out)
    assert len(second["objects"]) == 1 and second["objects"][0]["object_id"] == "SN-B"
    assert "SN-A" not in (out / "matches.csv").read_text()


def test_config_and_input_change_invalidate_resume(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    row = source_factory()
    manifest, cfg, out = manifest_factory([row]), config_factory(), tmp_path / "out"
    run_batch(manifest, cfg, out)
    id1 = read_json(out / "plan.json")["runs"][0]["execution_id"]
    cfg = config_factory(top_n=5)
    assert run_batch(manifest, cfg, out)["invocation"]["executed"] == 1
    id2 = read_json(out / "plan.json")["runs"][0]["execution_id"]
    assert id1 != id2
    Path(row["path"]).write_text("3000 4\n5000 5\n9000 6\n")
    assert run_batch(manifest, cfg, out)["invocation"]["executed"] == 1
    assert read_json(out / "plan.json")["runs"][0]["execution_id"] != id2


@pytest.mark.parametrize("stage", ["before", "after"])
@pytest.mark.parametrize("component", ["source_sha256", "bank_sha256", "runtime"])
def test_engine_drift_fails_closed(stage, component, source_factory, manifest_factory, config_factory,
                                  fake_engine, tmp_path, monkeypatch):
    from spectypus.adapters import engines
    calls = 0
    def fingerprint(name, cfg):
        nonlocal calls
        calls += 1
        result = {"source_sha256": "source-v1", "bank_sha256": "bank-v1", "runtime": "runtime-v1"}
        if calls >= (2 if stage == "before" else 3):
            result[component] = "changed"
        return result
    monkeypatch.setattr(engines, "fingerprint", fingerprint)
    out = tmp_path / "out"
    summary = run_batch(manifest_factory([source_factory()]), config_factory(), out)
    assert summary["run_counts"] == {"failed": 1}
    assert summary["objects"][0]["status"] == "unclassified"
    record = current_record(out, read_json(out / "plan.json")["runs"][0])
    assert record["reason"] == f"ValueError: engine provenance changed {stage} execution"
    assert record["candidates"] == []
    assert (Path(record["attempt_path"]) / "stdout.log").exists() == (stage == "after")


@pytest.mark.parametrize("stage", ["before", "after"])
def test_package_drift_fails_closed(stage, source_factory, manifest_factory, config_factory,
                                   fake_engine, tmp_path, monkeypatch):
    import spectypus.pipeline as pipeline
    calls = 0
    def package_hash(*args, **kwargs):
        nonlocal calls
        calls += 1
        return "changed" if calls >= (2 if stage == "before" else 3) else "original"
    monkeypatch.setattr(pipeline, "tree_hash", package_hash)
    out = tmp_path / "out"
    summary = run_batch(manifest_factory([source_factory()]), config_factory(), out)
    assert summary["run_counts"] == {"failed": 1}
    record = current_record(out, read_json(out / "plan.json")["runs"][0])
    assert record["reason"] == f"ValueError: Spectypus source changed {stage} execution"
    assert record["candidates"] == []


def test_duplicate_spectrum_has_one_attempt(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    manifest = manifest_factory([source_factory("a"), source_factory("copy")])
    summary = run_batch(manifest, config_factory(), tmp_path / "out")
    assert summary["invocation"]["executed"] == 1
    assert summary["all_runs_terminal"]
    assert summary["objects"][0]["duplicate_count"] == 1


def test_output_lock_rejects_concurrent_writer(tmp_path):
    with output_lock(tmp_path):
        with pytest.raises(ValueError, match="another writer"):
            with output_lock(tmp_path):
                pass


def test_saved_plan_integrity_is_verified(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    out = tmp_path / "out"
    run_batch(manifest_factory([source_factory()]), config_factory(), out, execute=False)
    plan = read_json(out / "plan.json")
    plan["config"]["top_n"] = 100
    (out / "plan.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="integrity"):
        summarize_output(out)


def test_top_ten_output_preserves_all_native_candidates(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    payload = sage_payload()
    base = payload["candidates"][0]
    payload["candidates"] = [{**base, "template_name": f"T{i}", "score_value": i + 2} for i in range(15)]
    fake_engine.write_text(f"import sys,json\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps({payload!r}))\n")
    out = tmp_path / "out"
    run_batch(manifest_factory([source_factory()]), config_factory(), out)
    from spectypus.io import read_csv
    rows = read_csv(out / "matches.csv")
    assert len(rows) == 10 and [float(r["score"]) for r in rows] == list(range(16, 6, -1))
    record = current_record(out, read_json(out / "plan.json")["runs"][0])
    assert len(record["candidates"]) == 15
