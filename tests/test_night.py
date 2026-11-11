from __future__ import annotations

import sys
from pathlib import Path

import pytest

from spectypus.cli import main
from spectypus.io import file_hash, read_json, write_csv, write_json
from spectypus.night import installation_config


@pytest.fixture
def nightly(tmp_path, monkeypatch, config_factory, fake_engine):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPECTYPUS_CONFIG", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    config = config_factory()
    settings = read_json(config)
    settings["engines"]["ngsf"] = {"python": sys.executable, "root": str(tmp_path)}
    write_json(tmp_path / "spectypus.local.json", settings)
    # Use both adapter parsers and real attempt bookkeeping, with synthetic subprocesses.
    from spectypus.adapters import engines
    parameters = tmp_path / "parameters.json"
    write_json(parameters, {})
    monkeypatch.setattr(engines, "fingerprint", lambda name, cfg: {
        "source_sha256": "fake-v1", "bank_sha256": "bank-v1",
        **({"parameters_sha256": file_hash(parameters)} if name == "ngsf" else {})})
    sage_command = engines.build_command
    ngsf_script = tmp_path / "fake_ngsf.py"
    ngsf_script.write_text(
        "import sys\nfrom pathlib import Path\n"
        "Path(sys.argv[1]).write_text('SN,CHI2/dof2,Z,Phase,GALAXY\\nIa/SN-test/epoch,1.23,0.1,5,SB2\\n')\n")

    def command(run, config, directory):
        if run["engine"] == "snid_sage":
            return sage_command(run, config, directory)
        result = directory / "candidates.csv"
        return [sys.executable, str(ngsf_script), str(result)], directory, result

    monkeypatch.setattr(engines, "build_command", command)
    folder = tmp_path / "2026-10-28"
    folder.mkdir()
    (folder / "SN-A.txt").write_text("3000 1\n5000 2\n9000 1\n")
    (folder / "SN-B.txt").write_text("3000 2\n5000 1\n9000 2\n")
    return folder


def test_folder_alone_runs_both_engines_preserves_inputs_and_resumes(nightly):
    original = {p.name: p.read_bytes() for p in nightly.iterdir()}
    # An archived nested spectrum must not become an extra input.
    archived = nightly / "archive"
    archived.mkdir()
    (archived / "old.txt").write_text("invalid old reduction")
    assert main(["night", str(nightly)]) == 0
    output = nightly / "spectypus"
    plan = read_json(output / "plan.json")
    assert {s["object_id"] for s in plan["spectra"]} == {"SN-A", "SN-B"}
    assert all(s["redshift"] is None for s in plan["spectra"])
    assert all(s["wavelength_frame"] == "observer" and s["wavelength_unit"] == "angstrom"
               and "profile" in s["frame_source"] for s in plan["spectra"])
    assert len(plan["runs"]) == 4
    assert {(r["engine"], r["mode"]) for r in plan["runs"]} == {("snid_sage", "free"), ("ngsf", "free")}
    assert plan["config"]["save_fit_curves"] is True
    summary = read_json(output / "summary.json")
    assert summary["invocation"]["executed"] == 4
    assert summary["run_counts"]["completed"] == 4
    records = {p: p.read_bytes() for p in (output / "attempts").rglob("record.json")}
    assert main(["night", str(nightly)]) == 0
    resumed = read_json(output / "summary.json")
    assert resumed["invocation"]["executed"] == 0
    assert resumed["invocation"]["reused"] == 4
    assert records == {p: p.read_bytes() for p in (output / "attempts").rglob("record.json")}
    assert plan["plan_id"] == read_json(output / "plan.json")["plan_id"]
    assert len(list((output / ".inputs").glob("*.csv"))) == 1
    assert {p.name: p.read_bytes() for p in nightly.iterdir() if p.is_file()} == original
    assert not list(output.rglob("*.pdf"))


def test_known_redshifts_and_custom_selection(nightly, tmp_path):
    (nightly / "SN-C.asci").write_text("300 1\n500 2\n900 1\n")
    targets = tmp_path / "redshifts.csv"
    write_csv(targets, [{"object_id": "SN-C", "redshift": 0, "redshift_source": "test catalogue"}],
              ["object_id", "redshift", "redshift_source"])
    output = tmp_path / "custom-results"
    assert main(["night", str(nightly), "--pattern", "*.asci", "--unit", "nm",
                 "--frame", "rest", "--targets", str(targets), "--z-min", "0.01",
                 "--z-max", "0.31", "--z-step", "0.05", "--output", str(output), "--plan-only"]) == 0
    plan = read_json(output / "plan.json")
    assert len(plan["spectra"]) == 1
    spectrum = plan["spectra"][0]
    assert spectrum["redshift"] == 0 and spectrum["redshift_source"] == "test catalogue"
    assert spectrum["staging"]["wavelength_scale"] == 10
    assert len(plan["runs"]) == 4
    assert {r["mode"] for r in plan["runs"]} == {"fixed", "free"}
    assert plan["config"]["free_redshift"] == {"min": 0.01, "max": 0.31, "step": 0.05}
    assert not (output / "attempts").exists()


