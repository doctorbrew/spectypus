"""Read saved EFOSpec science exports without importing or running its reducer."""
from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path

from .io import file_hash, read_json
from .phases import number

FLUX_UNIT = 'erg s^-1 cm^-2 Angstrom^-1'
UNIT_SOURCE = 'EFOSpec native_raw_calibration_daily_standards ASCII export: Angstrom'


def typing_metadata(manifest: Path, expected_hash: str) -> dict:
    """Optional, revision-bound metadata produced by EFOSpec; no HTML scraping."""
    path = manifest.parent / 'typing-metadata.json'
    if not path.exists():
        return {}
    metadata = read_json(path)
    if (metadata.get('schema') != 'efospec-typing-metadata/1'
            or metadata.get('reduction_manifest_sha256') != expected_hash
            or file_hash(manifest) != expected_hash or metadata.get('night') != read_json(manifest).get('night')):
        raise ValueError('EFOSpec typing metadata belongs to a different reduction')
    result = {}
    for item in metadata['spectra']:
        spectrum = (manifest.parent / item['path']).resolve()
        if not spectrum.is_relative_to(manifest.parent.resolve()) or file_hash(spectrum) != item['source_sha256']:
            raise ValueError('EFOSpec typing metadata spectrum hash/path mismatch')
        if str(spectrum) in result:
            raise ValueError('Repeated EFOSpec typing metadata spectrum')
        fields = {k: item[k] for k in ('object_id', 'tns_name', 'discovery_mjd', 'discovery_source',
                                     'discovery_survey', 'instrument', 'spectrum_url') if k in item}
        if item.get('host_status') == 'accepted':
            if not item.get('host_name') or not item.get('host_source'):
                raise ValueError('Accepted host needs a name and sourced cross-match')
            fields.update({k: item[k] for k in ('host_name', 'host_redshift', 'host_source') if k in item})
        adopted = number(item.get('adopted_redshift'))
        if item.get('adopted_redshift') not in (None, '') and (adopted is None or adopted < 0):
            raise ValueError('Adopted redshift must be finite and nonnegative')
        if adopted is not None:
            kind = item.get('adopted_redshift_kind')
            if (kind not in {'host_catalogue', 'narrow_lines', 'transient_spectral'}
                    or item.get('redshift_status') != 'accepted' or not item.get('adopted_redshift_source')):
                raise ValueError('Adopted redshift needs accepted status, kind and provenance')
            if kind == 'host_catalogue' and (item.get('host_status') != 'accepted' or
                                           number(item.get('host_redshift')) != adopted):
                raise ValueError('Adopted host redshift disagrees with accepted host cross-match')
            fields.update(redshift=adopted, redshift_source=item['adopted_redshift_source'], redshift_kind=kind)
            if kind == 'narrow_lines':
                fields.update(narrow_line_redshift=adopted, narrow_line_redshift_source=item['adopted_redshift_source'])
        fields['efosc_typing_metadata'] = {'path': str(path), 'sha256': file_hash(path), 'record': item}
        result[str(spectrum)] = fields
    return result


def science_exports(folder: Path, pattern: str | None = None) -> list[dict] | None:
    """Recognize a nightly root, processing revision, reduction or products folder.

    Only the selected run's science results are eligible. Rescue/archived
    revisions are not merged, and raw data folders are not reduction outputs.
    """
    pointer = folder / "nightly" / "current.json"
    if pointer.is_file():
        selection = read_json(pointer)
        revision = (pointer.parent / selection["revision"]).resolve()
        if revision.parent != pointer.parent or selection.get("night") != folder.name:
            raise ValueError("invalid EFOSpec nightly revision pointer")
        manifest = revision / "reduction" / "run.json"
        if not manifest.is_file():
            raise ValueError(f"selected EFOSpec revision has no reduction manifest: {manifest}")
    else:
        candidates = [folder / "run.json", folder / "reduction" / "run.json"]
        if folder.name == "products":
            candidates.insert(0, folder.parent / "run.json")
        manifest = next((p for p in candidates if p.is_file()), None)
        if manifest is None:
            return None
    run = read_json(manifest)
    if run.get("schema_version") != 1 or run.get("method") != "native_raw_calibration_daily_standards":
        raise ValueError(f"unsupported EFOSpec reduction manifest: {manifest}")
    if pointer.is_file() and run.get("night") != selection["night"]:
        raise ValueError("EFOSpec run and nightly pointer disagree on observing date")
    source_hash = file_hash(manifest)
    annotations = typing_metadata(manifest, source_hash)
    rows = []
    for record in run["results"]:
        if record.get("role") != "science":
            continue
        if record.get("status") == "PROVISIONAL" or record.get("wavelength_validated") is False:
            raise ValueError("unvalidated provisional EFOSpec wavelengths require a separately reviewed input")
        product = Path(record["product"]).expanduser()
        if not product.is_absolute():
            product = manifest.parent / product
        path = product.with_suffix(".asci").resolve()
        if not path.is_relative_to(manifest.parent.resolve()):
            raise ValueError(f"EFOSpec product is outside its reduction: {path}")
        if pattern is not None and not fnmatchcase(path.name, pattern):
            continue
        if not path.is_file():
            raise ValueError(f"missing EFOSpec ASCII counterpart: {path}")
        if record.get("reference_frame") != "topocentric" or record.get("output_wavelength_medium") != "air":
            raise ValueError("unsupported EFOSpec wavelength convention; explicit reviewed manifest required")
        name = str(record.get("object", "")).strip()
        if not name:
            raise ValueError(f"EFOSpec science product lacks object identity: {path}")
        row = {"spectrum_id": path.name, "object_id": name, "path": str(path),
               "wavelength_frame": "observer", "wavelength_unit": "angstrom", "batch": run["night"],
               "object_id_source": "EFOSpec run object", "frame_source": "EFOSpec run reference_frame=topocentric",
               "unit_source": UNIT_SOURCE,
               "flux_unit": FLUX_UNIT, "flux_unit_source": 'EFOSpec native_raw_calibration_daily_standards export contract',
               "wavelength_medium": "air", "reduction_status": record.get("status", ""),
               "reduction_execution_status": run.get("execution_status", ""),
               "efosc_manifest": str(manifest), "efosc_manifest_sha256": source_hash}
        if record.get("date_obs"):
            stamp = datetime.fromisoformat(record["date_obs"].replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
            row["mjd"] = stamp.timestamp() / 86400 + 40587
        metadata = annotations.get(str(path), {})
        if metadata and metadata['object_id'] != name:
            raise ValueError('EFOSpec typing metadata object identity mismatch')
        row.update(metadata)
        rows.append(row)
    if not rows:
        raise ValueError("no exported EFOSpec science spectra match this selection")
    if len({r["spectrum_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate spectrum identities in EFOSpec science exports")
    return sorted(rows, key=lambda row: row["spectrum_id"])
