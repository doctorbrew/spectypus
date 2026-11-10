"""Compact display fields; reviewer summaries remain separate from fit evidence."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build_spectral_atlas import h
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
    discovery = source.get('discovery_date_ut')
    dates = {number(r.get('mjd')) for r in refs if r.get('kind') == 'discovery'} - {None}
    if number(source.get('discovery_mjd')) is not None:
        dates.add(number(source['discovery_mjd']))
    if not discovery and len(dates) == 1:
        discovery = (datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(days=dates.pop())).date().isoformat()
    if not discovery:
        discovery = 'conflicting dates' if dates else '—'
    instrument = source.get('instrument')
    if instrument in (None, '', 'unknown', 'unknown-instrument'):
        instrument = ''
    title = (f'{source["object_id"]} (MJD {source.get("mjd") if source.get("mjd") is not None else "—"}, '
             f'Discovery: {discovery}, Supplied z: {source.get("redshift") if source.get("redshift") is not None else "—"})')
    filename = Path(source.get('path') or source['spectrum_id'].split(':', 1)[-1]).name
    return h(title) + (f' <span class="instrument">{h(instrument)}</span>' if instrument else ''), 'Filename: ' + h(filename)


def write_classification_tables(frozen, root, summaries=None):
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
            for run in runs:
                context = {k: run.get(k) for k in ('object_id', 'spectrum_id', 'execution_id', 'engine', 'mode', 'status', 'record_sha256')}
                context['campaign'] = snapshot['browser_campaign']
                best.append({**context, **(run['matches'][0] if run['matches'] else {})})
                native.extend({**context, **m} for m in run['matches'])
    write_csv(root / 'classification_summary.csv', rows, SUMMARY_HEADERS + ['campaign', 'spectrum_id', 'policy', 'automatic_execution_id', 'automatic_rank', 'automatic_redshift'])
    fields = ['campaign', 'object_id', 'spectrum_id', 'execution_id', 'engine', 'mode', 'status', 'record_sha256',
              'rank', 'template', 'native_class', 'native_subtype', 'redshift', 'phase_days', 'metric', 'score', 'metric_direction', 'qualified', 'native']
    write_csv(root / 'best_matches.csv', best, fields)
    write_csv(root / 'native_matches.csv', native, fields)
    return {'summary_rows': len(rows), 'best_match_rows': len(best), 'native_match_rows': len(native)}


def editable_log(records, identity):
    """A separate reviewer layer: no edits to the automatic inventory or fits."""
    from build_spectral_atlas import table
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
            + '<div class="log-actions"><button type="button" id="save-night-log">Save log</button>'
            + '<button type="button" id="csv-night-log">Download CSV</button>'
            + '<label>Load log <input type="file" id="load-night-log" accept="application/json,.json"></label></div>'
            + '<p id="night-log-status" class="muted" role="status">Automatic draft · edit before saving</p>'
            + '<noscript>Enable JavaScript to save reviewer edits.</noscript>'
            + '<script type="application/json" id="night-log-data">' + payload + '</script></section>')
