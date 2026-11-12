"""Bounded native-import and plot dependency probes; no fitting or downloads."""
import json
import os
import shutil
import subprocess
import sys
import time


def import_probe(python, modules):
    code = """import importlib,json,time
results=[]
for name in __import__('sys').argv[1:]:
    start=time.perf_counter()
    try:
        importlib.import_module(name)
        results.append(dict(module=name,status='ready',seconds=time.perf_counter()-start))
    except Exception as exc:
        results.append(dict(module=name,status='unavailable',reason=str(exc),seconds=time.perf_counter()-start))
print(json.dumps(results))
"""
    start = time.perf_counter()
    result = subprocess.run([str(python), '-c', code, *modules], capture_output=True,
                            text=True, timeout=60, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    if result.returncode:
        raise ValueError(f'Native import probe failed: {result.stderr[-3000:]}')
    rows = json.loads(result.stdout.splitlines()[-1])
    return {'imports': rows, 'elapsed_seconds': time.perf_counter() - start,
            'status': 'ready' if all(r['status'] == 'ready' for r in rows) else 'unavailable'}


def native_probe(name, settings):
    modules = ['numpy', 'scipy.linalg', 'pandas', 'astropy', 'matplotlib']
    modules += ['snid_sage', 'h5py'] if name == 'snid_sage' else ['extinction', 'PyAstronomy']
    return import_probe(settings['python'], modules)


def plot_probe():
    result = import_probe(os.environ.get('SPECTYPUS_PLOT_PYTHON', sys.executable),
                          ['matplotlib', 'scipy', 'scienceplots', 'pypalettes'])
    result['executables'] = {name: shutil.which(name) for name in ('latex', 'dvipng')}
    if not all(result['executables'].values()):
        result['status'] = 'unavailable'
    result['remedy'] = "Install spectypus[plots] and a TeX distribution providing latex and dvipng; cached exports do not require these."
    return result
