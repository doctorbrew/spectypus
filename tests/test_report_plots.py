"""Cache contracts ensure report refreshes do not re-run numerical preparation."""
import gzip
from pathlib import Path
from types import SimpleNamespace

import pytest

from spectypus.io import canonical, file_hash, read_json, write_json
from spectypus.reporting import plots


def test_discovery_legend_and_sourced_flux_units(tmp_path):
    from spectypus.reporting.grids import flux_label, legend_labels
    from spectypus.reporting.metadata import display_sources
    from spectypus.efosc import UNIT_SOURCE
    source = {'object_id': 'AT2026agwm', 'discovery_mjd': 61340.00076,
              'mjd': 61342.08307765046, 'unit_source': UNIT_SOURCE}
    row = display_sources(tmp_path, [source])[0]
    assert row['flux_unit'] == 'erg s^-1 cm^-2 Angstrom^-1'
    assert 'flux_unit' not in source
    assert r'\AA$^{-1}$' in flux_label(row)
    assert flux_label({}) == 'Flux (input units)'
    assert flux_label({'flux_unit': 'mJy'}) == 'Flux (mJy)'
    assert legend_labels({'source': row}, {'template': 'SN2007bm', 'native_class': 'Ia',
                         'native_subtype': 'Ia-norm', 'phase_days': -9.3}) == (
        'AT2026agwm(+2.1d since discovery)', 'SN2007bm — Ia / Ia-norm (-9.3 d)')


def test_master_cache_and_metadata_refresh_reuse_numerical_request(tmp_path, monkeypatch):
    Image = pytest.importorskip('PIL.Image')
    attempt = tmp_path / 'attempt'
    attempt.mkdir()
    write_json(attempt / 'fit_curves.json', {'curves': [{'available': True}]})
    calls = []
    def worker(command, **kwargs):
        action, job_path = command[-2:]
        job = read_json(Path(job_path)); calls.append(action)
        if action == 'prepare':
            request = {'record_sha256': job['record_sha256'], 'source': job['source'], 'native_samples': [1, 2, 3]}
            Path(job['request']).write_bytes(gzip.compress(canonical(request).encode(), mtime=0))
        else:
            path = Path(job['stem'] + '.jpg')
            Image.new('RGB', (20, 20)).save(path, dpi=(300, 300))
            write_json(Path(job['result']), {'status': 'ready', 'jpg': path.name, 'identity': job['identity'],
                'product_hashes': {'jpg': file_hash(path)}, 'request_sha256': file_hash(Path(job['request']))})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(plots.subprocess, 'run', worker)
    source = {'object_id': 'test', 'discovery_mjd': 60000}
    run = {'execution_id': 'fit', 'record_sha256': 'verified', 'engine': 'ngsf', 'mode': 'free', 'matches': [{}]}
    record = {'artifacts': {'fit_curves.json': file_hash(attempt / 'fit_curves.json')},
              'config': {'engines': {'ngsf': {'python': 'test-only'}}}}
    first = plots.ensure_grid(tmp_path, source, run, record, attempt)
    assert first['status'] == 'ready' and calls == ['prepare', 'render']
    assert plots.ensure_grid(tmp_path, source, run, record, attempt) == first
    assert calls == ['prepare', 'render']
    second = plots.ensure_grid(tmp_path, {**source, 'discovery_mjd': 60001}, run, record, attempt)
    assert second['status'] == 'ready' and calls == ['prepare', 'render', 'render']
    import json
    request = json.loads(gzip.decompress((Path(second['directory']) / 'request.json.gz').read_bytes()))
    assert request['source']['discovery_mjd'] == 60001 and request['native_samples'] == [1, 2, 3]
    (Path(second['directory']) / 'master.jpg').write_bytes(b'tampered')
    assert plots.ensure_grid(tmp_path, {**source, 'discovery_mjd': 60001}, run, record, attempt)['status'] == 'ready'
    assert calls == ['prepare', 'render', 'render', 'render']
    assert not list(tmp_path.rglob('*.pdf'))


def test_cached_jpg_validation_without_plotting_dependencies(tmp_path, monkeypatch):
    Image = pytest.importorskip('PIL.Image')
    from spectypus.reporting.products import validate_jpg
    import sys
    good, wrong = tmp_path / 'good.jpg', tmp_path / 'wrong.jpg'
    Image.new('RGB', (20, 20)).save(good, dpi=(300, 300))
    Image.new('RGB', (20, 20)).save(wrong, dpi=(72, 72))
    monkeypatch.setitem(sys.modules, 'PIL', None)
    validate_jpg(good)
    with pytest.raises(ValueError, match='300-dpi'):
        validate_jpg(wrong)
    good.write_bytes(good.read_bytes()[:-2])
    with pytest.raises(ValueError, match='complete JPEG'):
        validate_jpg(good)
