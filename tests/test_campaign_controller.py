import importlib.util
from pathlib import Path
import signal
import sys

import pytest

from spectypus.io import read_json
from spectypus.pipeline import output_lock


def controller():
    path = Path(__file__).resolve().parents[1] / "scripts/run_saved_campaign.py"
    spec = importlib.util.spec_from_file_location("campaign_controller", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_controller_stops_repeated_failures_preserves_remaining_queue(
        tmp_path, source_factory, manifest_factory, config_factory, fake_engine, monkeypatch):
    rows = [source_factory(f"s{i}", z=".1", flux=i+1) for i in range(7)]
    manifest_factory(rows).rename(tmp_path / "spectra.csv")
    config_factory()
    fake_engine.write_text("raise SystemExit(2)\n")
    monkeypatch.setattr(sys, "argv", ["controller", str(tmp_path)])
    handler = signal.getsignal(signal.SIGTERM)
    try:
        with pytest.raises(RuntimeError, match="six consecutive"):
            controller().main()
    finally:
        signal.signal(signal.SIGTERM, handler)
    status = read_json(tmp_path / "campaign_status.json")
    assert status["status"] == "stopped"
    assert status["completed_this_invocation"] == 6
    assert status["runs"] == {"failed": 6, "pending": 1}


def test_second_controller_does_not_overwrite_active_status(tmp_path, monkeypatch):
    status = tmp_path / "campaign_status.json"
    status.write_text('{"status":"running","pid":1234}')
    monkeypatch.setattr(sys, "argv", ["controller", str(tmp_path)])
    handler = signal.getsignal(signal.SIGTERM)
    try:
        with output_lock(tmp_path / "run"), pytest.raises(ValueError, match="another writer"):
            controller().main()
    finally:
        signal.signal(signal.SIGTERM, handler)
    assert read_json(status) == {"status": "running", "pid": 1234}
