"""Automatic match logs; consumes verified records, never runs a classifier."""
from collections import Counter, defaultdict
from pathlib import Path

from ..io import atomic_text, canonical, digest, file_hash, read_json
from .html import ASSETS, BAD, badge, data_uri, download_bytes, h, page, table
from .presentation import (
    AUTO_POLICY, SUMMARY_HEADERS, editable_log, summary_row,
    spectrum_heading, write_classification_tables,
)
from .rank_table import candidate_rows
from .metadata import display_sources
from .plots import ensure_grid
from .offline_plots import ensure_map
from .locations import TemplateLocations
from .navigation import atlas_body


def _write_report(plan, records, states, output, *, display="report"):
    """Called under the pipeline's output lock, after current-record verification.

    Only the current plan and its verified attempts enter the report. Native rows
    and precise values are embedded; mutable reviewer notes live in separate files.
    No source spectra, template banks, or plotting runtimes need to be available.
    """
    output = Path(output)
    locator = TemplateLocations()
    by_spectrum = defaultdict(list)
    attempts = {}
    for state in states:
        run = dict(state)
        record = records.get(run['execution_id'])
        run['record_sha256'] = None
        run['matches'] = []
        if run['blocked_reason'].startswith('duplicate_of:'):
            run['status'] = 'duplicate'
        if record:
            # Resolve through the verified current pointer, not a historical
            # absolute attempt_path which may predate relocation of the results.
            parent = output / 'attempts' / run['execution_id']
            directory = parent / read_json(parent / 'current.json')['trial']
            attempts[run['execution_id']] = directory
            run['record_sha256'] = file_hash(directory / 'record.json')
            run['matches'] = record['candidates'][:plan['config']['top_n']]
            # Do not lose a qualified automatic choice beyond the display limit.
            qualified = next((m for m in record['candidates'] if m.get('qualified')), None)
            if qualified and qualified not in run['matches']:
                run['matches'] = [*run['matches'], qualified]
            run['artifacts_sha256'] = record['artifacts']
            run['provenance'] = record['provenance']
        by_spectrum[run['spectrum_id']].append(run)

    def order(source):
        name = source['object_id']
        return (0 if name.startswith('AT') else 1 if name.startswith('SN') else 2,
                name, source['spectrum_id'])

    sources = sorted(display_sources(output, plan['spectra']), key=order)
    batches = {s.get('batch') for s in sources} - {None, ''}
    title = str(next(iter(batches))) if len(batches) == 1 else output.name
    inventory, articles, issues, report_records = [], [], [], []
    runs = []
    for source in sources:
        sid = source['spectrum_id']
        selected = sorted(by_spectrum[sid], key=lambda r: (r['mode'] != 'fixed', r['engine'] != 'snid_sage'))
        ident = 's-' + digest(sid)[:16]
        inventory.append(summary_row(source, selected, '#' + ident, context=sid))
        heading, filename = spectrum_heading(source)
        article = f'<article class="report-spectrum" id="{ident}"><h3>{heading}</h3><p class="report-meta">{filename}</p>'
        if source.get('frame_assumed') in (True, 'true'):
            article += '<p class="bad">Frame provisional</p>'
        cards = []
        for run in selected:
            engine = {'ngsf': 'NGSF', 'snid_sage': 'SNID-SAGE'}.get(run['engine'], run['engine'])
            card = (f'<section class="fit-card" data-execution="{h(run["execution_id"])}" '
                    f'data-engine="{h(run["engine"])}" data-mode="{h(run["mode"])}">'
                    f'<h4>{h(engine)} · {h(run["mode"])}-z {badge(run["status"])}</h4>')
            if run['reason']:
                card += f'<p class="{"bad" if run["status"] in BAD else "muted"}">{h(run["reason"])}</p>'
            matches = run['matches']
            if matches:
                figure = ensure_grid(output, source, run, records.get(run['execution_id']), attempts[run['execution_id']])
                run['figure'] = figure
                if figure['status'] == 'ready':
                    figure['browser_export'] = ensure_map(output, figure)
                    folder = Path(figure['directory'])
                    jpg = (folder / figure['jpg']).read_bytes()
                    figure_title = f'{source["object_id"]} / {engine} / {run["mode"]}-z: six ranked matches'
                    card += (f'<figure><button type="button" class="enlarge" aria-label="Enlarge {h(figure_title)}">'
                             f'<img id="master-{h(run["execution_id"])}" src="{data_uri(jpg, "image/jpeg")}" alt="{h(figure_title)}" loading="lazy"></button></figure>')
                    card += '<div class="downloads">' + download_bytes(jpg, source['object_id'] + '-' + run['engine'] + '-' + run['mode'] + '.jpg', 'JPG · 300 dpi', 'image/jpeg')
                    card += download_bytes((folder / 'request.json.gz').read_bytes(), run['execution_id'] + '.json.gz', 'Plot data', 'application/gzip') + '</div>'
                else:
                    card += f'<p class="muted">Plot unavailable: {h(figure["reason"])}</p>'
                metric = matches[0]
                card += f'<p class="muted">{h(metric["metric"])} · {h(metric["metric_direction"])} is better.</p>'
                locations, reason = locator.resolve(run, records[run['execution_id']], figure)
                run['template_links'] = {'locations': locations, 'reason': reason}
                card += candidate_rows({**run, 'matches': matches[:6]}, locations)
            else:
                card += '<p class="muted">No saved candidates.</p>'
            cards.append(card + '</section>')
            if run['status'] not in {'completed', 'duplicate'}:
                issues.append([f'<a href="#{ident}">{h(source["object_id"])}</a>', h(engine),
                               h(run['mode']), badge(run['status']), h(run['reason'] or '—')])
        article += '<div class="report-fits">' + (''.join(cards) or '<p>No planned fits.</p>') + '</div>'
        articles.append(article + '<p class="report-back"><a href="#inventory">Back to inventory ↑</a></p></article>')
        report_records.append({'campaign': 0, 'source': source, 'runs': selected})
        runs.extend(selected)

    snapshot = {'browser_campaign': 0, 'spectra': sources, 'runs': runs}
    write_classification_tables({'snapshots': [snapshot]}, output, native_tables=False)
    counts = dict(sorted(Counter(r['status'] for r in runs).items()))
    # Display annotations and provenance-only receipts do not invalidate a review
    # of the same fits; adopted host/redshift/discovery values still participate.
    identity = digest([{'source': {k: v for k, v in r['source'].items()
                                  if k not in {'flux_unit', 'flux_unit_source', 'tns_name', 'efosc_typing_metadata'}},
                       'runs': [(x['execution_id'], x['record_sha256'], x['status'])
                                                     for x in r['runs']]} for r in report_records])
    evidence = {'schema': 'spectypus-match-report/1', 'plan_id': plan['plan_id'],
                'report_identity': identity, 'automatic_summary_policy': AUTO_POLICY,
                'title': title, 'counts': counts, 'records': report_records,
                'renderer_sha256': file_hash(Path(__file__)),
                'implementation_sha256': {p.name: file_hash(p) for p in Path(__file__).parent.glob('*.py')},
                'presentation_sha256': {p.name: file_hash(p) for p in ASSETS.iterdir() if p.is_file()}}
    downloads = [download_bytes(canonical(evidence).encode(), 'classification-report-evidence.json', 'Data')]
    for filename, label in [('classification_summary.csv', 'Summary CSV'), ('matches.csv', 'Matches CSV'),
                            ('run_status.csv', 'Fit log CSV')]:
        downloads.append(download_bytes((output / filename).read_bytes(), filename, label, 'text/csv'))
    count_text = ' · '.join(f'{count} {status.replace("_", " ")}' for status, count in counts.items())
    body = f'<p class="report-summary">{len(sources)} spectra · {h(count_text)}</p>'
    body += '<nav aria-label="Report sections"><a href="#inventory">Classifications</a><a href="#spectra">Spectra &amp; matches</a><a href="#issues">Issues</a><a href="#night-log">Final night log</a></nav>'
    body += '<section id="inventory"><h2>Classifications</h2>' + table(SUMMARY_HEADERS, inventory)
    body += '<div class="downloads">' + ''.join(downloads) + '</div></section>'
    body += '<section id="spectra"><h2>Spectra &amp; matches</h2>' + ''.join(articles) + '</section>'
    body += '<section id="issues"><h2>Issues</h2>' + (table(['Name', 'Engine', 'z mode', 'State', 'Reason'], issues)
                                                    if issues else '<p>No outstanding fit issues.</p>') + '</section>'
    body += editable_log(report_records, identity)
    css = (ASSETS / 'report.css').read_text()
    if display == 'atlas':
        body = atlas_body(body, sources, articles)
        css += (ASSETS / 'navigation.css').read_text()
    html = page(title, body, display='SpectralAtlas' if display == 'atlas' else 'Classification Report', extra_css=css)
    scripts = ''.join('<script>' + (ASSETS / name).read_text() + '</script>'
                      for name in ('selected-plots.js', 'night-log.js', 'navigation.js'))
    html = html.replace('</body>', scripts + '</body>')
    destination = output / 'index.html'
    atomic_text(destination, html)
    evidence_path = output / 'classification-report-evidence.json'
    atomic_text(evidence_path, canonical(evidence))
    return {'path': str(destination), 'sha256': file_hash(destination), 'identity': identity,
            'evidence_sha256': file_hash(evidence_path),
            'spectra': len(sources), 'fits': len(runs), 'states': counts,
            'figures': sum(r.get('figure', {}).get('status') == 'ready' for r in runs)}
