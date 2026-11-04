"""Five full free-z trials against copied, hash-verified historical native fits.

Prepare once; execute from the frozen runtime/experiment directories. One
low-priority worker, at most five fresh attempts, 2400 s per fit. No writes to
the source campaign, engines or banks. Historical timings are not paired.
"""
import argparse
import copy
import os
from pathlib import Path
import shutil

import spectypus
from benchmark_ngsf import prepare as prepare_inputs, check_files
from spectypus.adapters import engines
from spectypus.io import digest, file_hash, read_json, write_json
from spectypus.pipeline import (make_plan, save_plan, execute_one, current_record,
                                verify_attempt, output_lock)


def prepare(campaign, root):
    prepare_inputs(campaign, root)
    contract = read_json(root / 'contract.json')
    config = read_json(root / 'config.json')
    config.update(redshift_mode='free', timeout_seconds=2400)
    write_json(root / 'config.json', config)
    contract['frozen_files']['config.json'] = file_hash(root / 'config.json')
    shutil.copytree(Path(spectypus.__file__).parent, root / 'runtime/spectypus',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for path in (root / 'runtime').rglob('*'):
        if path.is_file():
            contract['frozen_files'][str(path.relative_to(root))] = file_hash(path)
    native_plan = read_json(campaign / 'run/plan.json')
    selected = {s['spectrum_id'] for s in contract['sources']}
    baselines = {}
    for item in native_plan['runs']:
        if item['spectrum_id'] not in selected or item['engine'] != 'ngsf' or item['mode'] != 'free':
            continue
        record = current_record(campaign / 'run', item)
        if record is None or record['status'] not in {'completed', 'no_good_match'}:
            raise ValueError(f"missing verified native reference: {item['spectrum_id']}")
        directory = Path(record['attempt_path'])
        destination = root / 'baselines' / item['execution_id']
        for name in [*record['artifacts'], 'record.json', 'record.sha256']:
            dest = destination / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(directory / name, dest)
            contract['frozen_files'][str(dest.relative_to(root))] = file_hash(dest)
        if verify_attempt(destination, item['execution_id']) is None:
            raise ValueError('copied baseline failed verification')
        baselines[item['spectrum_id']] = {'execution_id': item['execution_id'],
            'directory': str(destination), 'source_directory': str(directory)}
    if len(baselines) != 5:
        raise ValueError('require five verified free-z baselines')
    contract.update(stages=['intermediate_reuse'], allowed_modes=['free'], maximum_attempts_per_mode=5,
        timeout_seconds_per_attempt=2400, baselines=baselines, capture_redshifts=[0., .5, 1.],
        expected_core_calls=4141, expected_error_computations=1, expected_galaxy_computations=101,
        scope='NGSF intermediate reuse; unchanged 101 redshifts x 41 extinction values and full native template selection',
        scheduling='nice 15, one numerical thread; OS schedules the worker below normal-priority campaign jobs',
        limitations='native reference results are historical, so timings are unpaired; no accuracy claim')
    write_json(root / 'contract.json', contract)


def run(root, max_new_runs):
    contract = read_json(root / 'contract.json')
    check_files(root, contract)
    if Path(spectypus.__file__).resolve().parent != root / 'runtime/spectypus':
        raise ValueError('launch with PYTHONPATH pointing at this experiment/runtime')
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        os.nice(15 - os.getpriority(os.PRIO_PROCESS, 0))
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHONPATH'] = str(root / 'runtime')
    launcher = root / 'experiment/ngsf_cache_trial.py'
    output = root / 'run'
    original_builder = engines.build_command
    with output_lock(output):
        plan = make_plan(root / 'spectra.csv', root / 'config.json')
        plan.pop('plan_id')
        plan['experiment'] = {'name': 'free-z intermediate reuse',
                              'contract_sha256': file_hash(root / 'contract.json')}
        if len(plan['runs']) != 5 or any(r['blocked_reason'] for r in plan['runs']):
            raise ValueError('expected exactly five eligible runs')
        for item in plan['runs']:
            item['native_execution_id'] = item['execution_id']
            item['execution_id'] = digest({'native': item['execution_id'], 'experiment': plan['experiment']})
        plan['plan_id'] = digest(plan)
        if (output / 'plan.json').exists() and read_json(output / 'plan.json') != plan:
            raise ValueError('frozen plan changed')
        save_plan(plan, output)
        if (root / 'comparison.json').exists():
            if not read_json(root / 'comparison.json')['all_exact']:
                raise ValueError('preserve failed evidence; use a new experiment')
            if any(current_record(output, item) is None for item in plan['runs']):
                raise ValueError('completed evidence corrupted')
            print('Verified existing completed experiment; no writes to comparisons.', flush=True)
            return
        rows, checks, launched = [], [], 0

        def build(item, config, directory):
            command, cwd, result = original_builder(item, config, directory)
            return [command[0], str(launcher), '--stage', '3', '--capture-redshifts',
                    '0', '.5', '1', '--', *command[2:]], cwd, result

        engines.build_command = build
        try:
            for index, item in enumerate(plan['runs'], 1):
                check_files(root, contract)
                ref = contract['baselines'][item['spectrum_id']]
                baseline = verify_attempt(Path(ref['directory']), ref['execution_id'])
                if baseline is None:
                    raise ValueError('reference evidence corrupted')
                record = current_record(output, item)
                if record is None:
                    if launched >= max_new_runs:
                        break
                    if (output / 'attempts' / item['execution_id']).exists():
                        raise ValueError('preserve incomplete attempt; use a new experiment')
                    if shutil.disk_usage(root).free < 8 * 1024**3:
                        raise RuntimeError('below benchmark 8 GiB raw-free reserve')
                    if sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) > 512 * 1024**2:
                        raise RuntimeError('benchmark disk budget exceeded')
                    if plan['provenance']['ngsf'] != baseline['provenance']:
                        raise ValueError('external source/bank/runtime differs from historical reference')
                    print(f"START free-z {index}/5 {item['spectrum_id']}", flush=True)
                    record = execute_one(item, plan, output)
                    launched += 1
                if record['status'] not in {'completed', 'no_good_match'}:
                    raise RuntimeError(f"free-z trial failed: {record['reason']}; {record['attempt_path']}")
                directory = Path(record['attempt_path'])
                metrics = read_json(directory / 'benchmark_metrics.json')
                if metrics['counts']['core_calls'] != 4141:
                    raise ValueError('incomplete redshift/extinction grid')
                artifacts = ['spectrum.txt', 'native/spectrum.csv', 'mask_applied.json',
                             'fit_curves.json', 'redshift_grid.json']
                exact = {name: record['artifacts'][name] == baseline['artifacts'][name] for name in artifacts}
                before = read_json(Path(ref['directory']) / 'parameters.json')
                after = read_json(directory / 'parameters.json')
                for params in (before, after):
                    for name in ('object_to_fit', 'saving_results_path'):
                        params.pop(name)
                check = {'spectrum_id': item['spectrum_id'], 'status_exact': record['status'] == baseline['status'],
                         'candidates_exact': record['candidates'] == baseline['candidates'],
                         'staging_exact': record['staging'] == baseline['staging'],
                         'parameters_exact': before == after, 'artifacts_exact': exact}
                checks.append(check)
                rows.append({'spectrum_id': item['spectrum_id'], 'object_id': item['object_id'],
                             'status': record['status'], 'attempt_seconds': record['elapsed_seconds'],
                             'historical_native_seconds': baseline['elapsed_seconds'],
                             'attempt_path': str(directory), 'metrics': metrics})
                passed = all(c['status_exact'] and c['candidates_exact'] and c['staging_exact']
                             and c['parameters_exact'] and all(c['artifacts_exact'].values()) for c in checks)
                result = {'all_exact': passed, 'complete': len(rows) == 5, 'rows': rows, 'checks': checks,
                          'campaign_status': read_json(Path(contract['parent_campaign']) / 'campaign_status.json')}
                write_json(root / 'progress.json', result)
                if not passed:
                    write_json(root / 'failure_comparison.json', result)
                    raise ValueError('free-redshift scientific equivalence failed')
                print(f"DONE free-z {index}/5: exact; {record['elapsed_seconds']:.1f}s; 4141 grid points", flush=True)
            if len(rows) == 5:
                write_json(root / 'comparison.json', result)
        finally:
            engines.build_command = original_builder


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--campaign', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    execute = sub.add_parser('run')
    execute.add_argument('root', type=Path)
    execute.add_argument('--max-new-runs', type=int, default=5, choices=range(1, 6))
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.campaign.resolve(), args.output.resolve())
    else:
        run(args.root.resolve(), args.max_new_runs)
