"""Installed, automatic HTML uses verified saved evidence and no engine runtime."""
import base64
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from spectypus.cli import main
from spectypus.io import file_hash, read_json, write_json
from spectypus.pipeline import run_batch, summarize_output


class Report(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.downloads, self.ids, self.links, self.scripts = {}, set(), [], []
        self.log_text, self.in_log = '', False
        self.feed(path.read_text())

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        if tag == 'script':
            self.scripts.append(attrs)
            self.in_log = attrs.get('id') == 'night-log-data'
        if tag == 'a':
            self.links.append(attrs['href'])
            if attrs.get('download'):
                self.downloads[attrs['download']] = base64.b64decode(attrs['href'].split(',', 1)[1])

    def handle_data(self, text):
        if self.in_log:
            self.log_text += text

    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_log = False

    @property
    def evidence(self):
        return json.loads(self.downloads['classification-report-evidence.json'])


def test_batch_cli_report_is_offline_precise_and_resumable(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    source = source_factory(object_id='SN-A </script><img src="x" onerror="oops">')
    manifest, cfg, output = manifest_factory([source]), config_factory(), tmp_path / 'batch'
    assert main(['run', '--manifest', str(manifest), '--config', str(cfg), '--output', str(output)]) == 0
    document = Report(output / 'index.html')
    assert document.evidence['counts'] == {'completed': 1}
    assert document.evidence['records'][0]['source']['object_id'] == source['object_id']
    assert json.loads(document.log_text)['records'][0]['source']['object_id'] == source['object_id']
    assert not any(s.get('src') for s in document.scripts)
    assert all(not url.startswith(('http:', 'https:')) for url in document.links)
    assert all(url[1:] in document.ids for url in document.links if url.startswith('#'))
    for name in ('classification_summary.csv', 'matches.csv', 'run_status.csv'):
        assert document.downloads[name] == (output / name).read_bytes()
    html = (output / 'index.html').read_text()
    assert '<h1>batch</h1>' in html
    assert '<img src="x"' not in html and '.pdf' not in html
    assert '0.100' in html and '5.000' in html and 'Ia-norm' in html
    assert not (output / 'best_matches.csv').exists()
    before = (output / 'index.html').read_bytes()
    assert run_batch(manifest, cfg, output)['invocation']['reused'] == 1
    assert (output / 'index.html').read_bytes() == before


def test_saved_export_works_after_relocation_without_inputs_or_engines(source_factory, manifest_factory, config_factory, fake_engine, tmp_path, monkeypatch):
    source = source_factory()
    manifest, cfg, old = manifest_factory([source]), config_factory(), tmp_path / 'old'
    run_batch(manifest, cfg, old)
    output = tmp_path / 'relocated'
    shutil.move(old, output)
    Path(source['path']).unlink()
    manifest.unlink()
    cfg.unlink()
    fake_engine.unlink()
    from spectypus import pipeline
    monkeypatch.setattr(pipeline, 'execute_one', lambda *a, **kw: pytest.fail('report must never fit'))
    monkeypatch.setattr(pipeline, 'make_plan', lambda *a, **kw: pytest.fail('report must use saved plan'))
    protected = {p: file_hash(p) for p in (output / 'attempts').rglob('*') if p.is_file()}
    log = output / 'night-log.json'
    log.write_text('{"reviewer":"unchanged"}')
    assert main(['summarize', '--output', str(output)]) == 0
    assert Report(output / 'index.html').evidence['counts'] == {'completed': 1}
    assert log.read_text() == '{"reviewer":"unchanged"}'
    assert protected == {p: file_hash(p) for p in protected}


def test_flux_display_metadata_keeps_saved_reviewer_log_identity(source_factory, manifest_factory, config_factory, fake_engine, tmp_path, monkeypatch):
    from spectypus.reporting import report
    output = tmp_path / 'unit-label'
    run_batch(manifest_factory([source_factory()]), config_factory(), output)
    before = Report(output / 'index.html')
    original = report.display_sources
    monkeypatch.setattr(report, 'display_sources', lambda out, sources: [
        {**s, 'flux_unit': 'mJy', 'flux_unit_source': 'declared', 'tns_name': '2026abc',
         'efosc_typing_metadata': {'sha256': 'new-receipt'}} for s in original(out, sources)])
    summarize_output(output)
    after = Report(output / 'index.html')
    assert json.loads(before.log_text)['identity'] == json.loads(after.log_text)['identity']
    assert after.evidence['records'][0]['source']['flux_unit'] == 'mJy'
    assert 'copy-night-log' in after.ids


def test_partial_and_reselected_plan_excludes_old_results(source_factory, manifest_factory, config_factory, fake_engine, tmp_path, monkeypatch):
    a, b = source_factory('a'), source_factory('b', 'SN-B', flux=2)
    manifest, cfg, output = manifest_factory([a, b]), config_factory(), tmp_path / 'partial'
    from spectypus import pipeline
    execute = pipeline.execute_one

    def check_pending(*args):
        assert Report(output / 'index.html').evidence['counts'] == {'pending': 2}
        return execute(*args)

    monkeypatch.setattr(pipeline, 'execute_one', check_pending)
    run_batch(manifest, cfg, output, max_runs=1)
    assert Report(output / 'index.html').evidence['counts'] == {'completed': 1, 'pending': 1}
    manifest_factory([b])
    run_batch(manifest, cfg, output, execute=False)
    evidence = Report(output / 'index.html').evidence
    assert evidence['counts'] == {'pending': 1}
    assert [r['source']['object_id'] for r in evidence['records']] == ['SN-B']


def test_corrupt_attempt_is_visible_but_excluded_from_matches(source_factory, manifest_factory, config_factory, fake_engine, tmp_path):
    output = tmp_path / 'invalid'
    run_batch(manifest_factory([source_factory()]), config_factory(), output)
    attempt = next((output / 'attempts').rglob('record.json'))
    payload = read_json(attempt)
    payload['candidates'][0]['template'] = 'corrupted'
    write_json(attempt, payload)
    assert main(['summarize', '--output', str(output)]) == 1
    report = Report(output / 'index.html')
    assert report.evidence['counts'] == {'invalid_evidence': 1}
    assert report.evidence['records'][0]['runs'][0]['matches'] == []
    assert 'corrupted' not in (output / 'index.html').read_text()
    html = (output / 'index.html').read_bytes()
    plan = read_json(output / 'plan.json')
    plan['spectra'][0]['object_id'] = 'bad plan'
    write_json(output / 'plan.json', plan)
    with pytest.raises(ValueError, match='integrity'):
        summarize_output(output)
    assert (output / 'index.html').read_bytes() == html


@pytest.mark.parametrize('outcome', ['failed', 'no_good_match', 'blocked', 'duplicate'])
def test_non_success_states_are_distinct(source_factory, manifest_factory, config_factory, fake_engine, tmp_path, outcome):
    rows = [source_factory()]
    if outcome == 'failed':
        fake_engine.write_text('raise RuntimeError("native failure")')
    elif outcome == 'no_good_match':
        fake_engine.write_text(fake_engine.read_text().replace("'classification_success': True", "'classification_success': False")
                               .replace("'passes_threshold': True", "'passes_threshold': False")
                               .replace("'score_value': 5.0", "'score_value': 0.1"))
    elif outcome == 'blocked':
        Path(rows[0]['path']).write_text('3000 NaN\n5000 1\n9000 2\n')
    else:
        rows.append(source_factory('duplicate'))
    output = tmp_path / 'out'
    run_batch(manifest_factory(rows), config_factory(), output)
    evidence = Report(output / 'index.html').evidence
    assert evidence['counts'][outcome] == 1
    if outcome == 'no_good_match':
        assert evidence['records'][0]['runs'][0]['matches'][0]['qualified'] is False
        assert 'Bad match' in (output / 'index.html').read_text()


def test_automatic_draft_priority_and_fixed_z_provenance():
    from spectypus.reporting.presentation import summary_values
    candidate = {'rank': 1, 'qualified': True, 'native_class': 'Ia', 'redshift': .1234567, 'phase_days': -5}
    runs = [{'execution_id': name, 'status': 'completed', 'engine': engine, 'mode': mode,
             'matches': [{**candidate, 'native_class': kind}]} for name, engine, mode, kind in
            [('a', 'snid_sage', 'free', 'II'), ('b', 'ngsf', 'fixed', 'Ib'), ('c', 'ngsf', 'free', 'Ia')]]
    values, tips = summary_values({'object_id': 'target', 'redshift': .12}, runs)
    assert values == ['target', 'SNIa', '0.123', '-5 d', '—']
    assert '0.1234567' in tips['redshift']
    values, _ = summary_values({'object_id': 'target', 'redshift': .12}, [runs[1]])
    assert values[2] == '—'
    values, _ = summary_values({'object_id': 'target', 'host_redshift': .087727,
                               'narrow_line_redshift': .09, 'narrow_line_redshift_source': 'reviewer'}, runs)
    assert values[2] == '0.090 (host 0.087727)'


def test_embedded_master_grid_keeps_folder_title(source_factory, manifest_factory, config_factory, fake_engine, tmp_path, monkeypatch):
    from spectypus.reporting import report
    from spectypus.io import write_json
    folder = tmp_path / 'plots'
    folder.mkdir()
    # The HTML layer receives an already-verified renderer result.
    (folder / 'master.jpg').write_bytes(b'preverified image bytes')
    (folder / 'request.json.gz').write_bytes(b'preverified numerical bytes')
    monkeypatch.setattr(report, 'ensure_grid', lambda *args: {'status': 'ready', 'directory': str(folder), 'jpg': 'master.jpg'})
    output = tmp_path / '2026-10-28'
    run_batch(manifest_factory([source_factory()]), config_factory(), output)
    html = (output / 'index.html').read_text()
    assert '<h1>2026-10-28</h1>' in html
    assert '<title>2026-10-28 · Classification Report</title>' in html
    assert 'class="enlarge"' in html and 'image/jpeg;base64,' in html
    evidence = Report(output / 'index.html').evidence
    assert evidence['title'] == '2026-10-28'
    assert read_json(output / 'summary.json')['report']['figures'] == 1


def test_modes_share_evidence_and_review_identity(source_factory, manifest_factory, config_factory,
                                                 fake_engine, tmp_path):
    output = tmp_path / 'two-modes'
    run_batch(manifest_factory([source_factory('a'), source_factory('b', flux=3)]),
              config_factory(), output)
    before = Report(output / 'index.html')
    protected = {p: file_hash(p) for p in (output / 'attempts').rglob('*') if p.is_file()}
    assert main(['summarize', '--output', str(output), '--display', 'atlas']) == 0
    after = Report(output / 'index.html')
    assert before.evidence == after.evidence
    assert json.loads(before.log_text) == json.loads(after.log_text)
    html = (output / 'index.html').read_text()
    assert '/ SpectralAtlas' in html and 'id="atlas-search"' in html
    assert html.count('class="atlas-object"') == 1
    assert html.count('class="atlas-epoch"') == 2
    assert all(url[1:] in after.ids for url in after.links if url.startswith('#'))
    assert protected == {p: file_hash(p) for p in protected}
    summarize_output(output, display='report')
    assert 'id="atlas-search"' not in (output / 'index.html').read_text()
    with pytest.raises(ValueError, match='display'):
        summarize_output(output, display='unknown')
