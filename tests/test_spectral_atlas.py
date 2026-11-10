"""Portable report contracts, without running real classifiers or requiring plots."""
import base64
import hashlib
import importlib.util
from pathlib import Path
import re

import pytest

from spectypus.io import file_hash, read_json, write_json
from spectypus.pipeline import run_batch


spec = importlib.util.spec_from_file_location('spectral_atlas_export', Path(__file__).parents[1] / 'scripts/build_spectral_atlas.py')
atlas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atlas)


def test_export_freezes_verified_states_and_downloads(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    rows = [source_factory('good', z='.1'), source_factory('bad', 'SN-<script>', frame='unknown')]
    output = tmp_path / 'run'
    run_batch(manifest_factory(rows), config_factory(), output)
    original = {str(p): file_hash(p) for p in output.rglob('*') if p.is_file()}
    dest = tmp_path / 'export' / 'campaign-1'
    snapshot = atlas.capture(output, dest, 'test campaign')
    assert snapshot['counts'] == {'completed': 1, 'blocked': 1}
    assert snapshot['jobs'] == []
    assert snapshot['summary']['objects'][0]['proposed_class'] is None
    inventory = atlas.write_campaign(snapshot, dest, {}, 6)
    manifest = atlas.write_index(dest.parent, [snapshot], inventory, {'ready': 0, 'failed': 0})
    assert manifest['object_reports'] == 2
    index = (dest.parent / 'index.html').read_text()
    assert 'SN-&lt;script&gt;' in index and 'SN-<script>' not in index
    assert 'Exploratory automated classifications' not in index and 'No good match' in index
    for checksum, payload in re.findall(r'data-sha256="([a-f0-9]+)" href="data:[^;]+;base64,([^"]+)"', index):
        assert hashlib.sha256(base64.b64decode(payload)).hexdigest() == checksum
    assert not re.search(r'(?:src|href)="https?://', index)
    assert original == {str(p): file_hash(p) for p in output.rglob('*') if p.is_file()}
    # Current source changes after capture cannot change the frozen report.
    next((output / 'attempts').rglob('stdout.log')).write_text('tampered')
    assert snapshot['counts']['completed'] == 1
    altered = atlas.capture(output, tmp_path / 'changed', 'tampered')
    assert altered['counts'] == {'invalid_evidence': 1, 'blocked': 1}
    assert all(o['proposed_class'] is None for o in altered['summary']['objects'])


def test_export_rejects_changed_plan(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    output = tmp_path / 'run'
    run_batch(manifest_factory([source_factory(z='.1')]), config_factory(), output)
    plan = read_json(output / 'plan.json'); plan['spectra'][0]['object_id'] = 'changed'
    write_json(output / 'plan.json', plan)
    with pytest.raises(ValueError, match='integrity'):
        atlas.capture(output, tmp_path / 'export', 'test')


def test_ngsf_curve_requires_native_galaxy_score_and_template(tmp_path):
    candidate = {'template': 'SN-template', 'score': 2., 'native': {'GALAXY': 'E'}}
    curves = [{'template': 'SN-template', 'score': 2., 'galaxy': g, 'available': True,
               'observed': [[3000, 1], [9000, 2]], 'model': [[3000, 1], [9000, 2]]} for g in ('S', 'E')]
    write_json(tmp_path / 'fit_curves.json', {'curves': curves})
    record = {'candidates': [candidate], 'artifacts': {'fit_curves.json': 'verified upstream'}, 'attempt_path': str(tmp_path)}
    plan = {'config': {}}
    run = {'engine': 'ngsf', 'mode': 'free', 'execution_id': 'test'}
    curve = atlas.best_curve(plan, run, record, {'redshift': .1})
    assert curve['galaxy'] == 'E' and curve['rank'] == 1
    candidate['score'] = 3.
    assert not atlas.best_curve(plan, run, record, {'redshift': .1})['available']


def test_native_columns_use_frozen_record_not_newer_pointer(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    output = tmp_path / 'run'
    run_batch(manifest_factory([source_factory(z='.1')]), config_factory(), output)
    path = tmp_path / 'export' / 'snapshot.json'
    snapshot = atlas.capture(output, path.parent, 'test')
    saved = next(r for r in snapshot['runs'] if r['matches'])
    for match in saved['matches']:
        match.pop('native')
    record_path = Path(saved['attempt_path']) / 'record.json'
    record = read_json(record_path)
    record['candidates'][0]['native'] = {'changed': True}
    write_json(record_path, record)
    with pytest.raises(ValueError, match='Frozen attempt changed'):
        atlas.enrich_native(snapshot, path)


def test_ngsf_table_preserves_extinction_and_host_values():
    run = {'engine': 'ngsf', 'matches': [{'rank': 1, 'score': 2., 'qualified': False,
            'native': {'A_v': '-0.2', 'GALAXY': 'E', 'Frac(SN)': '0.8', 'Frac(gal)': '0.2'}}]}
    html = atlas.candidate_table(run)
    assert 'A_v (mag)' in html and '<td>-0.2</td>' in html
    assert '<td>False</td>' in html and '<td>0.2</td>' in html


def test_finished_no_match_failure_pending_and_duplicate_remain_distinct(tmp_path, source_factory, manifest_factory, config_factory, fake_engine):
    a = source_factory('a', z='.1')
    rows = [a, {**a, 'spectrum_id': 'repeated'}, source_factory('b', flux=4, z='.1'), source_factory('c', flux=7, z='.1')]
    output = tmp_path / 'run'
    run_batch(manifest_factory(rows), config_factory(), output, max_runs=2)
    records = sorted((output / 'attempts').rglob('record.json'))
    for path, state in zip(records, ('no_good_match', 'failed')):
        record = read_json(path); record['status'] = state
        record['reason'] = 'synthetic outcome'
        for m in record['candidates']:
            m['qualified'] = False
        write_json(path, record); path.with_name('record.sha256').write_text(file_hash(path) + '\n')
    snapshot = atlas.capture(output, tmp_path / 'export', 'test')
    assert snapshot['counts'] == {'no_good_match': 1, 'failed': 1, 'duplicate': 1, 'pending': 1}
    assert snapshot['summary']['objects'][0]['proposed_class'] is None


def test_portable_card_has_only_jpg_image_download(tmp_path):
    from PIL import Image
    from validate_spectral_atlas import Report
    stem = atlas.key('spectrum')
    (tmp_path / 'figures').mkdir(); (tmp_path / 'data').mkdir()
    Image.new('RGB', (20, 20)).save(tmp_path / 'figures/plot.jpg', dpi=(300, 300))
    write_json(tmp_path / 'data' / (stem + '.json'), {'curves': []})
    result = {'status': 'ready', 'jpg': 'plot.jpg', 'panels': []}
    html = atlas.figure_card('spectrum', {'object_id': 'SN-A'}, tmp_path, {stem: result})
    report = Report(); report.feed(html)
    assert report.images == 1 and report.downloads == 2
    assert '.pdf' not in html and 'application/pdf' not in html
    with pytest.raises(AssertionError, match='PDF download'):
        Report().feed('<a download="plot.pdf" href="data:application/pdf;base64,AA==">PDF</a>')
