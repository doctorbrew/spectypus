"""Reviewer-selected single-match JPGs from verified frozen plot requests."""
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from ..io import digest, file_hash, read_json, write_json
from ..pipeline import SCHEMA, current_record, output_lock
from .products import validate_jpg

ENGINES = {'snid_sage': 'SNID-SAGE', 'ngsf': 'NGSF'}


def export_names(records):
    """Use native object names, with stable suffixes for filesystem collisions."""
    slug = lambda value: re.sub(r'[^A-Za-z0-9_.-]+', '_', str(value)).strip('._')[:100] or 'spectrum'
    names = Counter(slug(r['source']['object_id']).casefold() for r in records)
    result = {}
    for record in records:
        key = f'c{record["campaign"]}:{record["source"]["spectrum_id"]}'
        name = slug(record['source']['object_id'])
        if names[name.casefold()] > 1:
            name += '_' + digest(key)[:10]
        result[key] = {engine:f'PLOT_Classification_{label}_{name}.jpg' for engine, label in ENGINES.items()}
    return result


def evidence(output):
    summary = read_json(output / 'summary.json')['report']
    path = output / 'classification-report-evidence.json'
    if not path.is_file() or file_hash(path) != summary.get('evidence_sha256'):
        raise ValueError('Refresh this report with spectypus summarize before exporting selections')
    data = read_json(path)
    plan = read_json(output / 'plan.json')
    identity = plan.pop('plan_id')
    if (plan.get('schema') != SCHEMA or digest(plan) != identity or data['plan_id'] != identity
            or data['report_identity'] != summary['identity']):
        raise ValueError('Report does not match the current verified plan')
    return data


def resolve_selections(output, log):
    """Validate the whole request before rendering or replacing any exports."""
    data = evidence(output)
    if not isinstance(log, dict):
        raise ValueError('Expected a reviewer JSON log')
    if log.get('schema') != 'spectypus-night-log/1' or log.get('report_identity') != data['report_identity']:
        raise ValueError('Log belongs to different spectra or fits')
    records = {f'c{r["campaign"]}:{r["source"]["spectrum_id"]}': r for r in data['records']}
    rows = log.get('rows')
    if (not isinstance(rows, list) or len(rows) != len(records) or not all(isinstance(row, dict) for row in rows) or
            {row.get('key') for row in rows} != set(records)):
        raise ValueError('Log must contain each spectrum exactly once')
    names = export_names(list(records.values()))
    selected = []
    for row in rows:
        record = records[row['key']]
        choices = row.get('plot_selections', {})
        if not isinstance(choices, dict) or set(choices) - set(ENGINES):
            raise ValueError('Select at most one match per classifying tool')
        for engine, choice in choices.items():
            if not isinstance(choice, dict) or type(choice.get('rank')) is not int or not 1 <= choice['rank'] <= 6:
                raise ValueError('Match rank must be an integer from 1 to 6')
            run = next((r for r in record['runs'] if r['engine'] == engine
                        and r['execution_id'] == choice.get('execution_id')), None)
            if not run or run.get('figure', {}).get('status') != 'ready':
                raise ValueError('Selected configuration has no verified saved plot data')
            native = current_record(output, run)
            parent = output / 'attempts' / run['execution_id']
            attempt = parent / read_json(parent / 'current.json')['trial']
            if not native or file_hash(attempt / 'record.json') != run['record_sha256']:
                raise ValueError('Selected fit evidence changed; refresh the report')
            figure = run['figure']
            if not re.fullmatch(r'[0-9a-f]{64}', figure['identity']):
                raise ValueError('Invalid figure identity')
            request_path = output / 'figures' / figure['identity'] / 'request.json.gz'
            if file_hash(request_path) != figure['request_sha256']:
                raise ValueError('Selected numerical request failed verification')
            request = json.loads(gzip.decompress(request_path.read_bytes()))
            match = next((m for m in request['matches'] if m['candidate']['rank'] == choice['rank']), None)
            if (request['record_sha256'] != run['record_sha256'] or request['execution_id'] != run['execution_id']
                    or request['engine'] != engine or request['mode'] != run['mode']
                    or request['source']['spectrum_id'] != record['source']['spectrum_id']
                    or not match or not match['curve'].get('available')
                    or match['candidate'] not in native['candidates']):
                raise ValueError('Selected rank has no verified native model')
            filename = names[row['key']][engine]
            selected.append({'key': row['key'], 'object_id': record['source']['object_id'],
                'spectrum_id': record['source']['spectrum_id'], 'engine': engine, 'mode': run['mode'],
                'rank': choice['rank'], 'execution_id': run['execution_id'], 'record_sha256': run['record_sha256'],
                'candidate': match['candidate'], 'request': str(request_path),
                'request_sha256': figure['request_sha256'], 'filename': filename})
    if not selected:
        raise ValueError('Choose at least one saved match')
    return selected


