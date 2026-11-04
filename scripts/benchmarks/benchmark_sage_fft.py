"""Bounded, experimental SNID-SAGE FFT comparison; never a production backend.

Five copied spectra, native and complex128 JAX FFT, fixed redshift only. Run
from a frozen runtime with one nice-15 worker. External sources remain read-only.
"""
import argparse
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import sys
import textwrap
import time


def bridge():
    from spectypus.adapters.ngsf_backend import configure_cpu
    configure_cpu()
    import numpy as np
    from snid_sage.snid.core import integration
    from spectypus.adapters import sage_bridge
    from spectypus.io import write_json
    backend = os.environ['SPECTYPUS_SAGE_FFT_PROBE']
    report = {'experimental_backend': backend, 'calls': [], 'precision': 'complex128',
              'source_sha256': hashlib.sha256(Path(integration.__file__).read_bytes()).hexdigest()}
    if report['source_sha256'] != os.environ['SPECTYPUS_SAGE_FFT_SOURCE']:
        raise ValueError('SNID-SAGE source changed')
    start = time.perf_counter()
    if backend == 'jax':
        import jax
        import jaxlib
        import jax.numpy as jnp
        assert jax.__version__ == jaxlib.__version__ == '0.6.2'
        jax.config.update('jax_enable_x64', True)
        assert jax.default_backend() == 'cpu'
        kernel = jax.jit(lambda spectrum, templates, mask:
            jnp.real(jnp.fft.ifft(spectrum[None, :]*jnp.conj(templates)*mask[None, :], axis=1)))
    else:
        def kernel(spectrum, templates, mask):
            cross = spectrum[None, :]*np.conj(templates)
            filtered = cross*mask[None, :]
            return np.real(np.fft.ifft(filtered, axis=1))
    report['backend_import_seconds'] = time.perf_counter()-start

    def measured(spectrum, templates, mask):
        start = time.perf_counter()
        result = np.asarray(kernel(spectrum, templates, mask))
        report['calls'].append({'shape': list(templates.shape),
                                'seconds': time.perf_counter()-start})
        return result

    # Preserve template selection, result construction and downstream native
    # peak/threshold logic. Only the three arithmetic assignments are replaced.
    original = integration.SimpleFFTCorrelator._correlate_vectorized
    tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
    body = tree.body[0].body
    def name(node):
        return node.targets[0].id if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) else None
    first = next(i for i, node in enumerate(body) if name(node) == 'cross_power_matrix')
    last = next(i for i, node in enumerate(body) if name(node) == 'correlation_matrix')
    assert last-first == 2
    tree.body[0].body = body[:first] + ast.parse(
        'correlation_matrix = _spectypus_fft(spectrum_fft, relevant_template_ffts, self.filter_mask)').body + body[last+1:]
    namespace = dict(integration.__dict__, _spectypus_fft=measured)
    exec(compile(ast.fix_missing_locations(tree), '<sage-fft-probe>', 'exec'), namespace)
    integration.SimpleFFTCorrelator._correlate_vectorized = namespace['_correlate_vectorized']
    try:
        return sage_bridge.main(sys.argv[2:])
    finally:
        path = Path(sys.argv[sys.argv.index('--candidate-json')+1]).with_name('fft_probe.json')
        write_json(path, report)


def prepare(reference, root, python, templates):
    import spectypus
    from spectypus.io import read_json, write_json, read_csv, write_csv, file_hash
    import snid_sage.snid.core.integration as integration
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
    config['engines'] = {'snid_sage': {'python': str(python.absolute()),
        'templates': str(templates.resolve()), 'threshold': 1.5, 'backend': 'native'}}
    config.update(redshift_mode='fixed', timeout_seconds=600)
    write_json(root/'config.json', config)
    write_json(root/'contract.json', {'maximum_new_fits': 10, 'workers': 1,
        'nice': 15, 'timeout_seconds': 600,
        'scope': 'Experimental FFT substitution only; fixed redshift; five copied spectra',
        'source_sha256': file_hash(Path(integration.__file__)),
        'limitations': 'one alternating observation per spectrum/backend under concurrent load; no production authorization from this test alone',
        'files': {str(p.relative_to(root)):file_hash(p) for p in root.rglob('*') if p.is_file()}})


