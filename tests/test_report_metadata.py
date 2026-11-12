import io
import json
from pathlib import Path
import urllib.error

import pytest

from spectypus.io import read_json
from spectypus.reporting.metadata import cached_tns, discovery_fields, fetch_tns, mjd_from_utc
from spectypus.reporting.presentation import spectrum_heading


def response(name='2024afzf'):
    return {'id_code': 200, 'data': {'objname': name, 'discoverydate': '2024-12-30 05:46:33.024',
                                   'redshift': .2, 'hostname': None, 'host_redshift': None,
                                   'discovery_data_source': {'group_name': 'ATLAS'}}}


def test_tns_fetch_identity_precision_cache_and_no_credentials_in_results(tmp_path, monkeypatch):
    for k, v in [('TNS_API_KEY', 'secret-test-key'), ('TNS_BOT_ID', '1'), ('TNS_BOT_NAME', 'test')]:
        monkeypatch.setenv(k, v)
    calls = []
    def opener(request, timeout):
        calls.append(request.full_url)
        assert request.full_url == 'https://www.wis-tns.org/api/get/object' and timeout == 30
        assert b'secret-test-key' in request.data
        return io.StringIO(json.dumps(response()))
    sources = [{'object_id': 'AT2024afzf'}, {'object_id': 'opaque-file'}]
    assert fetch_tns(tmp_path, sources, opener=opener)['fetched'] == 1
    assert fetch_tns(tmp_path, sources, opener=opener)['cached'] == 1
    assert len(calls) == 1
    fields = cached_tns(tmp_path)['2024afzf']
    assert fields['discovery_mjd'] == pytest.approx(60674.24066)
    assert fields['discovery_survey'] == 'ATLAS'
    assert 'host_redshift' not in fields and 'redshift' not in fields
    assert all('secret-test-key' not in p.read_text() for p in tmp_path.rglob('*.json'))
    receipt = read_json(tmp_path / 'metadata/tns.json')['objects']['2024afzf']
    (tmp_path / 'metadata' / receipt['file']).write_text('{}')
    with pytest.raises(ValueError, match='integrity'):
        cached_tns(tmp_path)


def test_tns_mismatch_and_rate_limit_are_not_fake_discoveries(tmp_path, monkeypatch):
    for k, v in [('TNS_API_KEY', 'secret-test-key'), ('TNS_BOT_ID', '1'), ('TNS_BOT_NAME', 'test')]:
        monkeypatch.setenv(k, v)
    with pytest.raises(ValueError, match='identity'):
        discovery_fields(response('2026abc'), '2024afzf')
    calls = []
    def denied(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 429, 'limited', {}, None)
    result = fetch_tns(tmp_path, [{'object_id': 'AT2024afzf'}, {'object_id': 'SN2026abc'}], opener=denied)
    assert result['fetched'] == 0 and result['errors'][0]['http_status'] == 429 and len(calls) == 1
    assert cached_tns(tmp_path) == {}


def test_heading_uses_observer_discovery_phase_and_verified_file_link(tmp_path):
    path = tmp_path / 'spectrum <one>.asci'
    path.write_text('3000 1\n5000 2\n9000 3\n')
    source = {'object_id': 'AT2024afzf', 'spectrum_id': path.name, 'path': str(path),
              'mjd': 61342.30017625, 'discovery_mjd': 60674.24066, 'phase_rest_days': -5,
              'redshift': .2, 'host_name': 'UGC 123', 'host_redshift': .03456, 'host_source': 'reviewed catalogue'}
    title, meta = spectrum_heading(source)
    assert title == 'AT2024afzf'
    assert '>60674.241</span>' in meta and '>61342.300</span>' in meta
    assert 'Phase +668.1 d since discovery' in meta
    assert 'UGC 123 (z=0.035)' in meta
    assert path.as_uri() in meta and 'spectrum &lt;one&gt;.asci' in meta
    assert 'Supplied z' not in title and '-5' not in meta


def test_discovery_utc_conversion_and_missing_fields():
    assert mjd_from_utc('2000-01-01T00:00:00Z') == 51544
    assert mjd_from_utc('2000-01-01T01:00:00+01:00') == 51544
    _, meta = spectrum_heading({'object_id': 'SN-x', 'spectrum_id': 'x', 'redshift': .1})
    assert 'Discovery MJD: —' in meta and 'Observed MJD: —' in meta
    assert 'Phase ' not in meta and '(z=' not in meta
