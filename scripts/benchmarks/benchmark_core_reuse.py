"""Run five additional fixed-z fits for stage 3 against verified stage-0 evidence."""
import argparse
from pathlib import Path
import os
import shutil

from benchmark_ngsf import prepare, check_files
from spectypus.adapters import engines
from spectypus.io import digest, file_hash, read_json, write_json
from spectypus.pipeline import make_plan, save_plan, execute_one, current_record, output_lock
import spectypus


def run(reference, root):
    baseline_comparison = read_json(reference / 'fixed/comparison.json')
    if not baseline_comparison['all_exact']:
        raise ValueError('reference cache comparison must pass first')
    reference_contract = read_json(reference / 'contract.json')
    check_files(reference, reference_contract)
    if not root.exists():
        prepare(Path(reference_contract['parent_campaign']), root)
        contract = read_json(root / 'contract.json')
        contract.update(stages=['core_reuse'], allowed_modes=['fixed'], maximum_attempts_per_mode=5,
                        reference_root=str(reference), reference_comparison_sha256=file_hash(reference / 'fixed/comparison.json'),
                        scope='five fixed-z NGSF fits; stage 2 caches plus reuse of five native reductions and the residual array')
        write_json(root / 'contract.json', contract)
    contract = read_json(root / 'contract.json')
    check_files(root, contract)
    if (contract['reference_root'] != str(reference)
            or contract['reference_comparison_sha256'] != file_hash(reference / 'fixed/comparison.json')):
        raise ValueError('reference changed')
    if contract['sources'] != [{**s, 'copied_path': str(root / 'inputs' / Path(s['copied_path']).name)}
                               for s in reference_contract['sources']]:
        raise ValueError('different five-spectrum selection')
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        os.nice(15 - os.getpriority(os.PRIO_PROCESS, 0))
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHONPATH'] = str(Path(spectypus.__file__).resolve().parent.parent)
    cfg = read_json(root / 'config.json')
    cfg['redshift_mode'] = 'fixed'
    output = root / 'fixed/core_reuse'
    launcher = root / 'experiment/ngsf_cache_trial.py'
    original_builder = engines.build_command
    with output_lock(root / 'fixed'):
        plan = make_plan(root / 'spectra.csv', cfg)
        plan.pop('plan_id')
        plan['experiment'] = {'stage': 3, 'contract_sha256': file_hash(root / 'contract.json'),
                              'launcher_sha256': file_hash(launcher),
                              'transform_sha256': file_hash(root / 'experiment/ngsf_core_reuse.py')}
        if len(plan['runs']) != 5 or any(r['blocked_reason'] for r in plan['runs']):
            raise ValueError('expected five eligible runs')
        for item in plan['runs']:
            item['native_execution_id'] = item['execution_id']
            item['execution_id'] = digest({'native': item['execution_id'], 'experiment': plan['experiment']})
        plan['plan_id'] = digest(plan)
        if (output / 'plan.json').exists() and read_json(output / 'plan.json') != plan:
            raise ValueError('experiment plan changed')
        save_plan(plan, output)
        baseline_plan = read_json(reference / 'fixed/native/plan.json')
        baseline_runs = {r['spectrum_id']: r for r in baseline_plan['runs']}
        comparison_path = root / 'fixed/comparison.json'
        if comparison_path.exists() and read_json(comparison_path).get('complete'):
            if not read_json(comparison_path)['all_exact']:
                raise ValueError('preserve failed comparison; prepare a new benchmark')
            if any(current_record(output, item) is None for item in plan['runs']):
                raise ValueError('completed evidence failed verification')
            print('Verified completed attempts; original comparison retained.', flush=True)
            return
        rows, checks = [], []

        def build(item, config, directory):
            command, cwd, result = original_builder(item, config, directory)
            return [command[0], str(launcher), '--stage', '3', *command[2:]], cwd, result

        engines.build_command = build
        try:
            for i, item in enumerate(plan['runs'], 1):
                check_files(root, contract)
                if shutil.disk_usage(root).free < 8 * 1024**3:
                    raise RuntimeError('less than 8 GiB raw free')
                if sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) > 512 * 1024**2:
                    raise RuntimeError('experiment exceeded 512 MiB output budget')
                baseline = current_record(reference / 'fixed/native', baseline_runs[item['spectrum_id']])
                if baseline is None:
                    raise ValueError('baseline evidence failed verification')
                record = current_record(output, item)
                if record is None:
                    if (output / 'attempts' / item['execution_id']).exists():
                        raise ValueError('preserve incomplete attempt; use a new benchmark directory')
                    print(f"START core reuse {i}/5 {item['spectrum_id']}", flush=True)
                    record = execute_one(item, plan, output)
                if record['status'] not in {'completed', 'no_good_match'}:
                    raise RuntimeError(f"fit failed: {record['reason']} ({record['attempt_path']})")
                if record['provenance'] != baseline['provenance']:
                    raise ValueError('external engine, bank, environment or parameters changed from baseline')
                artifacts = ['spectrum.txt', 'native/spectrum.csv', 'mask_applied.json', 'fit_curves.json']
                exact = {name: record['artifacts'][name] == baseline['artifacts'][name] for name in artifacts}
                check = {'spectrum_id': item['spectrum_id'], 'candidates_exact': record['candidates'] == baseline['candidates'],
                         'status_exact': record['status'] == baseline['status'], 'artifacts_exact': exact}
                checks.append(check)
                metrics = read_json(Path(record['attempt_path']) / 'benchmark_metrics.json')
                rows.append({'stage': 3, 'spectrum_id': item['spectrum_id'], 'object_id': item['object_id'],
                             'status': record['status'], 'attempt_seconds': record['elapsed_seconds'],
                             'attempt_path': record['attempt_path'], 'metrics': metrics})
                write_json(root / 'fixed/progress.json', rows)
                passed = all(c['candidates_exact'] and c['status_exact'] and all(c['artifacts_exact'].values()) for c in checks)
                write_json(root / 'fixed/comparison.json', {'all_exact': passed, 'checks': checks, 'rows': rows,
                           'complete': len(rows) == 5,
                           'campaign_status_after': read_json(Path(contract['parent_campaign']) / 'campaign_status.json')})
                if not passed:
                    raise ValueError('core reuse changed scientific evidence')
                print(f"DONE core reuse {i}/5: exact; attempt {record['elapsed_seconds']:.2f}s; "
                      f"core {metrics['inclusive_seconds']['core']:.2f}s", flush=True)
        finally:
            engines.build_command = original_builder


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.reference.resolve(), args.output.resolve())
