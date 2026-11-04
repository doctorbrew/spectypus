"""Bounded integration check for installed backend choices on five copied spectra.

Run from a frozen experiment/runtime. Fifteen fixed fits rotate native/NumPy/JAX
order; five JAX free fits compare to the earlier verified native references.
The source campaign and external engine assets are read-only.
"""
import argparse
import os
from pathlib import Path
import shutil
import statistics
import sys
import time

from spectypus.io import read_json, write_json, file_hash, write_csv, read_csv
from spectypus.pipeline import make_plan, save_plan, execute_one, current_record, verify_attempt, output_lock


def prepare(reference, root, python):
    import spectypus
    if Path(spectypus.__file__).resolve().parent != Path(__file__).resolve().parents[2]/'src/spectypus':
        raise ValueError('prepare requires PYTHONPATH pointing at this checkout/src')
    root.mkdir(parents=True, exist_ok=False)
    (root/'inputs').mkdir()
    shutil.copytree(Path(spectypus.__file__).parent, root/'runtime/spectypus',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(__file__, root/'run_experiment.py')
    rows = read_csv(reference/'spectra.csv')
    for row in rows:
        source = Path(row['path'])
        shutil.copy2(source, root/'inputs'/source.name)
        row['path'] = str(root/'inputs'/source.name)
    write_csv(root/'spectra.csv', rows, list(rows[0]))
    config = read_json(reference/'config.json')
    config['engines']['ngsf']['python'] = str(python.absolute())
    config['timeout_seconds'] = 1800
    shutil.copy2(reference/'native_parameters.json', root/'native_parameters.json')
    config['engines']['ngsf']['parameters'] = str(root/'native_parameters.json')
    write_json(root/'config.json', config)
    files = {str(p.relative_to(root)):file_hash(p) for p in root.rglob('*') if p.is_file()}
    write_json(root/'contract.json', {
        'reference':str(reference), 'files':files, 'maximum_new_fits':20,
        'scope':'five spectra; three fixed-z backends; five full free-z JAX fits',
        'workers':1, 'nice':15, 'timeout_seconds':1800,
        'limitations':'one timing pair per fixed-z spectrum under concurrent load; no paired free-z speed claim'})


def run(root):
    import spectypus
    if Path(spectypus.__file__).resolve().parent != root/'runtime/spectypus':
        raise ValueError('use frozen runtime PYTHONPATH')
    contract = read_json(root/'contract.json')
    for name, expected in contract['files'].items():
        if file_hash(root/name) != expected:
            raise ValueError(f'frozen file changed: {name}')
    if (root/'complete.json').exists():
        raise ValueError('preserve completed experiment')
    os.environ['PYTHONPATH'] = str(root/'runtime')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    from spectypus.adapters.ngsf_backend import configure_cpu
    configure_cpu()
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        os.nice(15-os.getpriority(os.PRIO_PROCESS, 0))
    config = read_json(root/'config.json')
    rows, plans, outputs = [], {}, {}
    with output_lock(root):
        for mode, backends in [('fixed',('native','numpy','jax')), ('free',('jax',))]:
            for backend in backends:
                config['redshift_mode'] = mode
                config['engines']['ngsf']['backend'] = backend
                plan = make_plan(root/'spectra.csv', config)
                assert len(plan['runs']) == 5 and not any(r['blocked_reason'] for r in plan['runs'])
                output = root/mode/backend
                if (output/'plan.json').exists() and read_json(output/'plan.json') != plan:
                    raise ValueError('plan changed')
                save_plan(plan, output)
                plans[mode, backend], outputs[mode, backend] = plan, output
        tasks = []
        for i in range(5):
            backends = ['native','numpy','jax']
            for backend in backends[i%3:]+backends[:i%3]:
                tasks.append(('fixed',backend,i))
        tasks += [('free','jax',i) for i in range(5)]
        for mode, backend, index in tasks:
            plan, output = plans[mode,backend], outputs[mode,backend]
            item = plan['runs'][index]
            record = current_record(output, item)
            if record is None:
                if (output/'attempts'/item['execution_id']).exists():
                    raise ValueError('preserve incomplete attempt; prepare new experiment')
                if shutil.disk_usage(root).free < 8*1024**3:
                    raise ValueError('8 GiB disk reserve reached')
                print(f"START {mode} {backend} {item['object_id']}", flush=True)
                record = execute_one(item, plan, output)
            if record['status'] not in {'completed','no_good_match'}:
                raise ValueError(f"attempt failed: {record['reason']} {record['attempt_path']}")
            directory = Path(record['attempt_path'])
            info = read_json(directory/'backend.json')
            if info['effective'] != backend:
                raise ValueError(f'requested backend not exercised: {info}')
            rows.append({'mode':mode, 'backend':backend, 'spectrum_id':item['spectrum_id'],
                'object_id':item['object_id'], 'seconds':record['elapsed_seconds'],
                'attempt_path':str(directory), 'backend_report':info})
            write_json(root/'progress.json', {'rows':rows})
            print(f"DONE {mode} {backend} {item['object_id']} {record['elapsed_seconds']:.2f}s", flush=True)
        checks = []
        reference_contract = read_json(Path(contract['reference'])/'contract.json')
        for mode, backend, index in tasks:
            if backend == 'native':
                continue
            record = current_record(outputs[mode,backend],plans[mode,backend]['runs'][index])
            if mode == 'fixed':
                baseline = current_record(outputs[mode,'native'], plans[mode,'native']['runs'][index])
            else:
                ref = reference_contract['baselines'][record['run']['spectrum_id']]
                baseline = verify_attempt(Path(ref['directory']),ref['execution_id'])
            if baseline is None:
                raise ValueError('reference no longer verifies')
            names = ['native/spectrum.csv','fit_curves.json','mask_applied.json','spectrum.txt']
            if mode == 'free':
                names.append('redshift_grid.json')
            checks.append({'mode':mode,'backend':backend,'spectrum_id':record['run']['spectrum_id'],
                'candidates_exact':record['candidates']==baseline['candidates'],
                'status_exact':record['status']==baseline['status'],
                'artifacts_exact':{n:record['artifacts'][n]==baseline['artifacts'][n] for n in names}})
        exact = all(c['candidates_exact'] and c['status_exact'] and all(c['artifacts_exact'].values()) for c in checks)
        ratios = []
        for sid in {r['spectrum_id'] for r in rows}:
            pair = {r['backend']:r['seconds'] for r in rows if r['mode']=='fixed' and r['spectrum_id']==sid}
            ratios.append({'spectrum_id':sid,**pair,'native_to_jax':pair['native']/pair['jax']})
        write_json(root/'complete.json', {'all_exact':exact,'checks':checks,'rows':rows,'fixed_timings':ratios,
            'median_fixed_native_to_jax':statistics.median(r['native_to_jax'] for r in ratios)})
        if not exact:
            raise ValueError('scientific output comparison failed; inspect complete.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--python', required=True, type=Path)
    p = sub.add_parser('run')
    p.add_argument('root', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.reference.resolve(),args.output.resolve(),args.python)
    else:
        run(args.root.resolve())
