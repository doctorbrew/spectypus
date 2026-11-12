#!/usr/bin/env python3
"""Validate SN pages, local assets, native candidate identity and curve coverage."""
import argparse
from collections import Counter
import gzip
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spectral_atlas_products import PLOT_OUTPUT, validate_product, validate_jpg
from urllib.parse import unquote, urlsplit


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


class BrowserHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids = set(); self.links = []; self.images = []; self.sn_count = 0
        self.executions = []; self.epochs = 0; self.in_script = False; self.visible = []
        self.section_stack = []; self.rank_tables = []; self.active_table = None; self.active_row = None; self.active_cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'section': self.section_stack.append(a.get('data-execution'))
        execution = next((x for x in reversed(self.section_stack) if x), None)
        if tag == 'table' and execution:
            self.active_table = {'execution': execution, 'rows': []}; self.rank_tables.append(self.active_table)
        if tag == 'tr' and self.active_table is not None:
            self.active_row = []; self.active_table['rows'].append(self.active_row)
        if tag in ('td', 'th') and self.active_row is not None:
            self.active_cell = {'text': '', 'links': []}; self.active_row.append(self.active_cell)
        if tag == 'a' and self.active_cell is not None: self.active_cell['links'].append(a.get('href'))
        if a.get('id'):
            assert a['id'] not in self.ids, 'Repeated HTML ID'
            self.ids.add(a['id'])
        if tag in ('style', 'script'): self.in_script = True
        assert not (tag in ('script', 'link') and (a.get('src') or a.get('href'))), 'External runtime dependency'
        if tag == 'a' and a.get('href'): self.links.append(a['href'])
        if tag == 'a' and 'data-sn' in a: self.sn_count += 1
        if tag == 'section' and 'data-execution' in a: self.executions.append(a['data-execution'])
        if tag == 'details' and 'epoch' in a.get('class', '').split(): self.epochs += 1
        if tag == 'img' and a.get('src'):
            assert a.get('alt'), 'Figure missing alternative text'
            self.images.append(a['src'])

    def handle_endtag(self, tag):
        if tag == 'section': self.section_stack.pop()
        if tag in ('td', 'th'): self.active_cell = None
        if tag == 'tr': self.active_row = None
        if tag == 'table': self.active_table = None
        if tag in ('style', 'script'): self.in_script = False

    def handle_data(self, data):
        if not self.in_script: self.visible.append(data)
        if self.active_cell is not None: self.active_cell['text'] += data


