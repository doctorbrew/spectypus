"""Explicit provisioning of external assets; never called by fitting or imports."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from http.client import HTTPException
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen
import zipfile

from .config import EXAMPLE, load_config


SAGE_VERSION = "1.2.3"
SAGE_URL = f"https://github.com/FiorenSt/SNID-SAGE/releases/download/v{SAGE_VERSION}/templates-v{SAGE_VERSION}.zip"
# Digest published with the upstream v1.2.3 release asset.
SAGE_SHA256 = "4a8480fa829270ffe413172a1bd1ad39405a34eff03be23b2313d4b0ddd32a33"
NGSF_REVISION = "b78cfe083fd79def6f6dcbcc9bf7f6b63825de31"
NGSF_URL = f"https://codeload.github.com/oyaron/NGSF/zip/{NGSF_REVISION}"
NGSF_SHA256 = "f7a17ae04ec9cf397dac68b3291cee7487ab845ea1ab0ab58325473f78863eef"
# Published in oyaron/NGSF's NGSF/tests/test_fit.py. No upstream digest supplied.
NGSF_BANK_URL = "https://www.wiserep.org/sites/default/files/supyfit_bank.zip"
MAX_DOWNLOAD = 2 * 1024**3
MAX_EXTRACTED = 8 * 1024**3
MAX_MEMBERS = 200_000


def _download(url: str, destination: Path, expected: str | None = None) -> dict:
    digest = hashlib.sha256()
    size = 0
    try:
        request = Request(url, headers={"User-Agent": "Spectypus-template-setup"})
        with urlopen(request, timeout=60) as response, destination.open("xb") as stream:
            if not response.url.startswith("https://"):
                raise ValueError("template downloads must remain on HTTPS")
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise ValueError("template download exceeds the 2 GiB limit")
                digest.update(chunk)
                stream.write(chunk)
    except (URLError, TimeoutError, HTTPException) as exc:
        raise ValueError(
            f"download failed for {url}: {exc}. See docs/TEMPLATE_SETUP.md; "
            "for WISeREP use --ngsf-bank-archive PATH or --ngsf-root PATH."
        ) from exc
    actual = digest.hexdigest()
    if expected and actual != expected:
        raise ValueError(f"SHA-256 mismatch for {url}; refusing to install")
    return {"url": url, "sha256": actual, "bytes": size,
            "checksum_verified": expected is not None}


def _extract(archive: Path, destination: Path) -> None:
    """Extract regular ZIP files only, with bounded size and no escaping paths."""
    try:
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_EXTRACTED:
                raise ValueError("template archive exceeds extraction limits")
            seen = set()
            for member in members:
                path = PurePosixPath(member.filename)
                kind = stat.S_IFMT(member.external_attr >> 16)
                if (path.is_absolute() or ".." in path.parts or "\\" in member.filename
                        or ":" in member.filename or not path.parts
                        or kind not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise ValueError(f"unsafe archive entry: {member.filename!r}")
                if path in seen:
                    raise ValueError(f"duplicate archive entry: {member.filename!r}")
                seen.add(path)
            for member in members:
                target = destination.joinpath(*PurePosixPath(member.filename).parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(member) as src, target.open("xb") as dst:
                        shutil.copyfileobj(src, dst)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError(f"not a valid ZIP archive: {archive}") from exc


def _find_root(directory: Path, marker: str) -> Path:
    matches = list(directory.rglob(marker))
    if len(matches) != 1:
        raise ValueError(f"expected one {marker} in archive, found {len(matches)}")
    return matches[0].parent


def _validate_sage(root: Path) -> None:
    index = json.loads((root / "template_index.json").read_text())
    templates = index.get("templates") if isinstance(index, dict) else None
    if not isinstance(templates, dict) or not templates:
        raise ValueError(f"empty or invalid SAGE template index: {root}")
    files = set()
    for entry in templates.values():
        name = entry.get("storage_file") if isinstance(entry, dict) else None
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".hdf5"):
            raise ValueError(f"invalid SAGE storage file in {root}")
        files.add(name)
    for name in files:
        with (root / name).open("rb") as stream:
            if stream.read(8) != b"\x89HDF\r\n\x1a\n":
                raise ValueError(f"invalid SAGE HDF5 file: {root / name}")


def _validate_ngsf(root: Path) -> None:
    for name in ("run.py", "NGSF/sf_class.py", "parameters.json"):
        if not (root / name).is_file():
            raise ValueError(f"missing NGSF source: {root / name}")
    params = json.loads((root / "parameters.json").read_text())
    if not isinstance(params, dict):
        raise ValueError("NGSF parameters must be a JSON object")
    resolution = params.get("resolution", 10)
    if not isinstance(resolution, (int, float)) or resolution <= 0:
        raise ValueError("invalid NGSF resolution")
    for directory in {"original_resolution", "binnings/30A", f"binnings/{resolution:g}A"}:
        for kind in ("sne", "gal"):
            folder = root / "bank" / directory / kind
            if not folder.is_dir() or not any(p.is_file() for p in folder.rglob("*")):
                raise ValueError(f"missing or empty NGSF templates: {folder}")


def _install(destination: Path, populate, validate, progress) -> Path:
    if destination.exists() or destination.is_symlink():
        validate(destination)
        progress(f"Using existing assets: {destination}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".spectypus-setup-", dir=destination.parent) as temp:
        staged, provenance = populate(Path(temp))
        validate(staged)
        (staged / "spectypus-download.json").write_text(json.dumps(provenance, indent=2) + "\n")
        # Refuse another invocation's completed installation, including empty dirs.
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"destination appeared during setup: {destination}; retry")
        staged.rename(destination)
    progress(f"Installed assets: {destination}")
    return destination


def setup(*, config: Path, data_dir: Path, engine: str = "both",
          snid_templates: Path | None = None, ngsf_root: Path | None = None,
          ngsf_bank_archive: Path | None = None, progress=print) -> dict:
    """Download missing assets or register local ones, then create a new config."""
    config = config.expanduser().absolute()
    if config.exists() or config.is_symlink():
        raise ValueError(f"refusing to overwrite {config}; reuse it or choose a new --config path")
    if engine not in ("both", "snid-sage", "ngsf"):
        raise ValueError("unknown setup engine")
    if ngsf_root and ngsf_bank_archive:
        raise ValueError("use either --ngsf-root or --ngsf-bank-archive")
    if engine == "snid-sage" and (ngsf_root or ngsf_bank_archive) or engine == "ngsf" and snid_templates:
        raise ValueError("local asset options conflict with --engine")
    if ngsf_bank_archive:
        ngsf_bank_archive = ngsf_bank_archive.expanduser().resolve(strict=True)
        if not zipfile.is_zipfile(ngsf_bank_archive):
            raise ValueError("--ngsf-bank-archive must be a ZIP file")
    # Check explicit paths before any network activity; never populate these paths.
    if snid_templates:
        snid_templates = snid_templates.expanduser().resolve(strict=True)
        _validate_sage(snid_templates)
    if ngsf_root:
        ngsf_root = ngsf_root.expanduser().resolve(strict=True)
        _validate_ngsf(ngsf_root)
    data_dir = data_dir.expanduser().resolve()
    settings = deepcopy(EXAMPLE)
    for name, values in settings["engines"].items():
        values["enabled"] = engine == "both" or name == engine.replace("-", "_")
        # Resolve the directory, not the executable symlink: preserve venv identity.
        values["python"] = str(Path(sys.executable).absolute())

    if settings["engines"]["snid_sage"]["enabled"]:
        if snid_templates is None:
            try:
                installed = version("snid-sage")
            except PackageNotFoundError as exc:
                raise ValueError("install the engines extra or environment.yml before downloading SAGE templates") from exc
            if installed != SAGE_VERSION:
                raise ValueError(f"managed templates require SNID-SAGE {SAGE_VERSION}; found {installed}. Use --snid-templates for a compatible existing bank")

            def sage(temp):
                progress(f"Downloading SNID-SAGE {SAGE_VERSION} templates (about 268 MB)…")
                archive = temp / "sage.zip"
                record = _download(SAGE_URL, archive, SAGE_SHA256)
                _extract(archive, temp / "unpacked")
                return _find_root(temp / "unpacked", "template_index.json"), record

            snid_templates = _install(data_dir / f"sage-{SAGE_VERSION}", sage, _validate_sage, progress)
        settings["engines"]["snid_sage"]["templates"] = str(snid_templates)

    if settings["engines"]["ngsf"]["enabled"]:
        if ngsf_root is None:
            def ngsf(temp):
                progress(f"Downloading NGSF source at {NGSF_REVISION}…")
                source_zip = temp / "source.zip"
                source_record = _download(NGSF_URL, source_zip, NGSF_SHA256)
                _extract(source_zip, temp / "source")
                root = _find_root(temp / "source", "parameters.json")
                archive = ngsf_bank_archive
                if archive is None:
                    progress("Downloading the NGSF bank from WISeREP…")
                    archive = temp / "bank.zip"
                    bank_record = _download(NGSF_BANK_URL, archive)
                else:
                    digest = hashlib.sha256()
                    with archive.open("rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                    bank_record = {"local_archive": str(archive), "sha256": digest.hexdigest(),
                                   "checksum_verified": False}
                _extract(archive, temp / "templates")
                bank = _find_root(temp / "templates", "original_resolution")
                bank.rename(root / "bank")
                return root, {"revision": NGSF_REVISION, "source": source_record, "bank": bank_record}

            ngsf_root = _install(data_dir / f"ngsf-{NGSF_REVISION[:12]}", ngsf, _validate_ngsf, progress)
        settings["engines"]["ngsf"].update(root=str(ngsf_root), parameters=str(ngsf_root / "parameters.json"))

    load_config(settings)
    config.parent.mkdir(parents=True, exist_ok=True)
    with config.open("x") as stream:
        stream.write(json.dumps(settings, indent=2) + "\n")
    progress(f"Wrote {config}. Review the redshift range before fitting.")
    progress(f"Check dependencies and assets: spectypus doctor --config {config}")
    return settings
