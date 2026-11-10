#!/usr/bin/env python3
"""Check a portable atlas's byte hashes, navigation and embedded downloads."""
import argparse
import base64
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spectral_atlas_products import PLOT_OUTPUT, validate_product, validate_jpg
from urllib.parse import unquote, urlsplit


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


class Report(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links = set(), []
        self.images = self.downloads = self.bytes = 0
        self.duplicate_ids = []

    def handle_starttag(self, tag, attributes):
        a = dict(attributes)
        if 'id' in a:
            if a['id'] in self.ids:
                self.duplicate_ids.append(a['id'])
            self.ids.add(a['id'])
        if tag == 'img' and a.get('src'):
            assert a['src'].startswith('data:image/'), 'External image dependency'
            data = base64.b64decode(a['src'].split(',', 1)[1], validate=True)
            assert data[:2] == b'\xff\xd8' or data[:8] == b'\x89PNG\r\n\x1a\n', 'Invalid image'
            from io import BytesIO
            validate_jpg(BytesIO(data))
            assert a.get('alt'), 'Image missing alternative text'
            self.images += 1
        if tag in {'link', 'script'}:
            assert not a.get('src') and not a.get('href'), 'External runtime dependency'
        if tag == 'a' and a.get('href'):
            href = a['href']
            assert not a.get('download', '').lower().endswith('.pdf') and not href.lower().startswith('data:application/pdf'), 'PDF download'
            assert not unquote(urlsplit(href).path).lower().endswith('.pdf'), 'PDF link'
            if href.startswith('data:'):
                data = base64.b64decode(href.split(',', 1)[1], validate=True)
                assert hashlib.sha256(data).hexdigest() == a.get('data-sha256'), 'Download hash mismatch'
                assert a.get('download'), 'Embedded product missing filename'
                self.downloads += 1; self.bytes += len(data)
            else:
                self.links.append(href)


def validate(root):
    checksums = json.loads((root / 'checksums.json').read_text())
    for relative, expected in checksums.items():
        path = (root / relative).resolve()
        assert path.is_relative_to(root.resolve()), 'Unsafe product path'
        assert sha(path) == expected, f'Changed export product: {relative}'
    manifest = json.loads((root / 'manifest.json').read_text())
    assert manifest.get('plot_output') == PLOT_OUTPUT, 'Expected JPG-only manifest'
    assert not any(p.suffix.lower() == '.pdf' for p in root.rglob('*') if '.plot-cache' not in p.parts), 'Unexpected PDF product'
    results = json.loads((root / 'figure-results.json').read_text())
    expected_jobs = 0
    unavailable_panels = 0
    for path in sorted(root.glob('campaign-*/snapshot.json')):
        snapshot = json.loads(path.read_text())
        assert Counter(r['status'] for r in snapshot['runs']) == snapshot['counts']
        assert len({r['execution_id'] for r in snapshot['runs']}) == len(snapshot['runs'])
        plotted = set()
        for request, stem in snapshot['jobs']:
            # Export directories may be copied; serialized absolute paths remain
            # provenance, while products are resolved inside this local copy.
            request_path = path.parent / 'data' / Path(request).name
            payload = json.loads(request_path.read_text())
            for curve in payload['curves']:
                assert curve['execution_id'] not in plotted
                plotted.add(curve['execution_id'])
            result = results[stem]
            if result['status'] == 'ready':
                validate_product(path.parent / 'figures', result)
                unavailable_panels += sum(p['status'] != 'rendered' for p in result['panels'])
        assert plotted == {r['execution_id'] for r in snapshot['runs'] if r['curve_available']}
        expected_jobs += len(snapshot['jobs'])
    assert expected_jobs == manifest['rendering']['requested']
    assert len(results) == expected_jobs
    parsed = {}
    for i, path in enumerate(sorted(root.rglob('*.html')), 1):
        report = Report(); report.feed(path.read_text())
        assert not report.duplicate_ids, f'Duplicate anchors: {path}'
        parsed[path.resolve()] = report
        if i % 100 == 0:
            print(f'Checked {i} HTML reports', flush=True)
    for path, report in parsed.items():
        for href in report.links:
            url = urlsplit(href)
            assert not url.scheme and not url.netloc, f'External navigation dependency: {href}'
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            assert target.is_file(), f'Missing local link: {path.name}: {href}'
            if url.fragment:
                assert target in parsed and unquote(url.fragment) in parsed[target].ids, f'Missing anchor: {href}'
    return {'checked_files': len(checksums), 'html_pages': len(parsed), 'embedded_images': sum(p.images for p in parsed.values()),
            'embedded_downloads': sum(p.downloads for p in parsed.values()), 'download_bytes_verified': sum(p.bytes for p in parsed.values()),
            'spectrum_figures': expected_jobs, 'unavailable_panels': unavailable_panels,
            'jpg_only_300_dpi': 'passed', 'hashes': 'passed', 'counts_and_curve_coverage': 'passed', 'local_links_and_anchors': 'passed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = validate(args.directory)
    serialized = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.write_text(serialized)
    print(serialized)
