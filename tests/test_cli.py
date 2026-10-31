from __future__ import annotations

from spectypus.cli import main
from spectypus.io import read_json


def test_init_never_overwrites(tmp_path):
    path = tmp_path / "settings.json"
    assert main(["init", "--config", str(path)]) == 0
    assert read_json(path)["redshift_mode"] == "auto"
    path.write_text("user settings")
    assert main(["init", "--config", str(path)]) == 2
    assert path.read_text() == "user settings"


def test_cli_plan_run_summarize(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    manifest, config, out = manifest_factory([source_factory()]), config_factory(), tmp_path / "out"
    common = ["--manifest", str(manifest), "--config", str(config), "--output", str(out)]
    assert main(["plan", *common]) == 0
    assert main(["run", *common, "--max-runs", "1"]) == 0
    assert main(["summarize", "--output", str(out)]) == 0
