"""Bounded reproduction of JAX overlap and degenerate-mixture differences."""
import argparse
from pathlib import Path
import shutil

# Set resource and precision controls before importing JAX.
import benchmark_jax
import jax
import numpy as np
from jax_ngsf_kernel import compare, edge_fixtures, make_jax_kernel, native_reference
from spectypus.io import file_hash, read_json, write_json


def run(fixture_root, output):
    output.mkdir(parents=True, exist_ok=False)
    for name in ('diagnose_jax.py', 'benchmark_jax.py', 'jax_ngsf_kernel.py'):
        shutil.copy2(Path(__file__).with_name(name), output / name)
    source = fixture_root / 'native_source.py'
    reference = native_reference(source.read_text())
    np.seterr(all='ignore')
    cases = edge_fixtures()
    path = fixture_root / 'inputs/fixture_00.npz'
    with np.load(path, allow_pickle=False) as payload:
        args = [payload[k] for k in ('sn', 'gal', 'observed', 'sigma')]
    overlap = read_json(path.with_suffix('.json'))['kwargs']['minimum_overlap']
    expected = reference(*args, overlap)
    boundary = expected[2] / args[2].size == overlap
    columns = np.flatnonzero(boundary.any(axis=0))
    if not len(columns):
        raise ValueError('fixture has no overlap-boundary case')
    # One actual SN template against the eleven hosts; no full-template JAX work.
    column = int(columns[0])
    cases['real_overlap_boundary'] = (args[0][:, column:column+1], *args[1:], overlap)
    results = {}
    for dynamic in (False, True):
        kernel = make_jax_kernel(dynamic_overlap_divisor=dynamic)
        results[str(dynamic)] = {}
        for name, values in cases.items():
            expected = reference(*values)
            actual = jax.block_until_ready(kernel(*values))
            results[str(dynamic)][name] = compare(expected, actual)
    write_json(output / 'results.json', {
        'scope': f'{len(cases)-1} tiny synthetic cases plus one real template against eleven hosts',
        'source_sha256': file_hash(source), 'fixture_sha256': file_hash(path),
        'boundary_combinations': int(boundary.sum()), 'selected_template': column,
        'dynamic_overlap_divisor': results,
        'code_sha256': {p.name: file_hash(p) for p in output.glob('*.py')}})
    for dynamic, values in results.items():
        print('dynamic divisor:', dynamic)
        for name, value in values.items():
            print(name, value['accepted'],
                  [key for key, field in value['fields'].items()
                   if not (field['nonfinite_equal'] and field['within_tolerance'])])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture_root', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run(args.fixture_root.resolve(), args.output.resolve())
