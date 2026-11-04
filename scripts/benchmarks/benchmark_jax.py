"""Isolated, bounded JAX CPU/64-bit test on verified saved NGSF arrays.

Also measure float32 as a negative precision control. NumPy's native sorting
is applied to both score matrices to isolate numerical changes from sort policy.
No live fit, bank read or production-environment mutation takes place.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import sys
import time

for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
            'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS',
            'TF_NUM_INTRAOP_THREADS', 'TF_NUM_INTEROP_THREADS'):
    os.environ[key] = '1'
os.environ['JAX_PLATFORMS'] = 'cpu'
os.environ['JAX_ENABLE_X64'] = 'true'
os.environ['JAX_CPU_ENABLE_ASYNC_DISPATCH'] = 'false'
os.environ['NPROC'] = '1'
os.environ['XLA_FLAGS'] = ('--xla_cpu_multi_thread_eigen=false '
                         '--xla_cpu_enable_fast_math=false '
                         '--xla_cpu_parallel_codegen_split_count=1 '
                         '--xla_force_host_platform_device_count=1 '
                         'intra_op_parallelism_threads=1 inter_op_parallelism_threads=1')

import numpy as np
from jax_ngsf_kernel import native_reference, make_jax_kernel, compare, arithmetic, edge_fixtures, RTOL, ATOL
from spectypus.io import read_json, write_json, file_hash
from spectypus.pipeline import current_record


def fixtures(fixed, free):
    result = []
    for root, folder, pattern in [(fixed, 'fixed/core_reuse', 'kernel_inputs.npz'),
                                   (free, 'run', 'kernel_z*.npz')]:
        if root is None:
            continue
        plan = read_json(root / folder / 'plan.json')
        for item in plan['runs']:
            record = current_record(root / folder, item)
            if record is None:
                raise ValueError('source numerical fixture has unverified attempt evidence')
            directory = Path(record['attempt_path'])
            for path in sorted(directory.glob(pattern)):
                metadata = read_json(path.with_suffix('.json'))
                metrics = read_json(directory / 'benchmark_metrics.json')
                source = Path(metadata['native_source'])
                if file_hash(source) != metrics['native_functions_sha256']:
                    raise ValueError('native source changed since fixture capture')
                result.append({'path': path, 'metadata': metadata, 'object_id': item['object_id'],
                               'spectrum_id': item['spectrum_id'], 'record_sha256': file_hash(directory / 'record.json'),
                               'kind': 'fixed' if root == fixed else 'free'})
    return result


def prepare(fixed, free, root, chunk_templates=8):
    inputs = fixtures(fixed, free)
    expected = 5 + (15 if free else 0)
    if len(inputs) != expected:
        raise ValueError(f'expected {expected} fixtures, found {len(inputs)}')
    if len({file_hash(Path(item['metadata']['native_source'])) for item in inputs}) != 1:
        raise ValueError('fixtures come from different native arithmetic versions')
    root.mkdir(parents=True, exist_ok=False)
    (root / 'inputs').mkdir()
    (root / 'experiment').mkdir()
    manifest, files = [], {}
    for i, item in enumerate(inputs):
        destination = root / 'inputs' / f'fixture_{i:02d}.npz'
        shutil.copy2(item['path'], destination)
        write_json(destination.with_suffix('.json'), item['metadata'])
        manifest.append({**{k: v for k, v in item.items() if k not in ('path', 'metadata')},
                         'source_path': str(item['path']), 'path': str(destination.relative_to(root)),
                         'z': item['metadata']['z'], 'extcon': item['metadata']['extcon']})
        for path in (destination, destination.with_suffix('.json')):
            files[str(path.relative_to(root))] = file_hash(path)
    native_source = root / 'native_source.py'
    shutil.copy2(inputs[0]['metadata']['native_source'], native_source)
    files['native_source.py'] = file_hash(native_source)
    for name in ('benchmark_jax.py', 'jax_ngsf_kernel.py'):
        path = root / 'experiment' / name
        shutil.copy2(Path(__file__).with_name(name), path)
        files[str(path.relative_to(root))] = file_hash(path)
    write_json(root / 'contract.json', {
        'scope': f'{expected} saved full-template grid-point fixtures; no new classification fits',
        'fixtures': manifest, 'files': files, 'repetitions': 5, 'chunk_templates': chunk_templates,
        'rtol': RTOL, 'atol': ATOL, 'platform': platform.platform(), 'python': sys.version,
        'acceptance': 'identical NaN/Inf masks, exact sample counts and ordered top-10 indices; all finite fields within preregistered tolerance',
        'precision_modes': ['float64', 'float32'], 'float32_role': 'negative precision control, not proposed production mode',
        'backend': 'CPU', 'x64': True, 'xla_flags': os.environ['XLA_FLAGS'],
        'nproc': 1, 'async_dispatch': False, 'dynamic_overlap_divisor': True,
        'bounds': f'one low-priority process; {chunk_templates}-template chunks; five repetitions; stop if warm CPU/wall ratio exceeds 1.5',
        'timed_implementations': ['native_numpy', 'reuse_numpy', 'chunked_reuse_numpy', 'jax'],
        'limitations': 'arithmetic only; no interpolation, template loading, table reconstruction, whole-search ranking or GPU timing'})
    print(root, flush=True)


def run(root):
    contract = read_json(root / 'contract.json')
    for name, checksum in contract['files'].items():
        if file_hash(root / name) != checksum:
            raise ValueError(f'frozen benchmark input/code changed: {name}')
    if any((root / name).exists() for name in ('started.json', 'progress.json', 'results.json', 'edge_checks.json')):
        raise ValueError('preserve completed or partial results; prepare a new trial')
    write_json(root / 'started.json', {'pid': os.getpid(), 'contract_sha256': file_hash(root / 'contract.json')})
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        os.nice(15 - os.getpriority(os.PRIO_PROCESS, 0))
    import jax
    kernel = make_jax_kernel()
    if jax.default_backend() != 'cpu' or not jax.config.x64_enabled:
        raise ValueError('expected 64-bit CPU JAX')
    reference = native_reference((root / 'native_source.py').read_text())
    np.seterr(all='ignore')
    rows = []
    compiled_shapes = set()
    edge_checks = {}
    for name, args in edge_fixtures().items():
        expected = reference(*args)
        actual = jax.block_until_ready(kernel(*args))
        edge_checks[name] = compare(expected, actual)
    write_json(root / 'edge_checks.json', edge_checks)
    versions = {name: importlib.metadata.version(name) for name in ('jax', 'jaxlib', 'numpy', 'scipy', 'ml_dtypes', 'opt_einsum')}
    for fixture in contract['fixtures']:
        path = root / fixture['path']
        metadata = read_json(path.with_suffix('.json'))
        with np.load(path, allow_pickle=False) as payload:
            values = {k: payload[k] for k in payload.files}
        args = tuple(values[k] for k in ('sn', 'gal', 'observed', 'sigma')) + (metadata['kwargs']['minimum_overlap'],)
        expected = reference(*args)
        reuse = arithmetic(np, *args)
        if not all(np.array_equal(a, b, equal_nan=True) for a, b in zip(expected, reuse)):
            raise ValueError('NumPy reuse differs from the extracted native arithmetic')
        size = contract['chunk_templates']

        def chunked_numpy():
            outputs = [arithmetic(np, args[0][:, i:i+size], *args[1:])
                       for i in range(0, args[0].shape[1], size)]
            return tuple(np.concatenate([o[i] for o in outputs], axis=1) for i in range(6))

        if not all(np.array_equal(a, b, equal_nan=True) for a, b in zip(expected, chunked_numpy())):
            raise ValueError('chunked NumPy reuse differs from native arithmetic')
        for dtype in (np.float64, np.float32):
            started = time.perf_counter()
            sn, gal, observed, sigma = [np.asarray(a, dtype=dtype) for a in args[:4]]
            size = contract['chunk_templates']
            n = sn.shape[1]
            padded = np.pad(sn, ((0, 0), (0, (-n) % size), (0, 0)), constant_values=np.nan)
            common = tuple(jax.device_put(a) for a in (gal, observed, sigma, np.asarray(args[4], dtype=dtype)))
            chunks = [jax.device_put(padded[:, i:i+size]) for i in range(0, padded.shape[1], size)]
            jax.block_until_ready((common, chunks))
            transfer_seconds = time.perf_counter()-started
            signature = (np.dtype(dtype).name, tuple(chunks[0].shape), tuple(gal.shape), tuple(observed.shape))
            new_shape = signature not in compiled_shapes
            started = time.perf_counter()
            jax.block_until_ready(kernel(chunks[0], *common))
            first_call_seconds = time.perf_counter()-started
            compiled_shapes.add(signature)

            def evaluate():
                outputs = [jax.block_until_ready(kernel(chunk, *common)) for chunk in chunks]
                return tuple(np.concatenate([np.asarray(o[i]) for o in outputs], axis=1)[:, :n] for i in range(6))

            trial = evaluate()
            assessment = compare(expected, trial)
            functions = {'native': lambda: reference(*args),
                         'reuse': lambda: arithmetic(np, *args),
                         'chunked_reuse': chunked_numpy, 'jax': evaluate}
            for function in functions.values():
                function()  # excluded warm-up for every implementation
            pairs = []
            for i in range(contract['repetitions']):
                names = list(functions) if i % 2 == 0 else list(reversed(functions))
                pair = {}
                for name in names:
                    wall, cpu = time.perf_counter(), time.process_time()
                    functions[name]()
                    pair[name] = {'wall': time.perf_counter()-wall, 'cpu': time.process_time()-cpu}
                pairs.append(pair)
            timings = [pair['jax'] for pair in pairs]
            ratio = sum(t['cpu'] for t in timings) / sum(t['wall'] for t in timings)
            row = {**fixture, 'dtype': np.dtype(dtype).name, 'assessment': assessment,
                   'input_transfer_seconds': transfer_seconds, 'first_shape_call_seconds': first_call_seconds,
                   'new_compilation_shape': new_shape,
                   'paired_timings': pairs, 'jax_warm_seconds': timings,
                   'median_numpy_reuse_seconds': statistics.median(p['reuse']['wall'] for p in pairs),
                   'median_numpy_seconds': statistics.median(p['native']['wall'] for p in pairs),
                   'median_jax_seconds': statistics.median(t['wall'] for t in timings),
                   'paired_cpu_speed_ratio': statistics.median(p['native']['cpu']/p['jax']['cpu'] for p in pairs),
                   'paired_reuse_cpu_speed_ratio': statistics.median(p['reuse']['cpu']/p['jax']['cpu'] for p in pairs),
                   'paired_chunked_reuse_cpu_speed_ratio': statistics.median(p['chunked_reuse']['cpu']/p['jax']['cpu'] for p in pairs),
                   'observed_cpu_to_wall': ratio}
            row['warm_speed_ratio'] = row['median_numpy_seconds'] / row['median_jax_seconds']
            rows.append(row)
            result = {'versions': versions, 'devices': [str(d) for d in jax.devices()], 'rows': rows,
                      'edge_checks': edge_checks,
                      'complete': len(rows) == 2*len(contract['fixtures']),
                      'all_float64_accepted': all(r['assessment']['accepted'] for r in rows if r['dtype'] == 'float64'),
                      'all_edge_cases_accepted': all(e['accepted'] for e in edge_checks.values())}
            result['numerical_acceptance'] = (result['complete'] and result['all_float64_accepted']
                                               and result['all_edge_cases_accepted'])
            write_json(root / 'progress.json', result)
            print(f"{fixture['object_id']} {fixture['kind']} z={fixture['z']} {row['dtype']}: "
                  f"accepted={assessment['accepted']}; warm {row['warm_speed_ratio']:.2f}x; CPU/wall {ratio:.2f}", flush=True)
            if ratio > 1.5:
                write_json(root / 'resource_stop.json', result)
                raise RuntimeError('JAX exceeded single-core resource budget; reduce chunks in a new trial')
    write_json(root / 'results.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--fixed', type=Path, required=True)
    prep.add_argument('--free', type=Path)
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--chunk-templates', type=int, default=8, choices=(1, 4, 8, 16, 32))
    execute = sub.add_parser('run')
    execute.add_argument('root', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.fixed.resolve(), args.free.resolve() if args.free else None, args.output.resolve(), args.chunk_templates)
    else:
        run(args.root.resolve())