def render_one(job_path):
    """Worker: reuse the master renderer's exact samples, limits and styling."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .grids import create_figure, flux_label, LABEL_SIZE
    from .products import save_jpg
    job = read_json(Path(job_path))
    path = Path(job['request'])
    if file_hash(path) != job['request_sha256']:
        raise ValueError('Numerical request changed before rendering')
    request = json.loads(gzip.decompress(path.read_bytes()))
    request['matches'] = [m for m in request['matches'] if m['candidate']['rank'] == job['rank']]
    if len(request['matches']) != 1:
        raise ValueError('Selected rank is unavailable')
    fig, panels = create_figure(request)
    try:
        for ax in fig.axes[1:]:
            fig.delaxes(ax)
        fig.set_size_inches(8.4, 5.4)
        fig.axes[0].set_position([.14, .19, .84, .48])
        fig.supxlabel(r'Observer wavelength (\AA)', fontsize=LABEL_SIZE, y=.025)
        fig.supylabel(flux_label(request['source']), fontsize=LABEL_SIZE, x=.02)
        path = save_jpg(fig, Path(job['stem']))
        validate_jpg(path)
        write_json(Path(job['result']), {'sha256': file_hash(path), 'panels': panels,
                                        'request_sha256': job['request_sha256'], 'rank': job['rank']})
    finally:
        plt.close(fig)


def _render(output, item):
    implementation = Path(__file__).parent
    identity = digest({'selection': item, 'implementation': {name: file_hash(implementation / name) for name in
                      ('selected.py', 'grids.py', 'display.py', 'limits.py', 'products.py')},
                      'style': file_hash(implementation.parent / 'plot_style.py')})
    directory = output / '.selected-plots' / identity
    jpg, result = directory / 'match.jpg', directory / 'product.json'
    if result.is_file() and jpg.is_file() and file_hash(jpg) == read_json(result)['sha256']:
        validate_jpg(jpg)
        return jpg
    directory.mkdir(parents=True, exist_ok=True)
    job = {**item, 'stem': str(directory / 'match'), 'result': str(result)}
    write_json(directory / 'job.json', job)
    env = {**os.environ, 'MPLBACKEND': 'Agg', 'PYTHONDONTWRITEBYTECODE': '1',
           'MPLCONFIGDIR': str(output / '.plot-cache' / 'matplotlib'),
           'XDG_CACHE_HOME': str(output / '.plot-cache' / 'xdg')}
    code = 'import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("spectypus.reporting.selected",run_name="__main__")'
    try:
        with (directory / 'render.log').open('w') as stream:
            process = subprocess.run([os.environ.get('SPECTYPUS_PLOT_PYTHON', sys.executable), '-c', code,
                                      str(implementation.parents[1]), str(directory / 'job.json')],
                                     env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=300)
    except subprocess.SubprocessError as exc:
        raise ValueError(f'Plot rendering timed out or failed; see {directory / "render.log"}') from exc
    if process.returncode:
        raise ValueError(f'Plot rendering failed; see {directory / "render.log"}')
    validate_jpg(jpg)
    if file_hash(jpg) != read_json(result)['sha256']:
        raise ValueError('Rendered JPG failed verification')
    return jpg


def export_selected(output, log):
    output = Path(output).expanduser().resolve()
    with output_lock(output):
        choices = resolve_selections(output, log)
        receipt_path = output / 'classification-plot-selections.json'
        previous = read_json(receipt_path) if receipt_path.exists() else {'schema': 'spectypus-selected-plots/1', 'files': []}
        if previous.get('schema') != 'spectypus-selected-plots/1':
            raise ValueError('Existing plot-selection record is not a Spectypus export')
        managed = {entry['filename']: entry for entry in previous['files']}
        for item in choices:
            target = output / item['filename']
            if target.is_symlink() or (target.exists() and
                    (item['filename'] not in managed or file_hash(target) != managed[item['filename']]['sha256'])):
                raise ValueError(f'Refusing to replace an unrecognized or edited file: {target.name}')
        # Finish every requested render before publishing any named outputs.
        prepared = [(item, _render(output, item)) for item in choices]
        files = []
        for item, jpg in prepared:
            entry = {**item, 'sha256': file_hash(jpg), 'report_identity': log['report_identity']}
            fd, temporary = tempfile.mkstemp(prefix='.selected-', dir=output)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(jpg.read_bytes())
                os.replace(temporary, output / item['filename'])
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            managed[item['filename']] = entry
            files.append(entry)
        write_json(receipt_path, {'schema': 'spectypus-selected-plots/1', 'files': list(managed.values())})
        return {'files': files, 'directory': str(output)}


if __name__ == '__main__':
    render_one(sys.argv[1])
