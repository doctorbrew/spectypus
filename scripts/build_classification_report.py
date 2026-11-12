#!/usr/bin/env python3
"""Make a continuous, self-contained report from selected saved browser evidence.

No fitting, plotting or preprocessing. Only selected, verified JPGs and requests
are embedded. The source browser and its scientific snapshot remain unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from build_spectral_atlas import (
    ASSETS, ROOT, badge, count_text, data_uri, download_bytes, h, key, page, table,
)
from build_spectral_browser import fit_card
from spectral_atlas_presentation import AUTO_POLICY, SUMMARY_HEADERS, editable_log, load_summaries, summary_key, summary_row, spectrum_heading
from spectral_atlas_products import PLOT_OUTPUT, validate_product
from spectypus.io import canonical, digest, file_hash
from spectypus.phases import number


def build_report(source, output, *, spectrum_ids=(), campaigns=(), title=None, summary_path=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a new report path; existing reports are preserved')
    if output.is_relative_to(source):
        raise ValueError('Keep the new report outside the frozen source browser')
    checks = json.loads((source / 'checksums.json').read_text())
    used = {}

    def verified(name):
        path = (source / name).resolve()
        if not path.is_relative_to(source) or name not in checks:
            raise ValueError(f'Unverified or unsafe report asset: {name}')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != checks[name]:
            raise ValueError(f'Changed saved report asset: {name}')
        used[name] = checks[name]
        return data

    frozen = json.loads(verified('browser-snapshot.json'))
    manifest = json.loads(verified('manifest.json'))
    results = json.loads(verified('figure-results.json'))
    contract = json.loads(verified('render-contract.json'))
    if manifest.get('plot_output') != PLOT_OUTPUT or contract.get('plot_output') != PLOT_OUTPUT:
        raise ValueError('Classification Report requires 300-dpi JPG-only source products')
    if manifest.get('render_contract_sha256') != used['render-contract.json']:
        raise ValueError('Render contract disagrees with saved manifest')
    catalog = {'locations': {}, 'files': {}}
    if manifest.get('rank_table', {}).get('template_locations_sha256'):
        catalog = json.loads(verified('template-locations.json'))
        if used['template-locations.json'] != manifest['rank_table']['template_locations_sha256']:
            raise ValueError('Template catalog disagrees with saved manifest')
    notes = defaultdict(list)
    restoration = {}
    if manifest.get('model_restoration_sha256'):
        restoration = json.loads(verified('model-restoration.json'))
        if used['model-restoration.json'] != manifest['model_restoration_sha256']:
            raise ValueError('Model restoration disagrees with saved manifest')
        for note in restoration.get('curve_parameter_recoveries', []):
            notes[note['plot_key']].append(note)

    summaries = load_summaries(summary_path, frozen)
    selected = []
    for snapshot in frozen['snapshots']:
        if campaigns and snapshot['browser_campaign'] not in campaigns:
            continue
        by_sid = defaultdict(list)
        for run in snapshot['runs']:
            by_sid[run['spectrum_id']].append(run)
        for spectrum in snapshot['spectra']:
            if not spectrum_ids or spectrum['spectrum_id'] in spectrum_ids:
                selected.append((snapshot, spectrum, by_sid[spectrum['spectrum_id']]))
    if not selected or set(spectrum_ids) - {s['spectrum_id'] for _, s, _ in selected}:
        raise ValueError('No saved spectra, or requested spectrum IDs missing from the selected campaigns')
    if set(campaigns) - {s['browser_campaign'] for s, _, _ in selected}:
        raise ValueError('Requested campaign has no selected saved spectra')

    def order(row):
        snapshot, spectrum, _ = row
        name = spectrum['object_id']
        return (0 if name.startswith('AT') else 1 if name.startswith('SN') else 2,
                name, snapshot['browser_campaign'],
                number(spectrum.get('mjd')) if number(spectrum.get('mjd')) is not None else float('inf'),
                spectrum['spectrum_id'])

    selected.sort(key=order)
    assets, template_files, records = {}, {}, []
    inventory, articles, issues = [], [], []
    states = Counter(r['status'] for _, _, runs in selected for r in runs)
    figure_count = 0
    for snapshot, spectrum, runs in selected:
        sid = spectrum['spectrum_id']
        ident = f'c{snapshot["browser_campaign"]}-' + key(sid)
        refs = snapshot['phase_references'].get(spectrum['object_id'], [])
        review = summaries.get(summary_key(snapshot, spectrum))
        inventory.append(summary_row(spectrum, runs, '#' + ident, review,
                                     context=f'{snapshot["label"]}; {sid}'))
        heading, filename = spectrum_heading(spectrum, refs)
        article = f'<article class="report-spectrum" id="{ident}"><h3>{heading}</h3><p class="report-meta">{filename}</p>'
        if spectrum.get('frame_assumed') in (True, 'true'):
            article += '<p class="bad">Frame provisional</p>'
        cards = []
        for run in sorted(runs, key=lambda r: (r['mode'] != 'fixed', r['engine'] != 'snid_sage')):
            plot_key = run['plot_key']
            result = results.get(plot_key, {})
            locations = catalog['locations'].get(plot_key, {})
            if run['matches']:
                request_name = 'data/' + plot_key + '.json.gz'
                raw = verified(request_name)
                request = json.loads(gzip.decompress(raw))
                if (request['source'] != spectrum or request['execution_id'] != run['execution_id']
                        or request['record_sha256'] != run['record_sha256']
                        or request['engine'] != run['engine'] or request['mode'] != run['mode']
                        or [m['candidate'] for m in request['matches']] != run['matches']):
                    raise ValueError('Saved numerical evidence disagrees with selected fit')
                assets[request_name] = data_uri(raw, 'application/gzip')
                if result.get('status') == 'ready':
                    if (contract['requests'].get(request_name) != used[request_name]
                            or restoration.get('status') != 'passed'
                            or not restoration.get('scientific_fields_unchanged')
                            or manifest.get('plot_presentation', {}).get('model_masking') != 'none'):
                        raise ValueError('Ready figures require verified unmasked master-grid evidence')
                    if result.get('layout') != '2x3-matches-only':
                        raise ValueError('Expected a six-panel master grid')
                    validate_product(source / 'figures', result)
                    name = 'figures/' + result['jpg']
                    assets[name] = data_uri(verified(name), 'image/jpeg')
                    figure_count += 1
                for candidate in run['matches']:
                    location = locations.get(str(candidate['rank']))
                    if not location:
                        continue
                    path = Path(location['path'])
                    expected = catalog['files'].get(str(path))
                    if location['template'] != candidate['template'] or not path.is_absolute() or not expected:
                        raise ValueError('Template location disagrees with saved candidate')
                    if str(path) not in template_files:
                        if file_hash(path) != expected:
                            raise ValueError('Changed local template file')
                        template_files[str(path)] = expected
            cards.append(fit_card(run, results, '', notes[plot_key], locations,
                                  asset_url=assets.__getitem__))
            if run['status'] != 'completed' or (run['matches'] and result.get('status') != 'ready'):
                reason = run.get('reason') or ('Saved model figure unavailable' if run['matches'] and result.get('status') != 'ready' else 'No further reason recorded')
                issues.append([f'<a href="#{ident}">{h(sid)}</a>', h(snapshot['label']),
                               h(run['engine']), h(run['mode']), badge(run['status']), h(reason)])
        article += '<div class="report-fits">' + (''.join(cards) or '<p class="empty">No planned fits in this saved snapshot.</p>') + '</div>'
        articles.append(article + '<p class="report-back"><a href="#inventory">Back to spectrum inventory ↑</a></p></article>')
        records.append({'campaign': snapshot['browser_campaign'], 'label': snapshot['label'],
                        'plan_id': snapshot['plan_id'], 'checked_at': snapshot['checked_at'],
                        'source': spectrum, 'runs': runs, 'phase_references': refs})

    evidence = {'schema': 'spectypus-classification-report/1', 'display': 'Classification Report',
                'created_at': datetime.now(timezone.utc).isoformat(), 'source_browser': str(source),
                'automatic_summary_policy': AUTO_POLICY, 'reviewed_summaries': summaries, 'summary_source_sha256': file_hash(summary_path) if summary_path else None,
                'plot_output': PLOT_OUTPUT, 'spectra': len(selected), 'fits': sum(states.values()),
                'figures': figure_count, 'states': dict(states), 'records': records,
                'source_products_sha256': used, 'template_files_sha256': template_files,
                'curve_parameter_recoveries': [note for record in records for run in record['runs'] for note in notes[run['plot_key']]],
                'presentation_sha256': {n: file_hash(ASSETS / n) for n in ('atlas.css', 'atlas.js', 'report.css', 'night-log.js')},
                'builder_sha256': file_hash(Path(__file__)),
                'shared_reporting_sha256': {p.name: file_hash(p) for p in ASSETS.parent.glob('*.py')},
                'shared_components_sha256': {n: file_hash(ROOT / 'scripts' / n) for n in ('build_spectral_atlas.py', 'build_spectral_browser.py', 'spectral_atlas_rank_table.py', 'spectral_atlas_presentation.py')}}
    body = f'<p class="report-summary">{len(selected)} spectrum records · {figure_count} master grids · {h(count_text(states))}</p>'
    body += '<nav class="report-nav" aria-label="Report sections"><a href="#inventory">Spectrum inventory</a><a href="#spectra">Spectra &amp; matches</a><a href="#issues">Issues</a><a href="#night-log">Final night log</a></nav>'
    body += '<section id="inventory"><h2>Classifications</h2>' + table(SUMMARY_HEADERS, inventory)
    body += '<div class="downloads">' + download_bytes(canonical(evidence).encode(), 'classification-report-evidence.json', 'Data') + '</div></section>'
    body += '<section id="spectra"><h2>Spectra &amp; matches</h2>' + ''.join(articles) + '</section>'
    body += '<section id="issues"><h2>Issues</h2>' + (table(['Spectrum', 'Campaign', 'Engine', 'z mode', 'State', 'Reason'], issues) if issues else '<p>No unresolved fit or figure states in this selection.</p>') + '</section>'
    log_identity = digest([{'campaign': r['campaign'], 'source': r['source'], 'runs': [(x['execution_id'], x.get('record_sha256')) for x in r['runs']]} for r in records])
    body += editable_log(records, log_identity)
    stamp = max(s['checked_at'] for s, _, _ in selected)
    html = page(title or output.parent.name, body, stamp, display='Classification Report', extra_css=(ASSETS / 'report.css').read_text())
    html = html.replace('</body>', '<script>' + (ASSETS / 'night-log.js').read_text() + '</script></body>')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(html)
    return {'output': str(output), 'sha256': file_hash(output), 'spectra': len(selected),
            'fits': evidence['fits'], 'figures': figure_count, 'evidence_sha256': digest(evidence)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-browser', type=Path, required=True, help='Verified frozen browser directory')
    parser.add_argument('--output', type=Path, required=True, help='New standalone HTML file')
    parser.add_argument('--spectrum', action='append', default=[], help='Exact spectrum ID; repeat to select several (default: all)')
    parser.add_argument('--campaign', type=int, action='append', default=[], help='Saved browser campaign number; repeat as needed')
    parser.add_argument('--title', help='Folder label or date (default: output folder name)')
    parser.add_argument('--summary', type=Path, help='Separate reviewer summary JSON; never edits saved fits')
    args = parser.parse_args()
    print(json.dumps(build_report(args.from_browser, args.output, spectrum_ids=args.spectrum,
                                 campaigns=args.campaign, title=args.title, summary_path=args.summary), indent=2))


if __name__ == '__main__':
    main()
