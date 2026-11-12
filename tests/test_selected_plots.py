import copy
import gzip
import json
from pathlib import Path
import re

import pytest

from spectypus.io import canonical, digest, file_hash, read_json, write_json
from spectypus.pipeline import run_batch
from spectypus.reporting import report, selected


@pytest.fixture
def selection_output(tmp_path, source_factory, manifest_factory, config_factory, fake_engine, monkeypatch):
    Image = pytest.importorskip('PIL.Image')
    from conftest import sage_payload
    payload = sage_payload()
    payload['candidates'].append({**payload['candidates'][0], 'template_name': 'template-B',
                                  'template_epoch_id': 'template-B@2', 'age_days': 2, 'score_value': 4.})
    fake_engine.write_text('import json,sys\nfrom pathlib import Path\n' +
                          f'Path(sys.argv[1]).write_text(json.dumps({payload!r}))\n')

    def grid(output, source, run, record, attempt):
        folder = output / 'figures' / digest(run['execution_id'])
        folder.mkdir(parents=True, exist_ok=True)
        request = {'execution_id': run['execution_id'], 'record_sha256': file_hash(attempt / 'record.json'),
                   'engine': run['engine'], 'mode': run['mode'], 'source': source,
                   'matches': [{'candidate': m, 'curve': {'available': True}} for m in record['candidates']]}
        (folder / 'request.json.gz').write_bytes(gzip.compress(canonical(request).encode()))
        Image.new('RGB', (20, 20)).save(folder / 'master.jpg', dpi=(300, 300))
        return {'status': 'ready', 'identity': folder.name, 'directory': str(folder), 'jpg': 'master.jpg',
                'request_sha256': file_hash(folder / 'request.json.gz'),
                'panels': [{'rank': m['rank'], 'status': 'rendered'} for m in record['candidates']]}

    calls = []
    def render(output, item):
        calls.append((item['engine'], item['mode'], item['rank']))
        jpg = output / ('test-' + item['execution_id'] + '-' + str(item['rank']) + '.jpg')
        Image.new('RGB', (20, 20), color=(item['rank'], 0, 0)).save(jpg, dpi=(300, 300))
        return jpg
    monkeypatch.setattr(report, 'ensure_grid', grid)
    monkeypatch.setattr(selected, '_render', render)

    def build(duplicate=False, second_name='SN-A'):
        rows = [source_factory(z='.05')]
        if duplicate:
            rows.append(source_factory('second', object_id=second_name, z='.05', flux=2.))
        output = tmp_path / 'report'
        run_batch(manifest_factory(rows), config_factory(redshift_mode='both'), output)
        data = selected.evidence(output)
        log = {'schema': 'spectypus-night-log/1', 'report_identity': data['report_identity'], 'rows': []}
        for entry in data['records']:
            run = next(r for r in entry['runs'] if r['mode'] == 'free')
            log['rows'].append({'key': 'c0:' + entry['source']['spectrum_id'], 'Name': '../../unsafe-name',
                'plot_selections': {'snid_sage': {'execution_id': run['execution_id'], 'rank': 2}}})
        return output, log, data, calls
    return build


def test_selected_mode_rank_named_output_and_preserved_evidence(selection_output):
    output, log, data, calls = selection_output()
    protected = {p: file_hash(p) for p in (output / 'attempts').rglob('*') if p.is_file()}
    html_hash = file_hash(output / 'index.html')
    result = selected.export_selected(output, log)
    entry = result['files'][0]
    assert entry['filename'] == 'PLOT_Classification_SNID-SAGE_SN-A.jpg'
    assert entry['mode'] == 'free' and entry['rank'] == 2
    assert 'template-B' in entry['candidate']['template']
    assert file_hash(output / entry['filename']) == entry['sha256']
    assert calls == [('snid_sage', 'free', 2)]
    fixed = next(r for r in data['records'][0]['runs'] if r['mode'] == 'fixed')
    log['rows'][0]['plot_selections']['snid_sage'] = {'execution_id': fixed['execution_id'], 'rank': 1}
    replacement = selected.export_selected(output, log)['files'][0]
    assert replacement['filename'] == entry['filename'] and replacement['sha256'] != entry['sha256']
    assert protected == {p: file_hash(p) for p in protected}
    assert file_hash(output / 'index.html') == html_hash
    (output / entry['filename']).write_bytes(b'user-edited')
    with pytest.raises(ValueError, match='unrecognized or edited'):
        selected.export_selected(output, log)
    assert len(calls) == 2


@pytest.mark.parametrize('problem', ['identity', 'rank', 'engine', 'configuration', 'tampered', 'empty',
                                     'native', 'sidecar', 'rows', 'bool-rank'])
def test_invalid_selection_never_renders(selection_output, problem):
    output, log, data, calls = selection_output()
    choice = log['rows'][0]['plot_selections']['snid_sage']
    if problem == 'identity': log['report_identity'] = 'stale'
    if problem == 'rank': choice['rank'] = 7
    if problem == 'bool-rank': choice['rank'] = True
    if problem == 'engine': log['rows'][0]['plot_selections']['ngsf'] = copy.deepcopy(choice)
    if problem == 'configuration': choice['execution_id'] = '../wrong'
    if problem == 'empty': log['rows'][0]['plot_selections'] = {}
    if problem == 'rows': log['rows'] = []
    if problem == 'sidecar': (output / 'classification-report-evidence.json').write_text('{}')
    if problem == 'native':
        parent = output / 'attempts' / choice['execution_id']
        (parent / read_json(parent / 'current.json')['trial'] / 'record.json').write_text('{}')
    if problem == 'tampered':
        run = next(r for r in data['records'][0]['runs'] if r['execution_id'] == choice['execution_id'])
        (Path(run['figure']['directory']) / 'request.json.gz').write_bytes(b'changed')
    with pytest.raises(ValueError): selected.export_selected(output, log)
    assert calls == [] and not list(output.glob('PLOT_Classification_*.jpg'))


def test_repeated_objects_have_distinct_filenames(selection_output):
    output, log, _, _ = selection_output(duplicate=True)
    files = selected.export_selected(output, log)['files']
    assert len({f['filename'] for f in files}) == 2
    assert all(re.fullmatch(r'PLOT_Classification_SNID-SAGE_SN-A_[a-f0-9]{10}\.jpg', f['filename']) for f in files)


def test_names_remain_distinct_on_case_insensitive_filesystems(selection_output):
    output, log, _, _ = selection_output(duplicate=True, second_name='sn-a')
    files = selected.export_selected(output, log)['files']
    assert len({f['filename'].casefold() for f in files}) == 2


def test_plot_log_cli_exports_saved_choices(selection_output, capsys):
    from spectypus.cli import main
    output, log, _, _ = selection_output()
    path = output / 'reviewer.json'
    write_json(path, log)
    assert main(['plot-log', '--output', str(output), '--log', str(path)]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response['files'][0]['rank'] == 2 and response['files'][0]['mode'] == 'free'