def run(root):
    import spectypus
    from spectypus.io import read_json, write_json, file_hash
    from spectypus.pipeline import make_plan, save_plan, execute_one, current_record, output_lock
    from spectypus.adapters import engines
    from spectypus.adapters.ngsf_backend import configure_cpu
    assert Path(spectypus.__file__).resolve().parent == root/'runtime/spectypus'
    contract = read_json(root/'contract.json')
    for name, expected in contract['files'].items():
        if file_hash(root/name) != expected:
            raise ValueError(f'frozen file changed: {name}')
    if (root/'complete.json').exists():
        raise ValueError('preserve completed experiment')
    configure_cpu()
    os.environ['PYTHONPATH'] = str(root/'runtime')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['SPECTYPUS_SAGE_FFT_SOURCE'] = contract['source_sha256']
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        os.nice(15-os.getpriority(os.PRIO_PROCESS, 0))
    original = engines.build_command
    def command(*args):
        cmd, cwd, result = original(*args)
        cmd[1:2] = [str(root/'run_experiment.py'), 'bridge']
        return cmd, cwd, result
    engines.build_command = command
    rows, records = [], {}
    with output_lock(root):
        plan = make_plan(root/'spectra.csv', read_json(root/'config.json'))
        assert len(plan['runs']) == 5 and not any(r['blocked_reason'] for r in plan['runs'])
        for backend in ('native','jax'):
            save_plan(plan, root/backend)
        for i, item in enumerate(plan['runs']):
            for backend in (('native','jax') if i%2 == 0 else ('jax','native')):
                output = root/backend
                os.environ['SPECTYPUS_SAGE_FFT_PROBE'] = backend
                record = current_record(output, item)
                if record is None:
                    if (output/'attempts'/item['execution_id']).exists():
                        raise ValueError('preserve incomplete attempt; use a new experiment')
                    if shutil.disk_usage(root).free < 8*1024**3:
                        raise ValueError('8 GiB disk reserve reached')
                    print(f'START {backend} {item["object_id"]}', flush=True)
                    record = execute_one(item, plan, output)
                if record['status'] not in {'completed','no_good_match'}:
                    raise ValueError(f'attempt failed: {record["reason"]} {record["attempt_path"]}')
                info = read_json(Path(record['attempt_path'])/'fft_probe.json')
                assert info['calls'] and info['experimental_backend'] == backend
                records[backend,i] = record
                rows.append({'backend':backend, 'object_id':item['object_id'],
                    'seconds':record['elapsed_seconds'], 'fft':info,
                    'attempt_path':record['attempt_path']})
                write_json(root/'progress.json', {'rows':rows})
                print(f'DONE {backend} {item["object_id"]} {record["elapsed_seconds"]:.2f}s', flush=True)
        checks = []
        for i in range(5):
            a,b = records['native',i], records['jax',i]
            names = ['sage_candidates.json','fit_curves.json','mask_applied.json','spectrum.txt']
            checks.append({'object_id':a['run']['object_id'],
                'candidates_exact':a['candidates']==b['candidates'],
                'status_exact':a['status']==b['status'],
                'artifacts_exact':{n:a['artifacts'][n]==b['artifacts'][n] for n in names}})
        write_json(root/'complete.json', {'rows':rows, 'checks':checks})


