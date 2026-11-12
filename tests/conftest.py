from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from spectypus.io import write_csv
from spectypus.manifest import FIELDS


@pytest.fixture(autouse=True)
def no_live_tns_credentials(monkeypatch):
    """Synthetic tests must never use the developer's live catalogue account."""
    for key in ('TNS_API_KEY', 'TNS_BOT_ID', 'TNS_BOT_NAME'):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def source_factory(tmp_path):
    def create(name="spectrum", object_id="SN-A", *, z="", frame="observer", unit="angstrom", flux=1.0):
        path = tmp_path / f"{name}.dat"
        path.write_text(f"3000 {flux}\n5000 {flux + 1}\n9000 {flux - 1}\n")
        return {"spectrum_id": name, "object_id": object_id, "path": str(path),
                "wavelength_frame": frame, "wavelength_unit": unit, "redshift": z}
    return create


@pytest.fixture
def manifest_factory(tmp_path):
    def create(rows):
        path = tmp_path / "manifest.csv"
        write_csv(path, rows, FIELDS)
        return path
    return create


@pytest.fixture
def config_factory(tmp_path):
    def create(**overrides):
        data = {"redshift_mode": "auto", "top_n": 10, "timeout_seconds": 10,
                "free_redshift": {"min": 0, "max": 1, "step": 0.01},
                "engines": {"snid_sage": {"python": sys.executable, "templates": str(tmp_path)}}}
        data.update(overrides)
        path = tmp_path / "config.json"
        path.write_text(json.dumps(data))
        return path
    return create


def sage_payload(*, success=True, score=5.0, label="Ia", subtype="Ia-norm"):
    return {"capture_status": "ok", "classification_success": success, "candidates": [
        {"template_name": "template-A", "template_epoch_id": "template-A@0", "type": label,
         "subtype": subtype, "age_days": 0, "redshift": 0.1, "metric_name": "hsigma_lap_ccc",
         "score_value": score, "passes_threshold": score >= 1.5}]}


@pytest.fixture
def fake_engine(monkeypatch, tmp_path):
    from spectypus.adapters import engines
    monkeypatch.setattr(engines, "fingerprint", lambda name, cfg: {"source_sha256": "fake-v1", "bank_sha256": "bank-v1"})
    script = tmp_path / "fake_engine.py"
    payload = sage_payload()
    script.write_text("import json,sys\nfrom pathlib import Path\n"
                      f"Path(sys.argv[1]).write_text(json.dumps({payload!r}))\nprint('engine completed')\n")
    def build(run, config, directory):
        result = directory / "candidates.json"
        return [sys.executable, str(script), str(result)], directory, result
    monkeypatch.setattr(engines, "build_command", build)
    return script
