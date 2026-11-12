"""Isolated display preparation/rendering, never a classifier invocation."""
import gzip
import json
import math
from pathlib import Path
import sys

from ..features import features
from ..io import canonical, file_hash, read_json, write_json
from ..phases import phase_context
from ..pipeline import verify_attempt


def prepare(job_path):
    job = read_json(Path(job_path))
    directory = Path(job['attempt'])
    record = verify_attempt(directory, job['execution_id'])
    if not record or file_hash(directory / 'record.json') != job['record_sha256']:
        raise ValueError('Attempt changed before display preparation')
    payload = read_json(directory / 'fit_curves.json')
    if payload.get('wavelength_frame') != 'observer' or payload.get('wavelength_unit') != 'angstrom':
        raise ValueError('Saved curves need verified observer-frame Angstrom wavelengths')
    source = job['source']
    matches = []
    for candidate in record['candidates'][:min(6, record['config']['top_n'])]:
        native = next((c for c in payload['curves'] if c['template'] == candidate['template']
                       and math.isclose(c['score'], candidate['score'], rel_tol=1e-5, abs_tol=1e-8)
                       and (job['engine'] != 'ngsf' or c.get('galaxy') == candidate['native'].get('GALAXY'))), None)
        curve = {'available': False, 'reason': 'No saved curve for this native candidate'}
        if native and native.get('available'):
            points = native['observed']
            curve = {**{k: v for k, v in payload.items() if k != 'curves'}, **native,
                     'features': features(source.get('redshift'), points[0][0], points[-1][0],
                                          record['config'].get('telluric_windows', []))}
        matches.append({'candidate': candidate, 'curve': curve})
    contents = (directory / 'spectrum.txt').read_text()
    request = {'schema': 'spectypus-six-matches/1', 'source': source, 'engine': job['engine'],
               'mode': job['mode'], 'execution_id': job['execution_id'], 'record_sha256': job['record_sha256'],
               'curve_source_sha256': record['artifacts']['fit_curves.json'], 'matches': matches,
               'input_spectrum': {'available': True, 'contents': contents,
                                  'sha256': record['artifacts']['spectrum.txt']},
               'phase_context': phase_context(source)}
    from .display import make_transform
    request['display_transform'] = make_transform(request, {'attempt_path': str(directory),
                                                           'record_sha256': job['record_sha256']})
    if job['engine'] == 'ngsf':
        from .native_ngsf import NativeNGSF
        parameters = directory / 'parameters.json'
        params = read_json(parameters)
        if params['mask_galaxy_lines']:
            raise ValueError('Unreviewed native template-line masking')
        native = NativeNGSF(Path(record['config']['engines']['ngsf']['root']), parameters, record['provenance'])
        stdout = (directory / 'stdout.log').read_text()
        resolution = 30 if 'NGSF failed. Retrying for resolution = 30' in stdout else params['resolution']
        for match in matches:
            if match['curve']['available']:
                model, provenance = native.reconstruct(match, params, resolution)
                match['curve'].update(display_model=model, display_model_provenance=provenance)
        if any(file_hash(Path(p)) != expected for p, expected in native.files.items()):
            raise ValueError('Native template changed during model reconstruction')
    request['model_presentation'] = {'masking': 'none', 'classifier_runs': 0,
        'preprocessing_replays': int(job['engine'] == 'snid_sage'),
        'note': 'Saved models only; SAGE continuum replay is verified against saved observations.'}
    Path(job['request']).write_bytes(gzip.compress(canonical(request).encode(), mtime=0))


def render(job_path):
    from .grids import render_matches
    job = read_json(Path(job_path))
    result = render_matches((job['request'], job['stem']))
    jpg = Path(job['stem'] + '.jpg')
    result.update(product_hashes={'jpg': file_hash(jpg)}, request_sha256=file_hash(Path(job['request'])),
                  identity=job['identity'])
    write_json(Path(job['result']), result)


if __name__ == '__main__':
    {'prepare': prepare, 'render': render}[sys.argv[1]](sys.argv[2])
