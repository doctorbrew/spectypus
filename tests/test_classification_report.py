"""Report selections preserve evidence while using ordinary document navigation."""
import base64
import copy
import gzip
from html.parser import HTMLParser
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from build_classification_report import build_report
from build_spectral_browser import fit_card
from spectral_atlas_products import PLOT_OUTPUT
from spectypus.io import canonical, file_hash, read_json, write_json
from validate_spectral_browser import BrowserHTML


class ReportHTML(BrowserHTML):
    def __init__(self):
        super().__init__()
        self.downloads = {}
        self.articles = []

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('download'):
            self.downloads[attrs['download']] = base64.b64decode(attrs['href'].split(',', 1)[1])
        if tag == 'article':
            self.articles.append(attrs['id'])


def seal(root):
    write_json(root / 'checksums.json', {str(p.relative_to(root)): file_hash(p)
               for p in root.rglob('*') if p.is_file() and p.name != 'checksums.json'})


@pytest.fixture
def saved_browser(tmp_path):
    from PIL import Image
    root = tmp_path / 'browser'
    (root / 'data').mkdir(parents=True)
    (root / 'figures').mkdir()
    template = tmp_path / 'SN2012dn.dat'
    template.write_text('4000 1\n5000 2\n')
    source = {'spectrum_id': 'night:<test>.dat', 'object_id': 'SN-<script>',
              'instrument': 'NOT', 'mjd': 59010., 'redshift': .1, 'redshift_source': 'catalogue',
              'wavelength_frame': 'observer', 'wavelength_unit': 'angstrom', 'phase_rest_days': 0}
    runs, results, requests, locations = [], {}, {}, {}
    for mode in ('fixed', 'free'):
        for engine in ('snid_sage', 'ngsf'):
            ident = f'{engine}-{mode}'
            matches = [{'rank': rank, 'template': 'Ia-pec/2012dn/epoch1', 'native_class': 'Ia',
                        'native_subtype': 'Ia-pec', 'phase_days': 5., 'redshift': .123456,
                        'score': 1.234567 + rank, 'metric': 'rlap' if engine == 'snid_sage' else 'chi2',
                        'metric_direction': 'higher' if engine == 'snid_sage' else 'lower', 'qualified': rank < 4,
                        'native': {'A_v': .2, 'GALAXY': 'SB2', 'Frac(gal)': .05}} for rank in range(1, 7)]
            run = {'spectrum_id': source['spectrum_id'], 'object_id': source['object_id'],
                   'engine': engine, 'mode': mode, 'execution_id': ident, 'plot_key': ident,
                   'record_sha256': 'saved-record', 'status': 'completed', 'primary': mode == 'fixed',
                   'reason': '', 'matches': matches, 'curve_ranks': list(range(1, 7))}
            runs.append(run)
            request = {'source': source, 'execution_id': ident, 'record_sha256': 'saved-record',
                       'engine': engine, 'mode': mode, 'matches': [{'candidate': m} for m in matches]}
            path = root / 'data' / (ident + '.json.gz')
            path.write_bytes(gzip.compress(canonical(request).encode(), mtime=0))
            requests[str(path.relative_to(root))] = file_hash(path)
            jpg = root / 'figures' / (ident + '.jpg')
            Image.new('RGB', (20, 20)).save(jpg, dpi=(300, 300))
            results[ident] = {'status': 'ready', 'jpg': jpg.name, 'layout': '2x3-matches-only',
                              'panels': [], 'product_hashes': {'jpg': file_hash(jpg)}}
            locations[ident] = {str(m['rank']): {'path': str(template), 'template': m['template']} for m in matches}
    blocked = {**source, 'spectrum_id': 'unknown-frame.dat', 'object_id': 'AT-test', 'frame_assumed': True}
    runs.append({**runs[0], 'spectrum_id': blocked['spectrum_id'], 'object_id': blocked['object_id'],
                 'execution_id': 'blocked', 'plot_key': 'blocked', 'status': 'blocked',
                 'reason': 'Unsupported wavelength frame', 'matches': [], 'curve_ranks': []})
    snapshot = {'browser_campaign': 1, 'label': 'Night <one>', 'checked_at': '2026-11-06T12:00:00+00:00',
                'plan_id': 'plan1', 'spectra': [source, blocked], 'runs': runs, 'phase_references': {}}
    write_json(root / 'browser-snapshot.json', {'snapshots': [snapshot]})
    write_json(root / 'figure-results.json', results)
    write_json(root / 'render-contract.json', {'plot_output': PLOT_OUTPUT, 'requests': requests})
    write_json(root / 'model-restoration.json', {'status': 'passed', 'scientific_fields_unchanged': True})
    write_json(root / 'template-locations.json', {'locations': locations, 'files': {str(template): file_hash(template)}})
    write_json(root / 'manifest.json', {'plot_output': PLOT_OUTPUT, 'plot_presentation': {'model_masking': 'none'},
              'render_contract_sha256': file_hash(root / 'render-contract.json'),
              'model_restoration_sha256': file_hash(root / 'model-restoration.json'),
              'rank_table': {'template_locations_sha256': file_hash(root / 'template-locations.json')}})
    seal(root)
    return root


