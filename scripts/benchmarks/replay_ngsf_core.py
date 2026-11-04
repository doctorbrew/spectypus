"""Paired arithmetic timings on one saved A_v=0 grid point per real spectrum.

No template search, source-spectrum read, or campaign mutation occurs here.
Use five repetitions, alternating call order; exclude one warm-up pair. This
measures the reused arithmetic after error calculation and interpolation only.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import statistics
import time

for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
            'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'

import numpy as np
from astropy import table
import extinction

from ngsf_core_reuse import transform
from spectypus.io import file_hash, read_json, write_json
from spectypus.pipeline import current_record


def replay(root, output):
    if output.exists():
        raise ValueError('use a new replay output file')
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        os.nice(15 - os.getpriority(os.PRIO_PROCESS, 0))
    plan = read_json(root / 'fixed/core_reuse/plan.json')
    rows = []
    np.seterr(all='ignore')  # native code ignores invalid/divide warnings
    for item in plan['runs']:
        record = current_record(root / 'fixed/core_reuse', item)
        if record is None:
            raise ValueError('unverified stage-3 attempt')
        directory = Path(record['attempt_path'])
        metadata = read_json(directory / 'kernel_inputs.json')
        metrics = read_json(directory / 'benchmark_metrics.json')
        source = Path(metadata['native_source'])
        if file_hash(source) != metrics['native_functions_sha256']:
            raise ValueError('native source changed')
        definitions = [n for n in ast.parse(source.read_text()).body
                       if isinstance(n, ast.FunctionDef) and n.name in ('core', 'Alam')]
        native_code = ast.fix_missing_locations(ast.Module(body=definitions, type_ignores=[]))
        core = next(n for n in definitions if n.name == 'core')
        with np.load(directory / 'kernel_inputs.npz', allow_pickle=False) as payload:
            arrays = {k: payload[k] for k in payload.files}
        namespace = {'np': np, 'os': os, 'table': table,
                     'extinction': extinction, 'apply': extinction.apply,
                     'error_obj': lambda *a: arrays['sigma'],
                     'sn_hg_arrays': lambda *a: (arrays['sn'], arrays['gal'])}
        exec(compile(native_code, str(source), 'exec'), namespace)
        baseline = namespace['core']
        optimized_namespace = dict(namespace)
        exec(compile(transform(ast.unparse(core)), '<reused-expressions>', 'exec'), optimized_namespace)
        optimized = optimized_namespace['core']
        args = (arrays['observed'], metadata['z'], metadata['extcon'], metadata['sn_keys'], {},
                metadata['gal_keys'], {}, {}, arrays['lam'], metadata['resolution'], metadata['iterations'])
        timings = []
        for repeat in range(6):
            durations, results = {}, {}
            order = [('native', baseline), ('reuse', optimized)]
            if repeat % 2:
                order.reverse()
            for name, function in order:
                wall, cpu = time.perf_counter(), time.process_time()
                result = function(*args, **metadata['kwargs'])
                durations[name] = {'cpu_seconds': time.process_time() - cpu,
                                   'wall_seconds': time.perf_counter() - wall}
                results[name] = result
            for name in results['native'][0].colnames:
                np.testing.assert_array_equal(results['native'][0][name], results['reuse'][0][name])
            np.testing.assert_array_equal(results['native'][1], results['reuse'][1])
            if repeat:
                timings.append(durations)
        row = {'spectrum_id': item['spectrum_id'], 'object_id': item['object_id'],
               'z': metadata['z'], 'extcon': metadata['extcon'],
               'shapes': {k: list(v.shape) for k, v in arrays.items()},
               'all_exact': True, 'repetitions': timings,
               'median_native_cpu_seconds': statistics.median(t['native']['cpu_seconds'] for t in timings),
               'median_reuse_cpu_seconds': statistics.median(t['reuse']['cpu_seconds'] for t in timings),
               'median_paired_cpu_ratio': statistics.median(t['native']['cpu_seconds']/t['reuse']['cpu_seconds'] for t in timings)}
        rows.append(row)
        print(f"{item['object_id']}: paired arithmetic {row['median_paired_cpu_ratio']:.2f}x; exact", flush=True)
    write_json(output, {'scope': 'one saved full-template A_v=0 grid point for each of five spectra; five measured pairs plus one warm-up pair each',
                        'limitations': 'excludes interpolation, error estimation, input loading, provenance checks and output I/O; not end-to-end speedup or full-grid timing',
                        'all_exact': True, 'rows': rows,
                        'median_spectrum_cpu_ratio': statistics.median(r['median_paired_cpu_ratio'] for r in rows)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    replay(args.root, args.output)
