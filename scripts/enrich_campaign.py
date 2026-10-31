#!/usr/bin/env python3
"""Attach catalogue membership and explicit ZTF/date-window queue priorities."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re

from spectypus.io import read_csv, write_csv, write_json, file_hash


def date_mjd(value):
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc).timestamp() / 86400 + 40587
    except (ValueError, TypeError):
        return None


def row_epoch(row):
    for key in ('peak_mjd', 'first_jd', 'source_peak_time'):
        try:
            value = float(row.get(key, ''))
        except (ValueError, TypeError):
            continue
        if key == 'first_jd' and value > 2400000:
            value -= 2400000.5
        if key == 'source_peak_time':
            kind = row.get('source_peak_time_system', '').lower()
            if kind == 'bts_peakt': value += 57999.5
            elif kind == 'jd' and value > 2400000: value -= 2400000.5
            elif kind not in {'mjd', 'jd'}: continue
        if __import__('math').isfinite(value): return value, key
    return date_mjd(row.get('discovery_date_ut')), 'discovery_date_ut'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign', type=Path, required=True)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--start', default='2018-03-17')
    p.add_argument('--end', default='2026-01-01')
    args = p.parse_args()
    lo, hi = date_mjd(args.start), date_mjd(args.end)
    if lo is None or hi is None or lo >= hi: p.error('invalid date interval')
    module_path = args.source_root / 'Development/01_sample_revision/webpage/slsn_sample_atlas/spectra_library.py'
    spec = importlib.util.spec_from_file_location('atlas_spectra', module_path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    lib = module.SpectralLibrary(args.source_root)
    records = {r['source_id']: r for r in lib.records()}
    _, metadata = lib._aliases()
    rows = read_csv(args.campaign / 'spectra.csv')
    for row in rows:
        record = records[row['spectrum_id']]
        catalogues = [c for alias in record['aliases'] for c in metadata.get(alias, [])]
        members = sorted({c.get('sample') or Path(c['_catalog_path']).parent.name for c in catalogues
                          if Path(c['_catalog_path']).name == 'objects.csv'})
        ztf = record['ztf_id'].split(';')[0]
        name = record['object_name'] or row['object_id']
        epochs = sorted({(value, source, c['_catalog_path']) for c in catalogues
                         for value, source in [row_epoch(c)] if value is not None})
        years = [int(m.group(1)) for a in record['aliases'] for m in [re.fullmatch(r'(20\d{2})[A-Z]+', a)] if m]
        if not years and ztf: years = [2000+int(ztf[3:5])]
        in_window = any(lo <= epoch < hi for epoch, _, _ in epochs)
        method = 'catalogue date proxy' if epochs else 'name-year proxy' if years else 'unknown'
        if not epochs and years: in_window = int(args.start[:4]) <= min(years) < int(args.end[:4])
        row.update(samples=json.dumps(members), ztf_id=ztf,
                   tns_name=name if re.fullmatch(r'SN\d{4}[A-Za-z]+', name) else '',
                   priority_ztf='true' if ztf and in_window else 'false',
                   priority_start=args.start, priority_end=args.end,
                   priority_date_method=method, date_evidence=json.dumps(epochs))
    write_csv(args.campaign / 'spectra.csv', rows, list(rows[0]))
    write_json(args.campaign / 'priority.json', {'start_inclusive': args.start, 'end_exclusive': args.end,
        'policy': 'ZTF identifier plus catalogue peak/observation/discovery date proxy; name-year fallback as in source atlas. Priority only, no records discarded.',
        'input_sha256': file_hash(args.campaign / 'spectra.csv'),
        'priority_objects': len({r['object_id'] for r in rows if r['priority_ztf']=='true'}),
        'source_loader_sha256': file_hash(module_path)})
    print('Enriched',len(rows),'records')


if __name__ == '__main__': main()
