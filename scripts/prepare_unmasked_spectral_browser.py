#!/usr/bin/env python3
"""Restore display-only NGSF model samples from verified banks and saved parameters.

Bounded to the existing saved candidates. Never calls a fit/search routine or
modifies engine code, banks, original attempts, or source numerical requests.
Run in the existing spectypus environment; render afterward in .venv-plots.
"""
import argparse
from collections import Counter
from functools import lru_cache
import gzip
import json
import math
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.dont_write_bytecode = True
from spectypus.io import canonical, digest, file_hash, read_json, tree_hash, write_json
from build_spectral_browser import prepare_browser
from spectypus.reporting.native_ngsf import restore_missing_model, native_grid_value, recover_curve_coefficients, NativeNGSF




def atomic_gzip(path, payload):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.complete-model-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(gzip.compress(canonical(payload).encode(), compresslevel=3, mtime=0))
        # Replaces the new export's hard link; never writes through to its source.
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)








def prepare(source, output, audit, resume=False):
    source, output, audit = source.resolve(), output.resolve(), audit.resolve()
    if resume:
        frozen = read_json(output / 'browser-snapshot.json')
        if frozen['presentation_source']['directory'] != str(source):
            raise ValueError('Resume source mismatch')
    else:
        if output.exists() or audit.exists():
            raise ValueError('Use fresh output and audit directories')
        audit.mkdir(parents=True)
        frozen = prepare_browser(source, output)
    os.environ['MPLCONFIGDIR'] = str(audit / 'plot-cache')
    checks = read_json(source / 'checksums.json')
    native = None; stats = Counter(); restorations = []; verified_records = {}; failures = []
    for snapshot in frozen['snapshots']:
        for run in snapshot['runs']:
            if not run['curve_ranks']: continue
            path = output / 'data' / (run['plot_key'] + '.json.gz')
            request = json.loads(gzip.decompress(path.read_bytes()))
            if run['engine'] == 'ngsf':
                attempt = Path(run['attempt_path']); record_path = attempt / 'record.json'
                if file_hash(record_path) != run['record_sha256']:
                    raise ValueError('Frozen native record changed')
                record = read_json(record_path); params_path = attempt / 'parameters.json'
                if file_hash(params_path) != record['artifacts']['parameters.json']:
                    raise ValueError('Saved NGSF parameters changed')
                params = read_json(params_path)
                if params['mask_galaxy_lines']:
                    raise ValueError('Unreviewed template-line masking in saved configuration')
                if native is None:
                    native = NativeNGSF(Path(snapshot['config']['engines']['ngsf']['root']), params_path, record['provenance'])
                native.verify(record['provenance'])
                if Path(snapshot['config']['engines']['ngsf']['root']).resolve() != native.root:
                    raise ValueError('Multiple NGSF roots require separate verification')
                verified_records[run['plot_key']] = {'record_sha256': run['record_sha256'], 'parameters_sha256': file_hash(params_path)}
                stdout = attempt / 'stdout.log'
                if file_hash(stdout) != record['artifacts']['stdout.log']:
                    raise ValueError('Saved NGSF execution log changed')
                resolution = 30 if 'NGSF failed. Retrying for resolution = 30' in stdout.read_text() else params['resolution']
                request_failed = False
                for match in request['matches']:
                    if not match['curve']['available']: continue
                    try:
                        points, info = native.reconstruct(match, params, resolution)
                    except Exception as exc:
                        failure = {'plot_key': run['plot_key'], 'rank': match['candidate']['rank'], 'attempt': str(attempt), 'candidate': match['candidate'], 'parameters': params, 'error': str(exc)}
                        failures.append(failure); request_failed = True
                        write_json(audit / 'failed-models.json', failures)
                        print(f"Unresolved model {run['plot_key']} rank {match['candidate']['rank']}: {exc}", flush=True)
                        continue
                    match['curve']['display_model'] = points
                    match['curve']['display_model_provenance'] = info
                    restorations.append({'plot_key': run['plot_key'], 'rank': match['candidate']['rank'], **info})
                    stats['ngsf_panels'] += 1; stats['ngsf_samples_restored'] += info['restored_samples']
                    stats['ngsf_tied_curve_parameters_recovered'] += info['curve_parameters_recovered']
                    stats['ngsf_native_30A_retry_panels'] += resolution != params['resolution']
                if request_failed: continue
            else:
                stats['snid_panels'] += len(run['curve_ranks'])
            request['model_presentation'] = {'masking': 'none', 'source_request_sha256': checks['data/' + path.name],
                                           'note': 'No display mask. Native template coverage and SNID taper retained; no invented extension or refit.'}
            atomic_gzip(path, request)
            stats['requests'] += 1
            if stats['requests'] % 250 == 0: print(dict(stats), flush=True)
    if failures:
        raise ValueError(f'{len(failures)} models could not be verified; see failed-models.json')
    # Verify every original scientific field and source file after enrichment.
    for path in sorted((output / 'data').glob('*.json.gz')):
        if file_hash(source / 'data' / path.name) != checks['data/' + path.name]:
            raise ValueError('Original source request changed')
        old = json.loads(gzip.decompress((source / 'data' / path.name).read_bytes()))
        new = json.loads(gzip.decompress(path.read_bytes()))
        new.pop('model_presentation', None)
        for m in new['matches']:
            m['curve'].pop('display_model', None); m['curve'].pop('display_model_provenance', None)
        if new != old: raise ValueError('Scientific request fields changed during display enrichment')
    if native:
        if tree_hash(native.root / 'bank') != native.bank_hash: raise ValueError('Bank changed during reconstruction')
        if any(file_hash(Path(p)) != h for p, h in native.files.items()): raise ValueError('Template changed')
    write_json(audit / 'restored-models.json', restorations)
    write_json(audit / 'verified-records.json', verified_records)
    write_json(audit / 'template-files.json', native.files if native else {})
    report = {'status': 'passed', **stats, 'scientific_fields_unchanged': True, 'source_requests_unchanged': True,
              'classifier_runs': 0, 'preprocessing_replays': 0, 'scope': 'Saved native candidates only; display-only model restoration'}
    report['curve_parameter_recoveries'] = [{k: entry[k] for k in ('plot_key', 'rank', 'saved_parameters', 'evaluated_parameters')}
                                           for entry in restorations if entry['curve_parameters_recovered']]
    frozen['presentation_source']['note'] = 'Frozen scientific snapshots and original request fields preserved; verified unmasked model arrays added for display only.'
    write_json(output / 'browser-snapshot.json', frozen)
    write_json(audit / 'preparation.json', report)
    write_json(output / 'model-restoration.json', report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-browser', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audit-directory', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    prepare(args.from_browser, args.output, args.audit_directory, args.resume)
