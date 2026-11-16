"""Provisioning contracts: no fitting, no existing-asset mutation, safe archives."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import stat
import zipfile

import pytest

from spectypus.cli import main
from spectypus.config import load_config
from spectypus import setup as provisioning


def sage_bank(root):
    root.mkdir(parents=True)
    (root / "template_index.json").write_text(json.dumps({
        "templates": {"SN": {"storage_file": "templates_Ia.hdf5"}}}))
    (root / "templates_Ia.hdf5").write_bytes(b"\x89HDF\r\n\x1a\nfixture")
    return root


def ngsf_source(root):
    (root / "NGSF").mkdir(parents=True)
    (root / "NGSF/sf_class.py").write_text("# fixture")
    (root / "run.py").write_text("raise RuntimeError('setup must never run an engine')")
    (root / "parameters.json").write_text('{"resolution": 10}')
    return root


def ngsf_bank(root):
    for directory in ("original_resolution", "binnings/10A", "binnings/30A"):
        for kind in ("sne", "gal"):
            folder = root / directory / kind
            folder.mkdir(parents=True)
            (folder / "spectrum.dat").write_text("4000 1\n5000 2\n")
    return root


def archive_tree(path, root):
    with zipfile.ZipFile(path, "w") as archive:
        for file in root.rglob("*"):
            if file.is_file():
                archive.write(file, file.relative_to(root.parent))
    return path


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    banks = {
        provisioning.SAGE_URL: archive_tree(tmp_path / "sage.zip", sage_bank(tmp_path / "sage")),
        provisioning.NGSF_URL: archive_tree(tmp_path / "source.zip", ngsf_source(tmp_path / "source")),
        provisioning.NGSF_BANK_URL: archive_tree(tmp_path / "bank.zip", ngsf_bank(tmp_path / "bank")),
    }
    calls = []

    def download(url, destination, expected=None):
        calls.append(url)
        shutil.copyfile(banks[url], destination)
        return {"url": url, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}

    monkeypatch.setattr(provisioning, "_download", download)
    monkeypatch.setattr(provisioning, "version", lambda _: provisioning.SAGE_VERSION)
    return calls, banks


def test_setup_downloads_both_and_reuses_without_network(tmp_path, upstream):
    calls, _ = upstream
    config, assets = tmp_path / "config.json", tmp_path / "assets"
    assert main(["setup", "--config", str(config), "--data-dir", str(assets)]) == 0
    settings = load_config(config)
    assert set(settings["engines"]) == {"snid_sage", "ngsf"}
    assert len(calls) == 3
    for engine, key in (("snid_sage", "templates"), ("ngsf", "root")):
        assert (Path(settings["engines"][engine][key]) / "spectypus-download.json").is_file()
    second = tmp_path / "second.json"
    provisioning.setup(config=second, data_dir=assets)
    assert len(calls) == 3
    assert load_config(second) == settings


def test_registration_is_offline_and_does_not_change_external_assets(tmp_path, monkeypatch):
    sage = sage_bank(tmp_path / "existing-sage")
    ngsf = ngsf_source(tmp_path / "existing-ngsf")
    ngsf_bank(ngsf / "bank")
    before = {p: p.read_bytes() for root in (sage, ngsf) for p in root.rglob("*") if p.is_file()}
    monkeypatch.setattr(provisioning, "_download", lambda *a: pytest.fail("network access"))
    config = tmp_path / "settings.json"
    assert main(["setup", "--config", str(config), "--snid-templates", str(sage),
                 "--ngsf-root", str(ngsf), "--data-dir", str(tmp_path / "unused")]) == 0
    after = {p: p.read_bytes() for root in (sage, ngsf) for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert not (tmp_path / "unused").exists()


def test_existing_config_refused_before_download(tmp_path, upstream):
    config = tmp_path / "config.json"
    config.write_text("my configuration")
    assert main(["setup", "--config", str(config)]) == 2
    assert config.read_text() == "my configuration"
    assert upstream[0] == []


def test_missing_explicit_bank_not_populated(tmp_path, upstream):
    missing = tmp_path / "missing"
    assert main(["setup", "--config", str(tmp_path / "config.json"),
                 "--snid-templates", str(missing)]) == 2
    assert not missing.exists()
    assert upstream[0] == []


def test_failed_bank_download_keeps_completed_sage_and_no_config(tmp_path, upstream, monkeypatch):
    download = provisioning._download

    def fail_bank(url, *args):
        if url == provisioning.NGSF_BANK_URL:
            raise ValueError("HTTP 403")
        return download(url, *args)

    monkeypatch.setattr(provisioning, "_download", fail_bank)
    config, assets = tmp_path / "config.json", tmp_path / "assets"
    assert main(["setup", "--config", str(config), "--data-dir", str(assets)]) == 2
    assert not config.exists()
    assert [p.name for p in assets.iterdir()] == [f"sage-{provisioning.SAGE_VERSION}"]
    # A manually downloaded bank finishes the interrupted installation.
    assert main(["setup", "--config", str(config), "--data-dir", str(assets),
                 "--ngsf-bank-archive", str(upstream[1][provisioning.NGSF_BANK_URL])]) == 0
    assert upstream[0].count(provisioning.SAGE_URL) == 1


def test_single_engine_has_no_other_download(tmp_path, upstream):
    config = tmp_path / "config.json"
    provisioning.setup(config=config, data_dir=tmp_path / "assets", engine="snid-sage")
    assert list(load_config(config)["engines"]) == ["snid_sage"]
    assert upstream[0] == [provisioning.SAGE_URL]


@pytest.mark.parametrize("entry", ["../escape", "/absolute", "dir/../../escape", "dir\\escape", "C:/escape"])
def test_archive_paths_cannot_escape(tmp_path, entry):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(entry, "malicious")
    with pytest.raises(ValueError, match="unsafe"):
        provisioning._extract(archive, tmp_path / "unpacked")
    assert not (tmp_path / "unpacked").exists()


def test_symlinks_and_oversized_archives_rejected(tmp_path, monkeypatch):
    archive = tmp_path / "bad.zip"
    link = zipfile.ZipInfo("link")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(link, "../elsewhere")
    with pytest.raises(ValueError, match="unsafe"):
        provisioning._extract(archive, tmp_path / "unpacked")
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("large", "123456")
    monkeypatch.setattr(provisioning, "MAX_EXTRACTED", 5)
    with pytest.raises(ValueError, match="limits"):
        provisioning._extract(archive, tmp_path / "unpacked")


def test_download_verifies_digest_and_size(tmp_path, monkeypatch):
    def response(*args, **kwargs):
        stream = io.BytesIO(b"archive bytes")
        stream.url = "https://example.test/bank.zip"
        return stream

    monkeypatch.setattr(provisioning, "urlopen", response)
    digest = hashlib.sha256(b"archive bytes").hexdigest()
    record = provisioning._download("https://example.test/bank.zip", tmp_path / "ok", digest)
    assert record["checksum_verified"] and record["sha256"] == digest
    with pytest.raises(ValueError, match="SHA-256"):
        provisioning._download("https://example.test/bank.zip", tmp_path / "wrong", "0" * 64)
    monkeypatch.setattr(provisioning, "MAX_DOWNLOAD", 3)
    with pytest.raises(ValueError, match="limit"):
        provisioning._download("https://example.test/bank.zip", tmp_path / "big")


def test_invalid_managed_bank_is_preserved_and_not_replaced(tmp_path, upstream):
    assets = tmp_path / "assets"
    root = sage_bank(assets / f"sage-{provisioning.SAGE_VERSION}")
    (root / "templates_Ia.hdf5").write_text("incomplete")
    config = tmp_path / "config.json"
    assert main(["setup", "--engine", "snid-sage", "--config", str(config), "--data-dir", str(assets)]) == 2
    assert (root / "templates_Ia.hdf5").read_text() == "incomplete"
    assert not config.exists()
    assert upstream[0] == []
