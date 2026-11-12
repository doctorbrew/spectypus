"""Content-addressed master JPGs, cached independently of scientific attempts."""
import os
import gzip
import json
from pathlib import Path
import subprocess
import sys

from ..io import atomic_text, canonical, digest, file_hash, read_json, write_json
from .products import product_ready


def preparation_identity(record_sha256):
    root = Path(__file__).parent
    return digest({'record': record_sha256, 'implementation': {n: file_hash(root / n) for n in
                   ('plot_worker.py', 'display.py', 'native_ngsf.py')}})


def ensure_grid(output, source, run, record, attempt):
    if not record or not run['matches'] or 'fit_curves.json' not in record['artifacts']:
        return {'status': 'unavailable', 'reason': 'No saved model curves'}
    payload = read_json(attempt / 'fit_curves.json')
    if not any(c.get('available') for c in payload.get('curves', [])):
        return {'status': 'unavailable', 'reason': 'No saved model curves'}
    implementation = Path(__file__).parent
    # Renderer versions do not invalidate native classification identities.
    identity = digest({'record': run['record_sha256'], 'source': source,
                       'implementation': {n: file_hash(implementation / n) for n in
                                          ('plots.py', 'plot_worker.py', 'grids.py', 'display.py', 'limits.py', 'products.py', 'native_ngsf.py')},
                       'style': file_hash(implementation.parent / 'plot_style.py')})
    destination = Path(output) / 'figures' / identity
    result_path = destination / 'product.json'
    if result_path.is_file():
        result = read_json(result_path)
        if (result.get('identity') == identity and product_ready(destination, result)
                and file_hash(destination / 'request.json.gz') == result.get('request_sha256')):
            return {**result, 'directory': str(destination)}
    destination.mkdir(parents=True, exist_ok=True)
    job = {'source': source, 'execution_id': run['execution_id'], 'record_sha256': run['record_sha256'],
           'engine': run['engine'], 'mode': run['mode'], 'attempt': str(attempt), 'identity': identity,
           'request': str(destination / 'request.json.gz'), 'stem': str(destination / 'master'),
           'result': str(result_path)}
    job_path = destination / 'job.json'
    write_json(job_path, job)
    prepared = Path(output) / 'figures' / '.prepared' / (preparation_identity(run['record_sha256']) + '.json.gz')
    prepared_hash = prepared.with_suffix('.sha256')
    reuse_prepared = False
    if prepared.is_file() and prepared_hash.is_file() and file_hash(prepared) == prepared_hash.read_text().strip():
        request = json.loads(gzip.decompress(prepared.read_bytes()))
        if request['record_sha256'] == run['record_sha256']:
            request['source'] = source
            Path(job['request']).write_bytes(gzip.compress(canonical(request).encode(), mtime=0))
            reuse_prepared = True
    # Share one report-owned cache, never copy caches into fit evidence.
    env = {**os.environ, 'MPLBACKEND': 'Agg', 'PYTHONDONTWRITEBYTECODE': '1',
           'MPLCONFIGDIR': str(Path(output) / '.plot-cache' / 'matplotlib'),
           'XDG_CACHE_HOME': str(Path(output) / '.plot-cache' / 'xdg')}
    code = 'import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("spectypus.reporting.plot_worker",run_name="__main__")'
    try:
        for action, python in [('prepare', record['config']['engines'][run['engine']]['python']),
                               ('render', os.environ.get('SPECTYPUS_PLOT_PYTHON', sys.executable))]:
            if action == 'prepare' and reuse_prepared:
                continue
            with (destination / (action + '.log')).open('w') as log:
                process = subprocess.run([python, '-c', code, str(implementation.parents[1]), action, str(job_path)],
                                         env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
            if process.returncode:
                raise ValueError(f'{action} failed; see figures/{identity}/{action}.log')
            if action == 'prepare':
                prepared.parent.mkdir(parents=True, exist_ok=True)
                # Derived numerical requests are small; never write through a
                # hard link into native evidence or another render's request.
                prepared.write_bytes(Path(job['request']).read_bytes())
                atomic_text(prepared_hash, file_hash(prepared) + '\n')
        result = read_json(result_path)
        if not product_ready(destination, result):
            raise ValueError('Generated JPG failed validation')
        return {**result, 'directory': str(destination)}
    except (OSError, ValueError, subprocess.SubprocessError, ImportError) as exc:
        result = {'status': 'unavailable', 'identity': identity, 'reason': str(exc)}
        write_json(result_path, result)
        return result