def test_report_keeps_all_configs_states_ranks_and_exact_downloads(saved_browser, tmp_path):
    before = {str(p): file_hash(p) for p in saved_browser.rglob('*') if p.is_file()}
    output = tmp_path / 'report.html'
    result = build_report(saved_browser, output, title='Night <test>')
    assert (result['spectra'], result['fits'], result['figures']) == (2, 5, 4)
    html = output.read_text()
    parsed = ReportHTML(); parsed.feed(html)
    assert 'Classification Report' in html and 'Night &lt;test&gt;' in html
    assert 'SN-<script>' not in html and 'Unsupported wavelength frame' in html
    assert 'SN2012dn (Ia-pec, +5d)' in html and 'SB2 (5%)' in html
    assert 'title="0.123456">0.123</span>' in html and 'Filename: &lt;test&gt;.dat' in html
    assert len(parsed.articles) == 2 and len(parsed.executions) == 5 and len(parsed.rank_tables) == 4
    assert parsed.sn_count == parsed.epochs == 0
    assert 'sn-sidebar' not in html and 'epoch-jump' not in html and 'browser.js' not in html
    assert all(link[1:] in parsed.ids for link in parsed.links if link.startswith('#'))
    assert all(link.startswith(('data:', 'file:', '#')) for link in parsed.links)
    assert all(image.startswith('data:image/jpeg;base64,') for image in parsed.images)
    assert '.pdf' not in html and 'Fieldnotes' not in html
    snapshot = read_json(saved_browser / 'browser-snapshot.json')['snapshots'][0]
    evidence = json.loads(parsed.downloads.pop('classification-report-evidence.json'))
    for record in evidence['records']:
        assert record['source'] in snapshot['spectra']
        assert all(run in snapshot['runs'] for run in record['runs'])
    for name, data in parsed.downloads.items():
        path = saved_browser / ('figures' if name.endswith('.jpg') else 'data') / name
        assert data == path.read_bytes()
    # Same compact tables as the atlas; the report changes only navigation/layout.
    atlas = BrowserHTML()
    results = read_json(saved_browser / 'figure-results.json')
    locations = read_json(saved_browser / 'template-locations.json')['locations']
    for run in snapshot['runs']:
        atlas.feed(fit_card(run, results, '', locations=locations.get(run['plot_key'])))
    assert parsed.rank_tables == atlas.rank_tables
    assert before == {str(p): file_hash(p) for p in saved_browser.rglob('*') if p.is_file()}