def validate(root):
    root = root.resolve()
    checks = json.loads((root / 'checksums.json').read_text())
    for relative, expected in checks.items():
        path = (root / relative).resolve()
        assert path.is_relative_to(root), 'Unsafe checksum path'
        assert sha(path) == expected, f'Changed browser product: {relative}'
    frozen = json.loads((root / 'browser-snapshot.json').read_text())
    manifest = json.loads((root / 'manifest.json').read_text())
    catalog = {'files': {}, 'locations': {}}
    if manifest.get('rank_table', {}).get('template_locations_sha256'):
        assert sha(root / 'template-locations.json') == manifest['rank_table']['template_locations_sha256']
        catalog = json.loads((root / 'template-locations.json').read_text())
        for name, expected in catalog['files'].items():
            assert Path(name).is_absolute() and sha(Path(name)) == expected, 'Changed/missing optional local template file'
    allowed_template_urls = {Path(name).as_uri() for name in catalog['files']}
    assert manifest.get('plot_output') == PLOT_OUTPUT, 'Expected JPG-only manifest'
    if manifest.get('model_restoration_sha256'):
        assert sha(root / 'model-restoration.json') == manifest['model_restoration_sha256']
        restoration = json.loads((root / 'model-restoration.json').read_text())
        assert restoration['status'] == 'passed' and restoration['scientific_fields_unchanged']
        assert restoration['classifier_runs'] == restoration['preprocessing_replays'] == 0
    assert not any(p.suffix.lower() == '.pdf' for p in root.rglob('*') if '.plot-cache' not in p.parts), 'Unexpected PDF product'
    results = json.loads((root / 'figure-results.json').read_text())
    contract = json.loads((root / 'render-contract.json').read_text())
    assert contract['plot_output'] == PLOT_OUTPUT
    assert sha(root / 'render-contract.json') == manifest['render_contract_sha256']
    for relative, expected in contract['requests'].items():
        assert checks.get(relative) == expected, 'Request hash disagrees with render contract'
    objects = {s['object_id'] for c in frozen['snapshots'] for s in c['spectra']}
    assert len(objects) == manifest['objects']
    runs = [r for c in frozen['snapshots'] for r in c['runs']]
    saved_panels = rendered_panels = candidate_count = input_panels = 0
    figures = set()
    limit_checks = {}
    unmasked = Counter()
    for c in frozen['snapshots']:
        assert Counter(r['status'] for r in c['runs']) == c['counts']
        sources = {s['spectrum_id']: s for s in c['spectra']}
        for run in c['runs']:
            assert len(run['matches']) <= manifest.get('plot_presentation', {}).get('top_k', 5)
            candidate_count += len(run['matches'])
            if not run['matches']: continue
            request = json.loads(gzip.decompress((root / 'data' / (run['plot_key'] + '.json.gz')).read_bytes()))
            assert request['execution_id'] == run['execution_id'] and request['record_sha256'] == run['record_sha256']
            assert [m['candidate'] for m in request['matches']] == run['matches']
            assert request['source']['spectrum_id'] == run['spectrum_id']
            assert request['source'] == sources[run['spectrum_id']]
            assert request['curve_source_sha256'] == run['artifacts'].get('fit_curves.json')
            assert request['engine'] == run['engine'] and request['mode'] == run['mode']
            available = []
            for match in request['matches']:
                candidate, curve = match['candidate'], match['curve']
                if not curve['available']: continue
                assert curve['template'] == candidate['template']
                assert math.isclose(curve['score'], candidate['score'], rel_tol=1e-5, abs_tol=1e-8)
                if run['engine'] == 'ngsf': assert curve['galaxy'] == candidate['native']['GALAXY']
                assert curve['wavelength_frame'] == 'observer' and curve['wavelength_unit'] == 'angstrom'
                assert curve['engine'] == run['engine']
                available.append(candidate['rank'])
            assert available == run['curve_ranks']
            saved_panels += len(available)
            if available:
                figures.add(run['plot_key']); result = results[run['plot_key']]
                assert result['status'] == 'ready', f'Unavailable figure: {run["plot_key"]}'
                if manifest.get('plot_presentation'):
                    assert all(p.get('display_mask_applied') is False for p in result['panels'] if p['status'] == 'rendered')
                    assert result['colours'] == {'observed': '#000000', 'model': '#ef6666'}
                    raw = request['input_spectrum']
                    if raw['available']:
                        assert hashlib.sha256(raw['contents'].encode()).hexdigest() == raw['sha256'] == run['artifacts']['spectrum.txt']
                        assert raw['wavelength_frame'] == 'observer' and raw['wavelength_unit'] == 'angstrom'
                        if manifest['plot_presentation'].get('layout') in {'2x3-matches-only', '3x2-matches-only'}:
                            assert 'input_spectrum' not in result
                            assert result['layout'] == manifest['plot_presentation']['layout']
                            for panel in result['panels']:
                                if panel['status'] != 'rendered': continue
                                assert panel['tick_label_points'] == manifest['plot_presentation']['tick_label_points']
                                assert panel['savgol_width_angstrom'] == manifest['plot_presentation']['savgol_width_angstrom']
                                if manifest['plot_presentation'].get('observed_display'):
                                    assert panel['raw_observed_alpha'] == .2
                                    assert panel['raw_observed_colour'] == '0.5'
                                    assert panel['telluric_samples_included'] is True
                                    assert panel['limit_rule'] == manifest['plot_presentation']['limit_rule']
                                assert len(panel['legend_labels']) == 2
                                if manifest['plot_presentation'].get('observed_source') == 'full-staged-input':
                                    samples = [[float(v) for v in line.split()[:2]] for line in raw['contents'].splitlines() if line.strip() and not line.startswith('#')]
                                    assert panel['observed_source'] == 'full-staged-input'
                                    assert panel['input_sha256'] == raw['sha256']
                                    assert panel['observed_samples'] == len(samples)
                                    assert panel['observed_wavelength_range'] == [samples[0][0], samples[-1][0]]
                                    transform = request['display_transform']
                                    assert transform['input_sha256'] == raw['sha256']
                                    assert panel['model_display_transform'] == transform['kind']
                                    if manifest['plot_presentation'].get('legend_native_type'):
                                        from spectral_atlas_limits import robust_limits
                                        from spectral_atlas_top5_figures import legend_labels, native_type_label
                                        if raw['sha256'] not in limit_checks:
                                            limit_checks[raw['sha256']] = robust_limits(samples)
                                        limits, diagnostics = limit_checks[raw['sha256']]
                                        assert panel['limits'] == limits
                                        assert all(panel[k] == v for k, v in diagnostics.items())
                                        candidate = next(m['candidate'] for m in request['matches'] if m['candidate']['rank'] == panel['rank'])
                                        assert panel['matched_native_type'] == native_type_label(candidate)
                                        assert panel['legend_labels'] == list(legend_labels(request, candidate))
                                        import numpy as np
                                        from spectral_atlas_full_observed import model_input_flux
                                        match = next(m for m in request['matches'] if m['candidate']['rank'] == panel['rank'])
                                        model = model_input_flux(match['curve'], transform)[:, 1]
                                        model = model[np.isfinite(model)]
                                        assert panel['model_samples_outside_limits'] == int(np.sum((model < limits[0]) | (model > limits[1])))
                                        assert panel['model_entirely_outside_limits'] == bool(len(model) and (np.min(model) > limits[1] or np.max(model) < limits[0]))
                                        if manifest['plot_presentation'].get('model_masking') == 'none':
                                            assert request['model_presentation']['masking'] == 'none'
                                            assert panel['model_mask_applied'] is False
                                            assert panel['model_internal_missing_samples'] == 0
                                            unmasked['panels'] += 1
                                            if run['engine'] == 'ngsf':
                                                curve = match['curve']
                                                original = np.asarray(curve['model'], float)
                                                complete = np.asarray(curve['display_model'], float)
                                                good = np.isfinite(original[:, 1])
                                                assert np.array_equal(original[:, 0], complete[:, 0])
                                                assert np.array_equal(original[good, 1], complete[good, 1])
                                                info = curve['display_model_provenance']
                                                assert info['verification_max_relative_error'] <= info['verification_tolerance']
                                                assert info['internal_missing_samples'] == 0
                                                assert info['saved_finite_samples_unchanged'] == int(good.sum())
                                                assert info['restored_samples'] == int(np.sum(~good & np.isfinite(complete[:, 1])))
                                                assert panel['model_restored_samples'] == info['restored_samples']
                                                unmasked['restored_ngsf_samples'] += info['restored_samples']
                                                unmasked['exact_tied_curve_identities'] += info['curve_parameters_recovered']
                                                if info['curve_parameters_recovered']:
                                                    assert info['verification_tolerance'] <= 1e-10
                                            displayed = model_input_flux(match['curve'], transform)
                                            finite_ids = np.flatnonzero(np.isfinite(displayed[:, 1]))
                                            assert len(finite_ids) and np.all(np.isfinite(displayed[finite_ids[0]:finite_ids[-1]+1, 1]))

                        else:
                            info = result['input_spectrum']
                            assert info['status'] == 'rendered' and info['display_mask_applied'] is False
                            assert info['telluric_extrema_included_in_limits'] and info['telluric_samples_outside_limits'] == 0
                            assert info['source_sha256'] == raw['sha256']
                            assert info['samples'] == len([line for line in raw['contents'].splitlines() if line.strip() and not line.startswith('#')])
                            input_panels += 1
                actual = [p['rank'] for p in result['panels'] if p['status'] == 'rendered']
                assert actual == available, 'Saved curve missing from figure'
                rendered_panels += len(actual)
                validate_product(root / 'figures', result)
    assert set(results) == figures
    assert len(figures) == manifest['figures'] and manifest['unavailable_figures'] == 0
    assert saved_panels == rendered_panels == manifest['saved_curves']
    assert candidate_count == manifest['displayed_candidates']
    parsed = {}
    for path in root.rglob('*.html'):
        p = BrowserHTML(); p.feed(path.read_text()); parsed[path.resolve()] = p
        assert p.sn_count == len(objects), f'Missing SN navigation: {path.name}'
        assert 'fieldnotes' not in ' '.join(p.visible).lower(), 'Internal style label leaked into visible text'
    for path, p in parsed.items():
        for href in p.links + p.images:
            url = urlsplit(href)
            if url.scheme == 'file':
                source_paths = {Path(source['path']).resolve() for snapshot in frozen['snapshots']
                                for source in snapshot['spectra'] if source.get('path')}
                source_urls = {path.as_uri() for path in source_paths if path.is_file()}
                assert href in allowed_template_urls | source_urls, 'Unverified external template or source-spectrum link'
                continue
            assert not unquote(url.path).lower().endswith('.pdf'), 'PDF link'
            assert not url.scheme and not url.netloc, f'Nonlocal asset/navigation: {href}'
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            assert target.is_relative_to(root) and target.is_file(), f'Broken local link: {href}'
            if url.fragment: assert target in parsed and url.fragment in parsed[target].ids
    # Object pages contain every source record and fit exactly once; index is a
    # deliberate duplicate of the featured object's page and excluded here.
    object_pages = [p for path, p in parsed.items() if path.parent == root / 'objects']
    rank_rows_checked = 0
    if manifest.get('rank_table'):
        from spectral_atlas_rank_table import compact_identity
        by_execution = {r['execution_id']: r for r in runs}
        for page in object_pages:
            for item in page.rank_tables:
                run = by_execution[item['execution']]
                expected_headers = ['Rank', 'Template', 'Fit z', 'Native score']
                if run['engine'] == 'ngsf': expected_headers += ['Aᵥ (mag)', 'Galaxy type (fraction)']
                assert [c['text'] for c in item['rows'][0]] == expected_headers
                assert len(item['rows']) == len(run['matches']) + 1
                for cells, m in zip(item['rows'][1:], run['matches']):
                    assert cells[0]['text'] == str(m['rank'])
                    assert cells[1]['text'] == compact_identity(m)
                    from spectypus.phases import number
                    for index, field in ((2, 'redshift'), (3, 'score')):
                        v = number(m.get(field)); expected = f'{v:.3f}' if v is not None else '—'
                        if index == 3 and not m['qualified']: expected += 'Unqualified'
                        assert cells[index]['text'] == expected
                    if run['engine'] == 'ngsf':
                        native = m['native']; fraction = number(native.get('Frac(gal)'))
                        assert cells[4]['text'] == (str(native['A_v']) if native.get('A_v') is not None else '—')
                        galaxy = native.get('GALAXY')
                        expected = (f"{galaxy} ({fraction * 100:.0f}%)" if fraction is not None else f"{galaxy} (unknown)") if galaxy else '—'
                        assert cells[5]['text'] == expected
                    location = catalog['locations'].get(run['plot_key'], {}).get(str(m['rank']))
                    if catalog['files']: assert location, 'Missing template location for a displayed rank'
                    if location:
                        assert location['template'] == m['template']
                        assert cells[1]['links'] == [Path(location['path']).as_uri()]
                    rank_rows_checked += 1
        assert rank_rows_checked == candidate_count
    assert len(object_pages) == len(objects)
    assert sum(p.epochs for p in object_pages) == manifest['spectra']
    assert Counter(e for p in object_pages for e in p.executions) == Counter(r['execution_id'] for r in runs)
    return {'objects': len(objects), 'html_pages': len(parsed), 'spectrum_records': manifest['spectra'], 'fit_rows': len(runs),
            'displayed_candidates': candidate_count, 'saved_and_rendered_curves': rendered_panels, 'figures': len(figures),
            'full_input_panels': input_panels, 'unmasked_models': dict(unmasked), 'rank_rows_checked': rank_rows_checked, 'local_template_files_checked': len(catalog['files']), 'checked_files': len(checks), 'robust_limit_inputs_checked': len(limit_checks), 'jpg_only_300_dpi': 'passed', 'hashes': 'passed', 'native_identity_and_rank': 'passed',
            'all_spectra_and_fits_visible': 'passed', 'local_assets_and_links': 'passed', 'naming_rule': 'passed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path); parser.add_argument('--report', type=Path)
    args = parser.parse_args(); result = validate(args.directory)
    text = json.dumps(result, indent=2) + '\n'
    if args.report: args.report.write_text(text)
    print(text)
