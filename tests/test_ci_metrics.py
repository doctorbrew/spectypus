import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

spec = importlib.util.spec_from_file_location('ci_metrics', Path(__file__).parents[1]/'scripts/ci_metrics.py')
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


@pytest.mark.parametrize('body,exit_code,expected', [
    ('<testcase/><testcase><skipped/></testcase>', 0, '1 passed, 1 skipped'),
    ('<testcase><failure/></testcase>', 1, '0 passed, 1 failed, run failed'),
    ('<testcase><error/></testcase>', 2, '0 passed, 1 errors, run failed'),
    ('<testcase><skipped/></testcase>', 0, '0 passed, 1 skipped'),
    ('', 0, 'report unavailable'),
])
def test_counts_and_coverage_require_completed_tests(tmp_path, body, exit_code, expected):
    junit, cov = tmp_path/'junit.xml', tmp_path/'coverage.xml'
    junit.write_text('<testsuites><testsuite>'+body+'</testsuite></testsuites>')
    cov.write_text('<coverage line-rate="0.75"/>')
    result = metrics.prepare(junit, cov, exit_code)
    assert result['tests.json']['message'] == expected
    assert result['coverage.json']['message'] == ('75.0%' if expected.startswith('1 passed') else 'unavailable')


def test_missing_reports_and_failed_exit_cannot_claim_success(tmp_path):
    result = metrics.prepare(tmp_path/'missing', tmp_path/'missing', 1)
    assert result['tests.json']['color']=='red'
    assert result['coverage.json']['message']=='unavailable'


def test_nested_suite_counts_and_inconsistent_summary(tmp_path):
    p=tmp_path/'junit.xml'
    p.write_text('<testsuites tests="1"><testsuite tests="1"><testsuite tests="1"><testcase/></testsuite></testsuite></testsuites>')
    assert metrics.read_counts(p)==(1,0,0,0)
    p.write_text('<testsuite tests="2"><testcase/></testsuite>')
    with pytest.raises(ValueError, match='disagree'):
        metrics.read_counts(p)


def test_svg_escapes_text_and_keeps_verifiable_source():
    svg=metrics.render('tests', '1 < 2 & 3', 'red', 'abc123 https://example.test/run/42')
    root=ET.fromstring(svg)
    assert 'abc123' in root.attrib['aria-label']
    assert '1 &lt; 2 &amp; 3' in svg


def test_compact_success_badge_retains_details_and_does_not_hide_failures():
    root = ET.fromstring(metrics.render('tests', '234 passed, 4 skipped', 'brightgreen', 'verified-run'))
    visible = [node.text for node in root.iter() if metrics.tag(node) == 'text']
    assert '234 passed' in visible and all('skipped' not in text for text in visible)
    assert '234 passed, 4 skipped' in root.attrib['aria-label']
    assert 'verified-run' in root.attrib['aria-label']
    assert int(root.attrib['width']) == 110
    failed = ET.fromstring(metrics.render('tests', '234 passed, 1 failed, run failed', 'red', 'failed-run'))
    assert any('1 failed, run failed' in (node.text or '') for node in failed.iter() if metrics.tag(node) == 'text')