def test_selection_keeps_campaigns_distinct_and_avoids_unused_products(saved_browser, tmp_path):
    frozen = read_json(saved_browser / 'browser-snapshot.json')
    other = copy.deepcopy(frozen['snapshots'][0]); other['browser_campaign'] = 2; other['label'] = 'Second campaign'
    frozen['snapshots'].append(other)
    write_json(saved_browser / 'browser-snapshot.json', frozen); seal(saved_browser)
    # These plots are outside the explicitly selected blocked input.
    next((saved_browser / 'figures').glob('*.jpg')).write_bytes(b'changed but not selected')
    result = build_report(saved_browser, tmp_path / 'selection.html', spectrum_ids=['unknown-frame.dat'])
    assert result['spectra'] == 2 and result['fits'] == 2 and result['figures'] == 0
    result = build_report(saved_browser, tmp_path / 'campaign.html', spectrum_ids=['unknown-frame.dat'], campaigns=[2])
    assert result['spectra'] == 1


@pytest.mark.parametrize('name', ['browser-snapshot.json', 'figure-results.json', 'data/ngsf-fixed.json.gz', 'figures/ngsf-fixed.jpg'])
def test_changed_selected_evidence_fails_before_writing(saved_browser, tmp_path, name):
    with (saved_browser / name).open('ab') as stream: stream.write(b'changed')
    output = tmp_path / 'bad.html'
    with pytest.raises(ValueError, match='Changed'):
        build_report(saved_browser, output)
    assert not output.exists()


def test_candidate_disagreement_rejected_even_with_updated_checksum(saved_browser, tmp_path):
    path = saved_browser / 'data/ngsf-fixed.json.gz'
    request = json.loads(gzip.decompress(path.read_bytes()))
    request['matches'][0]['candidate']['score'] = 0
    path.write_bytes(gzip.compress(canonical(request).encode())); seal(saved_browser)
    with pytest.raises(ValueError, match='disagrees with selected fit'):
        build_report(saved_browser, tmp_path / 'bad.html')


def test_unknown_selection_and_existing_output_are_not_silently_replaced(saved_browser, tmp_path):
    output = tmp_path / 'report.html'
    with pytest.raises(ValueError, match='missing'):
        build_report(saved_browser, output, spectrum_ids=['does-not-exist'])
    assert not output.exists()
    output.write_text('previous report')
    with pytest.raises(FileExistsError): build_report(saved_browser, output)
    assert output.read_text() == 'previous report'
    with pytest.raises(ValueError, match='outside'):
        build_report(saved_browser, saved_browser / 'new.html')


def test_changed_local_template_is_not_linked_as_verified(saved_browser, tmp_path):
    (tmp_path / 'SN2012dn.dat').write_text('changed template')
    with pytest.raises(ValueError, match='Changed local template'):
        build_report(saved_browser, tmp_path / 'bad.html')


def test_compact_report_defaults_to_folder_and_removes_explanatory_sections(saved_browser, tmp_path):
    output = tmp_path / '2026-10-28' / 'index.html'
    build_report(saved_browser, output)
    html = output.read_text()
    assert '<h1>2026-10-28</h1>' in html
    for text in ('Run record', 'Saved classification evidence', 'Primary evidence',
                 'Diagnostic fit;', 'Plot display details', 'Exploratory automated',
                 'Automated candidates for review', 'Supplied target phase', 'unknown-instrument'):
        assert text not in html
    assert '<th scope="col">Name</th><th scope="col">Type</th><th scope="col">z</th><th scope="col">Phase</th><th scope="col">Survey</th>' in html


