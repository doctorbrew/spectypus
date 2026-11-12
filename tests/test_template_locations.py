import gzip
import json
from pathlib import Path

import pytest

from spectypus.io import file_hash, tree_hash, write_json
from spectypus.reporting.locations import TemplateLocations


def test_ngsf_link_requires_exact_candidate_and_file(tmp_path):
    bank = tmp_path / 'bank'
    bank.mkdir()
    template = bank / 'native.dat'
    template.write_text('native template')
    candidate = {'rank': 1, 'template': 'Ia/example/0'}
    request = {'matches': [{'candidate': candidate, 'curve': {'display_model_provenance': {
        'sn_template': str(template), 'sn_template_sha256': file_hash(template)}}}]}
    path = tmp_path / 'request.json.gz'
    path.write_bytes(gzip.compress(json.dumps(request).encode()))
    figure = {'status': 'ready', 'directory': str(tmp_path), 'request_sha256': file_hash(path)}
    record = {'config': {'engines': {'ngsf': {'root': str(tmp_path)}}}}
    run = {'engine': 'ngsf', 'matches': [candidate]}
    links, reason = TemplateLocations().resolve(run, record, figure)
    assert reason is None and links['1']['path'] == str(template)
    template.write_text('changed')
    assert TemplateLocations().resolve(run, record, figure)[0] == {}
    template.unlink()
    assert TemplateLocations().resolve(run, record, figure)[0] == {}


def test_sage_native_epoch_order_and_phase(tmp_path):
    h5py = pytest.importorskip('h5py')
    source = tmp_path / 'source'
    source.mkdir()
    (source / '__init__.py').write_text('')
    bank = tmp_path / 'bank'
    bank.mkdir()
    path = bank / 'templates.h5'
    with h5py.File(path, 'w') as container:
        for key, age in [('epoch_10', 4), ('epoch_2', 9)]:
            container.create_group('/templates/SNtest/epochs/' + key).attrs['age'] = age
    write_json(bank / 'template_index.json', {'templates': {'SNtest': {'storage_file': path.name}}})
    record = {'provenance': {'runtime': {'sage_source': str(source / '__init__.py')},
              'source_sha256': tree_hash(source, suffixes={'.py', '.json', '.yaml', '.yml'}),
              'templates': str(bank), 'bank_sha256': tree_hash(bank)}}
    candidate = {'rank': 1, 'template': 'SNtest_epoch_1', 'phase_days': 9}
    run = {'engine': 'snid_sage', 'matches': [candidate]}
    links, reason = TemplateLocations().resolve(run, record, {})
    assert reason is None
    assert links['1']['group'] == '/templates/SNtest/epochs/epoch_2'
    candidate['phase_days'] = 4
    assert TemplateLocations().resolve(run, record, {})[0] == {}
