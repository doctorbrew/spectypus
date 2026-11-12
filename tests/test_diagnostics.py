import sys
from spectypus.diagnostics import import_probe


def test_import_diagnostic_reports_actual_failure():
    result = import_probe(sys.executable, ['json', 'spectypus_deliberately_missing_dependency'])
    assert result['status'] == 'unavailable'
    assert result['imports'][0]['status'] == 'ready'
    assert 'No module named' in result['imports'][1]['reason']
    assert result['elapsed_seconds'] > 0
