#!/usr/bin/env python3
"""Freeze the existing SLSN atlas spectral union into Spectypus inputs.

This project bridge reads the source project only. It deliberately preserves
unknown frames/units and conflicting catalogue redshifts as unknown. The
standalone package does not depend on the source project's atlas implementation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import shutil

from spectypus.io import file_hash, read_csv, read_json, write_csv, write_json
from spectypus.manifest import FIELDS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.source_root.resolve(), args.output.resolve()
    if output.exists():
        parser.error("output already exists; choose a fresh campaign directory")
    stage = root / "Development/01_spectroscopicclassification"
    loader = root / "Development/01_sample_revision/webpage/slsn_sample_atlas/spectra_library.py"
    spec = importlib.util.spec_from_file_location("source_atlas_spectra", loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    library = module.SpectralLibrary(root)
    records = library.records()
    if library.issues:
        raise ValueError("Source archive requires repair: " + "; ".join(library.issues))
    inventory = {"fritz:" + r["spectrum_id"]: r for r in read_csv(stage / "data/fritz_spectra_atlas/spectrum_inventory.csv")}
    _, metadata = library._aliases()
    rows = []
    for r in records:
        if ";" in r["ztf_id"]:
            raise ValueError("Multiple ZTF identities need review: " + r["object_key"])
        path = r["_path"]
        if r["dataset"] == "fritz":
            item = inventory[r["source_id"]]
            # No synthetic numeric file for rejected Fritz arrays: keep the
            # original JSON reference and numerical rejection in the accounting.
            if item["dat_path"]:
                path = stage / "data/fritz_spectra_atlas" / item["dat_path"]
            input_reason = item["reason"]
        else:
            input_reason = ""
        unit = r["wavelength_unit"].lower().strip()
        unit = {"aa": "angstrom", "angstroms": "angstrom"}.get(unit, unit)
        evidence = sorted({(c["_catalog_path"], str(c.get("redshift", "")))
                           for a in r["aliases"] for c in metadata.get(a, []) if c.get("redshift")})
        source = r.get("redshift_source") or ("exact-alias catalogue agreement; see catalog_redshifts" if r["redshift"] is not None else "")
        rows.append({"spectrum_id": r["source_id"], "object_id": r["object_key"], "path": str(path),
                     "wavelength_frame": r["wavelength_frame"], "wavelength_unit": unit,
                     "redshift": r["redshift"], "redshift_source": source,
                     "batch": r["dataset"], "mjd": r["obs_mjd"], "phase_rest_days": r["phase_rest_days"],
                     "instrument": r["instrument"], "frame_source": r["frame_source"],
                     "aliases": r["aliases"], "catalog_redshifts": evidence,
                     "input_issue": input_reason, "source_id": r["source_id"],
                     "source_metadata_path": str(r["_path"]), "source_metadata_sha256": file_hash(r["_path"])})
    # All source records remain visible, including repeated/rejected spectra.
    output.mkdir(parents=True)
    fields = FIELDS + ["frame_source", "aliases", "catalog_redshifts", "input_issue", "source_id",
                       "source_metadata_path", "source_metadata_sha256"]
    write_csv(output / "spectra.csv", rows, fields)
    config = read_json(args.config)
    config["redshift_mode"] = "auto"
    config["timeout_seconds"] = 900  # Bound each fine free-redshift search.
    write_json(output / "config.json", config)
    inputs = sorted((root / "Development/01_sample_revision/data").glob("*/objects.csv"))
    inputs += [loader, library.manifest, root / "data/chen_spectralsample/ReadMe",
               stage / "data/fritz_spectra_atlas/run_summary.json",
               stage / "data/fritz_spectra_atlas/spectrum_inventory.csv",
               stage / "data/fritz_atlas_targets/targets.csv", args.config.resolve()]
    fritz_summary = read_json(stage / "data/fritz_spectra_atlas/run_summary.json")
    missing = [{"object_id": s["source_id"], "status": s["status"]}
               for s in fritz_summary["sources"] if s["status"] != "downloaded"]
    write_csv(output / "targets_without_fritz_spectra.csv", missing, ["object_id", "status"])
    report = {"schema": "spectypus-slsn-import/1", "tier": "exploratory",
              "scope": "All local Gomez, Chen and expanded Fritz atlas spectrum records; candidate catalogue, not confirmed classifications or a rate sample",
              "rows": len(rows), "objects": len({r["object_id"] for r in rows}),
              "sources": dict(Counter(r["batch"] for r in rows)),
              "frame_policy": "Chen publication ReadMe; other frames preserved from atlas, including header warnings. Unknown stays blocked.",
              "redshift_policy": "Existing spectrum redshift, otherwise exact alias catalogue agreement. Conflicts stay unknown; Spectypus propagates known object redshifts across epochs.",
              "identity_policy": "Existing atlas exact-alias graph; source channels retained in batch; numerical duplicates handled by Spectypus",
              "fritz_targets_without_downloads": len(missing),
              "input_hashes": {str(p): file_hash(p) for p in inputs},
              "spectra_sha256": file_hash(output / "spectra.csv")}
    write_json(output / "import.json", report)
    shutil.copyfile(loader, output / "atlas_loader.py.snapshot")
    print(json.dumps({k: report[k] for k in ("rows", "objects", "sources", "fritz_targets_without_downloads")}))


if __name__ == "__main__":
    main()