def report(root, output):
    data = json.loads((root/'complete.json').read_text())
    if len(data['rows']) != 10 or not all(c['candidates_exact'] and c['status_exact']
            and all(c['artifacts_exact'].values()) for c in data['checks']):
        raise ValueError('requires ten completed fits and exact scientific comparisons')
    totals = {}
    for backend in ('native', 'jax'):
        rows = [r for r in data['rows'] if r['backend']==backend]
        totals[backend] = {'attempt':sum(r['seconds'] for r in rows),
            'fft':sum(c['seconds'] for r in rows for c in r['fft']['calls']),
            'initialization':sum(r['fft']['backend_import_seconds'] for r in rows)}
    summary = {'totals':totals,'all_five_comparisons_exact':True,
        'extra_jax_seconds':totals['jax']['attempt']-totals['native']['attempt'],
        'percent_extra_time':100*(totals['jax']['attempt']/totals['native']['attempt']-1),
        'native_fft_percent':100*totals['native']['fft']/totals['native']['attempt'],
        'scope':'Fixed redshift only, one alternating observation per backend/spectrum under shared load; experimental FFT substitution, not a production backend.'}
    output.mkdir(parents=True,exist_ok=False)
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    html = '''<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;color:var(--foreground);font:14px var(--font-sans,system-ui)}p{line-height:1.5}.muted{color:var(--muted-foreground);font-size:12px}
    select{padding:6px;background:var(--card);color:var(--foreground);border:1px solid var(--border);border-radius:var(--radius)}
    .chart{height:100px;margin:12px 0}.row{display:grid;grid-template-columns:140px 1fr 70px;gap:8px;align-items:center;height:45px}.track{background:var(--secondary);height:20px}.bar{background:var(--chart-1);height:20px}#jax{background:var(--chart-3)}.value{text-align:right;font:12px var(--font-mono,monospace)}
    @media(max-width:450px){.row{grid-template-columns:105px 1fr 65px;font-size:12px;gap:5px}}
    </style></head><body><p><strong>SNID-SAGE: keep native FFTs</strong><br><span class="muted">Same five spectra · all candidate and saved-fit comparisons exact</span></p>
    <select id="stage"><option value="attempt">Complete fitting attempts</option><option value="fft">FFT stage, including first-shape compilation</option><option value="initialization">Backend initialization</option></select>
    <div class="chart"><div class="row"><span>Native FFT</span><div class="track"><div class="bar" id="native"></div></div><span class="value" id="nativevalue"></span></div><div class="row"><span>JAX FFT trial</span><div class="track"><div class="bar" id="jax"></div></div><span class="value" id="jaxvalue"></span></div></div>
    <p id="summary"></p><p class="muted">Native FFT arithmetic uses only about 0.20% of complete attempt time. This trial does not support a JAX default for SAGE. One alternating observation per spectrum/backend under shared load; fixed redshift only.</p>
    <script>const d=__DATA__,el=id=>document.getElementById(id);function draw(){const k=el('stage').value,max=Math.max(d.totals.native[k],d.totals.jax[k]);for(const b of ['native','jax']){el(b).style.width=100*d.totals[b][k]/max+'%';el(b+'value').textContent=d.totals[b][k].toFixed(k==='attempt'?1:3)+' s'}}el('stage').addEventListener('change',draw);draw();el('summary').textContent=`JAX took ${d.extra_jax_seconds.toFixed(2)} s longer overall (${d.percent_extra_time.toFixed(1)}% more time) in this trial.`;</script></body></html>'''
    (output/'comparison.html').write_text(html.replace('__DATA__',json.dumps(summary).replace('</','<\\/')))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='bridge':
        raise SystemExit(bridge())
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p=sub.add_parser('prepare')
    for name in ('reference','output','python','templates'):
        p.add_argument('--'+name, required=True, type=Path)
    p=sub.add_parser('run')
    p.add_argument('root',type=Path)
    p=sub.add_parser('report')
    p.add_argument('root',type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.action=='prepare':
        prepare(args.reference.resolve(),args.output.resolve(),args.python,args.templates)
    elif args.action=='run':
        run(args.root.resolve())
    else:
        report(args.root.resolve(),args.output.resolve())