def test_changed_selection_and_input_keep_previous_evidence(nightly):
    args = ["night", str(nightly)]
    assert main(args) == 0
    output = nightly / "spectypus"
    records = {p: p.read_bytes() for p in (output / "attempts").rglob("record.json")}
    previous = read_json(output / "plan.json")
    (nightly / "SN-B.txt").write_text("3000 4\n5000 8\n9000 3\n")
    (nightly / "SN-C.txt").write_text("3000 2\n5000 9\n9000 6\n")
    assert main(args) == 0
    summary = read_json(output / "summary.json")
    assert summary["invocation"]["executed"] == 4
    assert summary["invocation"]["reused"] == 2
    assert all(p.read_bytes() == content for p, content in records.items())
    assert (output / "plans" / f"{previous['plan_id']}.json").exists()
    assert Path(previous["manifest"]).is_file()
    assert len(list((output / ".inputs").glob("*.csv"))) == 2


def test_max_runs_and_fixed_mode(nightly):
    assert main(["night", str(nightly), "--max-runs", "1"]) == 0
    output = nightly / "spectypus"
    assert read_json(output / "summary.json")["invocation"]["executed"] == 1
    assert main(["night", str(nightly), "--mode", "fixed"]) == 1
    plan = read_json(output / "plan.json")
    assert all(r["blocked_reason"] == "fixed mode requires a known redshift" for r in plan["runs"])


@pytest.mark.parametrize("options", [["--pattern", "*.missing"], ["--pattern", "**/*.txt"],
                                  ["--z-step", "0"], ["--z-max", "nan"], ["--max-runs", "0"]])
def test_invalid_options_make_no_output(nightly, options):
    assert main(["night", str(nightly), *options]) == 2
    assert not (nightly / "spectypus").exists()


def test_malformed_spectrum_is_blocked_without_modification(nightly):
    bad = nightly / "SN-A.txt"
    bad.write_text("3000 nan\n5000 1\n9000 2\n")
    assert main(["night", str(nightly)]) == 1
    plan = read_json(nightly / "spectypus" / "plan.json")
    assert "nonfinite" in next(s for s in plan["spectra"] if s["object_id"] == "SN-A")["blocked_reason"]
    assert "nan" in bad.read_text()


def test_configuration_selection_and_missing_setup(nightly, tmp_path, monkeypatch, capsys):
    local = tmp_path / "spectypus.local.json"
    user = Path.home() / ".config/spectypus/config.json"
    write_json(user, read_json(local))
    assert installation_config() == local
    assert installation_config(user) == user
    monkeypatch.setenv("SPECTYPUS_CONFIG", str(user))
    assert installation_config() == user
    assert installation_config(local) == local
    monkeypatch.setenv("SPECTYPUS_CONFIG", str(tmp_path / "missing.json"))
    assert main(["night", str(nightly)]) == 2
    assert "One-time setup" in capsys.readouterr().err
    assert not (nightly / "spectypus").exists()
    monkeypatch.delenv("SPECTYPUS_CONFIG")
    local.unlink()
    assert installation_config() == user
    assert main(["night", str(nightly), "--plan-only"]) == 0


def test_auto_manifest_tampering_is_not_silently_overwritten(nightly):
    assert main(["night", str(nightly), "--plan-only"]) == 0
    manifest = next((nightly / "spectypus/.inputs").glob("*.csv"))
    manifest.write_text("modified evidence")
    assert main(["night", str(nightly)]) == 2
    assert manifest.read_text() == "modified evidence"


def test_colliding_filename_labels_and_input_output_overlap_are_rejected(nightly):
    (nightly / "SN-A.asci").write_text("3000 2\n5000 3\n9000 4\n")
    assert main(["night", str(nightly), "--pattern", "*"]) == 2
    assert main(["night", str(nightly), "--output", str(nightly)]) == 2
    assert not (nightly / "spectypus").exists()