def test_reviewed_summary_preserves_native_results_and_host_precision(saved_browser, tmp_path):
    snapshot = read_json(saved_browser / 'browser-snapshot.json')['snapshots'][0]
    run = next(r for r in snapshot['runs'] if r['execution_id'] == 'ngsf-free')
    summary = tmp_path / 'review.json'
    write_json(summary, {'schema': 'spectypus-reviewed-summary/1', 'records': [{
        'campaign': 1, 'spectrum_id': run['spectrum_id'], 'execution_id': run['execution_id'],
        'record_sha256': run['record_sha256'], 'rank': 1, 'reference': 'test reviewer selection',
        'redshift': .089123, 'redshift_method': 'narrow_lines', 'host_redshift': .087727,
        'type': 'SNIa-03fg or SNIa', 'phase': 'around peak', 'survey': 'ATLAS'}]})
    output = tmp_path / 'reviewed.html'
    build_report(saved_browser, output, summary_path=summary)
    html = output.read_text()
    assert '0.089 (host 0.087727)' in html and 'narrow_lines' in html
    assert 'SNIa-03fg or SNIa' in html and 'around peak' in html and 'ATLAS' in html
    assert 'title="0.123456">0.123</span>' in html  # native candidate untouched
    payload = read_json(summary); payload['records'][0]['record_sha256'] = 'stale'
    write_json(summary, payload)
    with pytest.raises(ValueError, match='saved fit record'):
        build_report(saved_browser, tmp_path / 'stale.html', summary_path=summary)


def test_compact_fields_do_not_invent_host_survey_instrument_or_spectral_z():
    from spectral_atlas_presentation import summary_values, spectrum_heading
    source = {'object_id': 'SN2018avk', 'spectrum_id': 'chen:NOT.dat',
              'redshift': .132, 'instrument': 'unknown-instrument', 'ztf_id': 'ZTF18aaisyyp'}
    values, _ = summary_values(source, [])
    assert values == ['SN2018avk', '—', '—', '—', '—']
    heading, filename = spectrum_heading(source)
    assert heading == source['object_id'] and 'unknown-instrument' not in heading
    assert 'Discovery MJD: —' in filename and 'Observed MJD:' in filename
    assert filename.endswith('Filename: NOT.dat')
    run = {'execution_id': 'fixed', 'mode': 'fixed', 'record_sha256': 'sha',
           'matches': [{'rank': 1, 'native_class': 'Ia', 'redshift': .132, 'phase_days': 0}]}
    review = {'execution_id': 'fixed', 'record_sha256': 'sha', 'rank': 1}
    values, _ = summary_values(source, [run], review)
    assert values[1:4] == ['SNIa', '—', '+0 d']  # fixed z is not a spectral measurement
    run['mode'] = 'free'
    assert summary_values(source, [run], review)[0][2] == '0.132'
    source.update(narrow_line_redshift=.088877, narrow_line_redshift_source='saved line measurement', host_redshift=.087727)
    assert summary_values(source, [run], review)[0][2] == '0.089 (host 0.087727)'


def test_automatic_summary_uses_documented_priority_not_cross_engine_scores(saved_browser):
    from spectral_atlas_presentation import automatic_selection, summary_values
    snapshot = read_json(saved_browser / 'browser-snapshot.json')['snapshots'][0]
    runs = snapshot['runs'][:4]
    run, candidate = automatic_selection(runs)
    assert (run['engine'], run['mode'], candidate['rank']) == ('ngsf', 'free', 1)
    run['matches'][0]['qualified'] = False
    assert automatic_selection(runs)[1]['rank'] == 2
    for match in run['matches']: match['qualified'] = False
    assert automatic_selection(runs)[0]['engine'] == 'snid_sage'
    for row in runs: row['status'] = 'no_good_match'
    assert summary_values(snapshot['spectra'][0], runs)[0][1:4] == ['—', '—', '—']


def test_editable_log_payload_roundtrips_unsafe_names_and_keeps_evidence(saved_browser, tmp_path):
    import re
    output = tmp_path / 'log.html'
    build_report(saved_browser, output)
    payload = json.loads(re.search(r'<script type="application/json" id="night-log-data">(.*?)</script>', output.read_text()).group(1))
    assert payload['records'][1]['source']['object_id'] == 'SN-<script>'
    assert 'save-night-log' in output.read_text() and 'csv-night-log' in output.read_text()
    assert len(payload['records'][1]['runs']) == 4
