"""Bounded five-spectrum NGSF experiment, isolated from live campaigns.

Prepare once, then run fixed and/or free mode. Each mode allows exactly fifteen
attempts (five spectra x three stages), with native 900-second fit timeouts.
Re-invocation only verifies/reuses completed attempts; failures stop the trial.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import shutil
import sys
import time

from spectypus.adapters import engines
from spectypus.io import digest, file_hash, read_json, write_csv, write_json
from spectypus.manifest import spectrum_data
from spectypus.pipeline import make_plan, save_plan, execute_one, current_record, output_lock
import spectypus


STAGES = ('native', 'error_cache', 'error_and_galaxy_cache')


def prepare(campaign, root):
    original = read_json(campaign / 'run/plan.json')
    identity = original.pop('plan_id')
    if digest(original) != identity:
        raise ValueError('campaign plan hash mismatch')
    original['plan_id'] = identity
    pool = sorted((s for s in original['spectra'] if s['batch'] == 'chen'
                   and not s['blocked_reason'] and not s['duplicate_of'] and s['redshift'] is not None),
                  key=lambda s: (s['staging']['samples'], s['spectrum_id']))
    indices = [round((len(pool) - 1) * q / 4) for q in range(5)]
    if len(set(indices)) != 5:
        raise ValueError('need five distinct eligible spectra')
    root.mkdir(parents=True, exist_ok=False)
    (root / 'inputs').mkdir()
    (root / 'experiment').mkdir()
    rows, provenance = [], []
    for index in indices:
        source = pool[index]
        path = Path(source['path'])
        if file_hash(path) != source['staging']['source_sha256']:
            raise ValueError(f'source changed: {path}')
        destination = root / 'inputs' / path.name
        shutil.copy2(path, destination)
        # Preserve declared rest/observer frame and catalogue redshift source.
        row = {k: v for k, v in source.items() if k not in ('staging', 'blocked_reason', 'duplicate_of')}
        row['path'] = str(destination)
        _, staged = spectrum_data(row)
        if staged != source['staging']:
            raise ValueError('copied spectrum staging differs')
        rows.append(row)
        provenance.append({'original_path': str(path), 'copied_path': str(destination),
                           'spectrum_id': source['spectrum_id'], 'object_id': source['object_id'],
                           'redshift': source['redshift'], 'staging': staged})
    write_csv(root / 'spectra.csv', rows, list(rows[0]))
    config = copy.deepcopy(original['config'])
    config['engines'] = {'ngsf': config['engines']['ngsf']}
    cfg = config['engines']['ngsf']
    cfg['backend'] = 'native'  # this runner supplies its own experimental hooks
    shutil.copy2(cfg['parameters'], root / 'native_parameters.json')
    cfg['parameters'] = str(root / 'native_parameters.json')
    config['timeout_seconds'] = 900
    config['save_fit_curves'] = True
    write_json(root / 'config.json', config)
    files = {}
    for path in Path(__file__).parent.glob('*.py'):
        dest = root / 'experiment' / path.name
        shutil.copy2(path, dest)
        files[str(dest.relative_to(root))] = file_hash(dest)
    files['config.json'] = file_hash(root / 'config.json')
    files['native_parameters.json'] = file_hash(root / 'native_parameters.json')
    files['spectra.csv'] = file_hash(root / 'spectra.csv')
    for source in provenance:
        dest = Path(source['copied_path'])
        files[str(dest.relative_to(root))] = file_hash(dest)
    write_json(root / 'contract.json', {
        'schema': 'spectypus-ngsf-cache-benchmark/1', 'created_at': datetime.now(timezone.utc).isoformat(),
        'parent_campaign': str(campaign), 'parent_plan_id': identity,
        'selection': 'five input-length quantiles from eligible unique Chen spectra with known catalogue redshift',
        'sources': provenance, 'stages': STAGES, 'maximum_attempts_per_mode': 15,
        'allowed_modes': ['fixed', 'free'], 'timeout_seconds_per_attempt': 900,
        'workers': 1, 'numerical_threads': 1, 'niceness': 15,
        'scope': 'NGSF only; fixed uses catalogue z; free uses unchanged 0..1/0.01 grid; full native extinction grid and template selection',
        'comparison': 'exact candidate records and byte-identical native CSV, staged input, masks and fit curves',
        'limitations': 'five spectra, one attempt per stage/mode, concurrent campaigns and shared caches; no accuracy or controlled system-wide speed claim',
        'resource_bounds': 'one low-priority worker; stop new attempts below 8 GiB raw free; experiment maximum 512 MiB on disk',
        'platform': platform.platform(), 'python': sys.version, 'frozen_files': files,
        'campaign_status_before': read_json(campaign / 'campaign_status.json')})
    print(root, flush=True)


def check_files(root, contract):
    for relative, checksum in contract['frozen_files'].items():
        if file_hash(root / relative) != checksum:
            raise ValueError(f'benchmark input or code changed: {relative}')


def run(root, mode):
    contract = read_json(root / 'contract.json')
    check_files(root, contract)
    if mode not in contract['allowed_modes']:
        raise ValueError('undeclared mode')
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        os.nice(15 - os.getpriority(os.PRIO_PROCESS, 0))
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHONPATH'] = str(Path(spectypus.__file__).resolve().parent.parent)
    cfg = read_json(root / 'config.json')
    cfg['redshift_mode'] = mode
    launcher = root / 'experiment/ngsf_cache_trial.py'
    original_builder = engines.build_command
    plans, outputs = [], []
    started = time.monotonic()
    with output_lock(root / mode):
        native = make_plan(root / 'spectra.csv', cfg)
        if len(native['runs']) != 5 or any(r['blocked_reason'] for r in native['runs']):
            raise ValueError('benchmark requires five runnable spectra')
        for stage, name in enumerate(STAGES):
            plan = copy.deepcopy(native)
            plan.pop('plan_id')
            plan['experiment'] = {'stage': stage, 'name': name, 'launcher_sha256': file_hash(launcher),
                                  'contract_sha256': file_hash(root / 'contract.json')}
            for item in plan['runs']:
                item['native_execution_id'] = item['execution_id']
                item['execution_id'] = digest({'native': item['execution_id'], 'experiment': plan['experiment']})
            plan['plan_id'] = digest(plan)
            output = root / mode / name
            if (output / 'plan.json').exists() and read_json(output / 'plan.json') != plan:
                raise ValueError('experiment plan changed; prepare a new benchmark')
            save_plan(plan, output)
            plans.append(plan)
            outputs.append(output)
        if (root / mode / 'comparison.json').exists():
            completed = read_json(root / mode / 'comparison.json')
            if not completed['all_exact']:
                raise ValueError('preserve failed comparison; prepare a new benchmark')
            for plan, output in zip(plans, outputs):
                if any(current_record(output, item) is None for item in plan['runs']):
                    raise ValueError('completed evidence failed verification')
            print('Verified completed attempts; original comparison retained.', flush=True)
            return
        progress = []
        try:
            # Rotate ordering to avoid always giving an optimization warm caches.
            for index in range(5):
                for stage in [(index + i) % 3 for i in range(3)]:
                    check_files(root, contract)
                    if shutil.disk_usage(root).free < 8 * 1024**3:
                        raise RuntimeError('benchmark reserve: less than 8 GiB raw free')
                    if sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) > 512 * 1024**2:
                        raise RuntimeError('benchmark exceeded 512 MiB output budget')
                    plan, output = plans[stage], outputs[stage]
                    item = plan['runs'][index]

                    def build(run_item, config, directory):
                        command, cwd, result = original_builder(run_item, config, directory)
                        return [command[0], str(launcher), '--stage', str(stage), *command[2:]], cwd, result

                    engines.build_command = build
                    prior = current_record(output, item)
                    if prior is not None:
                        record = prior
                    elif (output / 'attempts' / item['execution_id']).exists():
                        raise RuntimeError('incomplete prior attempt; preserve it and prepare a new benchmark')
                    else:
                        print(f"START {mode} {index+1}/5 {STAGES[stage]} {item['spectrum_id']}", flush=True)
                        record = execute_one(item, plan, output)
                    if record['status'] not in {'completed', 'no_good_match'}:
                        raise RuntimeError(f"benchmark failure: {record['reason']} ({record['attempt_path']})")
                    metrics = read_json(Path(record['attempt_path']) / 'benchmark_metrics.json')
                    row = {'spectrum_id': item['spectrum_id'], 'object_id': item['object_id'],
                           'mode': mode, 'stage': stage, 'status': record['status'],
                           'attempt_seconds': record['elapsed_seconds'], 'metrics': metrics,
                           'attempt_path': record['attempt_path']}
                    progress.append(row)
                    write_json(root / mode / 'progress.json', progress)
                    print(f"DONE {mode} {index+1}/5 {STAGES[stage]}: {record['status']}; "
                          f"attempt {record['elapsed_seconds']:.2f}s, core {metrics['inclusive_seconds'].get('core',0):.2f}s", flush=True)
            checks = []
            for index in range(5):
                records = [current_record(outputs[s], plans[s]['runs'][index]) for s in range(3)]
                if any(r is None for r in records):
                    raise ValueError('attempt evidence failed verification')
                base = records[0]
                for stage, candidate in enumerate(records[1:], 1):
                    artifacts = ['spectrum.txt', 'native/spectrum.csv', 'mask_applied.json', 'fit_curves.json']
                    if mode == 'free':
                        artifacts.append('redshift_grid.json')
                    exact = {name: base['artifacts'][name] == candidate['artifacts'][name] for name in artifacts}
                    check = {'spectrum_id': base['run']['spectrum_id'], 'stage': stage,
                             'status_exact': base['status'] == candidate['status'],
                             'candidates_exact': base['candidates'] == candidate['candidates'],
                             'artifacts_exact': exact}
                    checks.append(check)
            passed = all(c['status_exact'] and c['candidates_exact'] and all(c['artifacts_exact'].values()) for c in checks)
            write_json(root / mode / 'comparison.json', {'all_exact': passed, 'checks': checks,
                       'elapsed_seconds': time.monotonic()-started, 'rows': progress,
                       'campaign_status_after': read_json(Path(contract['parent_campaign']) / 'campaign_status.json')})
            if not passed:
                raise ValueError('scientific equivalence check failed')
            print(f'EXACT: all 10 stage comparisons passed for {mode}', flush=True)
        finally:
            engines.build_command = original_builder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--campaign', required=True, type=Path)
    prep.add_argument('--output', required=True, type=Path)
    execute = sub.add_parser('run')
    execute.add_argument('root', type=Path)
    execute.add_argument('--mode', choices=('fixed', 'free'), required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.campaign.resolve(), args.output.resolve())
    else:
        run(args.root.resolve(), args.mode)


if __name__ == '__main__':
    main()
