#!/usr/bin/env python3
"""Freeze exact-alias catalogue phase references without modifying the run plan."""
import argparse
import importlib.util
import json
from pathlib import Path
from spectypus.io import file_hash, read_json, write_json
from spectypus.phases import references


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True, help='Existing run directory')
    p.add_argument('--source-root', type=Path, required=True)
    args = p.parse_args()
    path = args.output / 'review_metadata.json'
    if path.exists(): p.error('review metadata already exists; preserve it before preparing a new version')
    loader = args.source_root / 'Development/01_sample_revision/webpage/slsn_sample_atlas/spectra_library.py'
    spec = importlib.util.spec_from_file_location('atlas_spectra', loader)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    lib = module.SpectralLibrary(args.source_root)
    _, metadata = lib._aliases()
    plan = read_json(args.output / 'plan.json')
    objects, hashes = {}, {}
    for source in plan['spectra']:
        oid = source['object_id']
        if oid in objects: continue
        aliases = {a for s in plan['spectra'] if s['object_id'] == oid for a in json.loads(s.get('aliases') or '[]')}
        refs = []
        for alias in aliases:
            for row in metadata.get(alias, []):
                rel = row['_catalog_path']
                hashes[rel] = file_hash(args.source_root / rel)
                refs.extend(references(row, rel))
        objects[oid] = sorted({json.dumps(r, sort_keys=True) for r in refs})
        objects[oid] = [json.loads(r) for r in objects[oid]]
    write_json(path, {'plan_id': plan['plan_id'], 'objects': objects, 'catalogue_sha256': hashes,
                      'source_loader_sha256': file_hash(loader)})
    print(f'Saved {sum(bool(r) for r in objects.values())}/{len(objects)} objects with phase references to {path}')


if __name__ == '__main__': main()
