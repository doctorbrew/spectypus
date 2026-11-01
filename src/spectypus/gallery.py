"""Serialized, content-addressed Python figure exports outside native attempts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock
import os
import subprocess
import sys
from .io import digest, file_hash, read_json, write_json
from .phases import phase_context


class Galleries:
    def __init__(self, output):
        self.root = Path(output) / 'review_figures'
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='fit-figures')
        self.jobs, self.lock = {}, RLock()

    def request(self, snapshot, execution_id):
        from .review import fit_curve
        run = next((r for r in snapshot['runs'] if r['execution_id'] == execution_id), None)
        if run is None: raise KeyError(execution_id)
        source = next(s for s in snapshot['plan']['spectra'] if s['spectrum_id'] == run['spectrum_id'])
        n = min(10, len(snapshot['records'].get(execution_id, {}).get('candidates', [])))
        curves = [fit_curve(snapshot, execution_id, i) for i in range(1, n + 1)]
        curves = [c for c in curves if c.get('available')]
        if not curves: return {'status': 'unavailable', 'reason': 'No verified saved model curves'}
        context = phase_context(source, snapshot.get('phase_references', {}).get(source['object_id'], []))
        payload = {'curves': curves, 'source': {'object_id': source['object_id'], 'spectrum_id': source['spectrum_id']},
                   'engine': run['engine'], 'mode': run['mode'], 'phase_context': context,
                   'renderer_sha256': file_hash(Path(__file__).with_name('fit_plots.py')),
                   'style_sha256': file_hash(Path(__file__).with_name('plot_style.py'))}
        key = digest(payload); folder = self.root / key
        with self.lock:
            if (folder / 'gallery.json').exists():
                return {**read_json(folder / 'gallery.json'), 'key': key}
            job = self.jobs.get(key)
            if job and job.done():
                error = job.exception()
                if error: return {'status': 'error', 'reason': str(error)}
            if not job:
                folder.mkdir(parents=True, exist_ok=True)
                write_json(folder / 'request.json', payload)
                self.jobs[key] = self.pool.submit(self.render, folder)
            return {'status': 'rendering', 'key': key}

    @staticmethod
    def render(folder):
        local = Path(__file__).resolve().parents[2] / '.venv-plots/bin/python'
        python = os.environ.get('SPECTYPUS_PLOT_PYTHON') or (str(local) if local.exists() else sys.executable)
        env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
               'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MPLBACKEND': 'Agg'}
        with (folder / 'render.log').open('w') as log:
            result = subprocess.run([python, '-m', 'spectypus.fit_plots', str(folder / 'request.json'), str(folder)],
                                    stdout=log, stderr=log, env=env, timeout=900)
        if result.returncode:
            raise RuntimeError('Python plot export failed; inspect ' + str(folder / 'render.log') +
                               '. Requires the plots extra and working LaTeX; no browser-plot fallback.')
