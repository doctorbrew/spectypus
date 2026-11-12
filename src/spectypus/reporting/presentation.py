"""Compact display fields; reviewer summaries remain separate from fit evidence."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from .html import h
from spectypus.io import read_json, write_csv
from spectypus.phases import number

SUMMARY_HEADERS = ['Name', 'Type', 'z', 'Phase', 'Survey']
AUTO_POLICY = 'qualified-native-first/ngsf-free-snid-free-ngsf-fixed-snid-fixed/1'


def automatic_selection(runs):
    """Display priority, not a comparison/calibration of different native scores."""
    choices = []
    for run in runs:
        if run.get('status') != 'completed':
            continue
        candidate = next((m for m in run['matches'] if m.get('qualified')), None)
        if candidate is not None:
            priority = (run['mode'] != 'free', run['engine'] != 'ngsf', candidate['rank'], run['execution_id'])
            choices.append((priority, run, candidate))
    if not choices:
        return {}, {}
    _, run, candidate = min(choices, key=lambda item: item[0])
    return run, candidate


def summary_key(snapshot, source):
    return f'c{snapshot["browser_campaign"]}:{source["spectrum_id"]}'


def load_summaries(path, frozen):
    if path is None:
        return {}
    payload = read_json(path)
    if payload.get('schema') != 'spectypus-reviewed-summary/1':
        raise ValueError('Expected spectypus-reviewed-summary/1')
    available = {summary_key(s, x) for s in frozen['snapshots'] for x in s['spectra']}
    records = {}
    for row in payload['records']:
        key = f'c{row["campaign"]}:{row["spectrum_id"]}'
        if key not in available or key in records:
            raise ValueError('Unknown or repeated summary spectrum/campaign')
        if not row.get('reference'):
            raise ValueError('Reviewer summary needs a reference')
        records[key] = row
    return records


def summary_values(source, runs, review=None):
    review = review or {}
    selected, candidate = automatic_selection(runs)
    if review.get('execution_id'):
        selected = next((r for r in runs if r['execution_id'] == review['execution_id']), None)
        if selected is None or selected.get('record_sha256') != review.get('record_sha256'):
            raise ValueError('Reviewed selection does not match the saved fit record')
        candidate = next((m for m in selected['matches'] if m['rank'] == review.get('rank')), None)
        if candidate is None:
            raise ValueError('Reviewed candidate rank is absent')
    kind = review.get('type') or candidate.get('native_subtype') or candidate.get('native_class') or '—'
    if kind.startswith(('Ia', 'Ib', 'Ic', 'II')):
        kind = 'SN' + kind
    phase = review.get('phase')
    if not phase and number(candidate.get('phase_days')) is not None:
        phase = f'{number(candidate["phase_days"]):+g} d'
    z, method = number(review.get('redshift')), review.get('redshift_method')
    if z is not None and method not in ('spectral_match', 'narrow_lines'):
        raise ValueError('Summary redshift requires spectral_match or narrow_lines provenance')
    if z is None and source.get('narrow_line_redshift_source'):
        z = number(source.get('narrow_line_redshift'))
        if z is not None:
            method = 'narrow_lines'
    if z is None and selected.get('mode') == 'free':
        z, method = number(candidate.get('redshift')), 'spectral_match'
    host = review.get('host_redshift', source.get('host_redshift'))
    host = host if number(host) is not None else None
    text = f'{z:.3f}' if z is not None else '—'
    if host is not None:
        text += f' (host {host})'
    survey = review.get('survey') or source.get('discovery_survey') or source.get('survey') or '—'
    values = [source['object_id'], kind, text, phase or '—', survey]
    title = review.get('reference') or (f'Automatic: {AUTO_POLICY}; {selected.get("engine")} {selected.get("mode")}; rank {candidate.get("rank")}' if candidate else 'No qualified match')
    return values, {'type': title, 'redshift': f'{method or "unresolved"}; full z: {z}; host: {host}',
                    'phase': title + ('; native template phase' if not review.get('phase') and candidate else '')}


def summary_row(source, runs, href, review=None, *, context=''):
    values, tips = summary_values(source, runs, review)
    return [f'<a href="{h(href)}" title="{h(context)}">{h(values[0])}</a>',
            f'<span title="{h(tips["type"])}">{h(values[1])}</span>',
            f'<span title="{h(tips["redshift"])}">{h(values[2])}</span>',
            f'<span title="{h(tips["phase"])}">{h(values[3])}</span>', h(values[4])]


def spectrum_heading(source, refs=()):
    from .metadata import mjd_from_utc
    discovery = number(source.get('discovery_mjd'))
    dates = {number(r.get('mjd')) for r in refs if r.get('kind') == 'discovery'} - {None}
    if discovery is None and source.get('discovery_date_ut'):
        try:
            discovery = mjd_from_utc(source['discovery_date_ut'])
        except ValueError:
            pass
    if discovery is None and len(dates) == 1:
        discovery = next(iter(dates))
    observed = number(source.get('mjd'))
    def date_text(value):
        return f'<span title="{h(value)}">{value:.3f}</span>' if value is not None else '—'
    discovery_text = date_text(discovery)
    url = source.get('discovery_source', '')
    if urlparse(url).scheme in {'https', 'http'}:
        discovery_text = f'<a href="{h(url)}" target="_blank" rel="noopener">{discovery_text}</a>'
    phase = (f' (Phase {observed - discovery:+.1f} d since discovery)'
             if observed is not None and discovery is not None else '')
    host, z = source.get('host_name'), number(source.get('host_redshift'))
    host_text = h(host) if host else '—'
    if host and z is not None:
        host_text += f' (z={z:.3f})'
    host_text = f'<span title="{h(source.get("host_source") or "No identified host cross-match")}; full z: {h(z)}">{host_text}</span>'
    filename = Path(source.get('path') or source['spectrum_id'].split(':', 1)[-1]).name
    link = source.get('spectrum_url', '')
    if urlparse(link).scheme not in {'http', 'https'}:
        path = Path(source.get('path') or '')
        link = path.as_uri() if path.is_absolute() and path.is_file() else ''
    filename = (f'<a href="{h(link)}" target="_blank" rel="noopener" title="Open source spectrum">{h(filename)}</a>'
                if link else h(filename))
    return h(source['object_id']), (f'Discovery MJD: {discovery_text}<br>'
                                  f'Observed MJD: {date_text(observed)}{phase}<br>'
                                  f'Host Cross-match: {host_text}<br>Filename: {filename}')


def write_classification_tables(frozen, root, summaries=None, *, native_tables=True):
    summaries = summaries or {}
    rows, best, native = [], [], []
    for snapshot in frozen['snapshots']:
        for source in snapshot['spectra']:
            runs = [r for r in snapshot['runs'] if r['spectrum_id'] == source['spectrum_id']]
            values, _ = summary_values(source, runs, summaries.get(summary_key(snapshot, source)))
            selected, candidate = automatic_selection(runs)
            rows.append({**dict(zip(SUMMARY_HEADERS, values)), 'campaign': snapshot['browser_campaign'],
                         'spectrum_id': source['spectrum_id'], 'policy': AUTO_POLICY,
                         'automatic_execution_id': selected.get('execution_id'),
                         'automatic_rank': candidate.get('rank'), 'automatic_redshift': candidate.get('redshift') if selected.get('mode') == 'free' else None})
            for run in runs if native_tables else ():
                context = {k: run.get(k) for k in ('object_id', 'spectrum_id', 'execution_id', 'engine', 'mode', 'status', 'record_sha256')}
                context['campaign'] = snapshot['browser_campaign']
                best.append({**context, **(run['matches'][0] if run['matches'] else {})})
                native.extend({**context, **m} for m in run['matches'])
    write_csv(root / 'classification_summary.csv', rows, SUMMARY_HEADERS + ['campaign', 'spectrum_id', 'policy', 'automatic_execution_id', 'automatic_rank', 'automatic_redshift'])
    fields = ['campaign', 'object_id', 'spectrum_id', 'execution_id', 'engine', 'mode', 'status', 'record_sha256',
              'rank', 'template', 'native_class', 'native_subtype', 'redshift', 'phase_days', 'metric', 'score', 'metric_direction', 'qualified', 'native']
    if native_tables:
        write_csv(root / 'best_matches.csv', best, fields)
        write_csv(root / 'native_matches.csv', native, fields)
    return {'summary_rows': len(rows), 'best_match_rows': len(best), 'native_match_rows': len(native)}


def editable_log(records, identity):
    """A separate reviewer layer: no edits to the automatic inventory or fits."""
    from .html import table
    rows = []
    for record in records:
        source, runs = record['source'], record['runs']
        values, _ = summary_values(source, runs)
        ident = f"c{record['campaign']}:{source['spectrum_id']}"
        row = []
        for field, value in zip(SUMMARY_HEADERS, values):
            row.append(f'<input aria-label="{h(values[0])} {field}" data-key="{h(ident)}" data-field="{field}" value="{h(value)}">')
        rows.append(row)
    payload = json.dumps({'identity': identity, 'records': records}, ensure_ascii=True).replace('<', chr(92) + 'u003c')
    return ('<section id="night-log"><h2>Final night log</h2>' + table(SUMMARY_HEADERS, rows)
            + '<div class="log-actions"><button type="button" id="save-night-log" title="Save reviewer edits as a reloadable JSON file">Save log</button>'
            + '<button type="button" id="csv-night-log" title="Export the current edited table as night-log.csv">Download CSV</button>'
            + '<button type="button" id="copy-night-log">Copy text</button>'
            + '<label title="Restore a JSON log saved for these spectra and fits">Load log <input type="file" id="load-night-log" accept="application/json,.json"></label></div>'
            + '<textarea id="night-log-copy-text" aria-label="Final night log as text" rows="7" readonly hidden></textarea>'
            + '<p id="night-log-status" class="muted" role="status">Automatic draft · edit before saving</p>'
            + '<noscript>Enable JavaScript to save reviewer edits.</noscript>'
            + '<script type="application/json" id="night-log-data">' + payload + '</script></section>')
