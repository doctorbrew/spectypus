#!/usr/bin/env python3
"""Export verified classification evidence to portable SpectralAtlas HTML.

Kept outside src/: running campaigns fingerprint that package. Only the selected
current attempt is read. Retained trials and original products are never changed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from spectral_atlas_products import PLOT_OUTPUT, product_ready, validate_jpg
from spectypus.aggregate import aggregate
from spectypus.features import features
from spectypus.io import atomic_text, canonical, digest, file_hash, read_json, write_csv, write_json
from spectypus.phases import phase_context
from spectypus.pipeline import SCHEMA, current_record
from spectypus.review import compact_record

from spectypus.reporting.html import ASSETS, h, table, badge, page, data_uri, download_bytes
BAD = {'failed', 'blocked', 'invalid_evidence', 'unavailable'}


def now():
    return datetime.now(timezone.utc).isoformat()


def key(value):
    return re.sub(r'[^A-Za-z0-9_-]', '-', value)[:50] + '-' + hashlib.sha256(value.encode()).hexdigest()[:10]




def count_text(counts):
    return ' · '.join(f'{value:,} {name.replace("_", " ")}' for name, value in sorted(counts.items()))






def download(path, label):
    mime = {'.jpg': 'image/jpeg', '.csv': 'text/csv'}.get(path.suffix, 'application/json')
    return download_bytes(path.read_bytes(), path.name, label, mime)


def best_curve(plan, run, record, source):
    """Same candidate/score/galaxy match as the saved-results review endpoint."""
    if not record['candidates'] or 'fit_curves.json' not in record['artifacts']:
        return {'available': False, 'reason': 'No saved model curve for this attempt'}
    payload = read_json(Path(record['attempt_path']) / 'fit_curves.json')
    candidate = record['candidates'][0]
    curve = next((c for c in payload['curves'] if c['template'] == candidate['template']
                  and math.isclose(c['score'], candidate['score'], rel_tol=1e-5, abs_tol=1e-8)
                  and (run['engine'] != 'ngsf' or c.get('galaxy') == candidate['native']['GALAXY'])), None)
    if not curve or not curve.get('available'):
        return {'available': False, 'reason': 'Native model curve unavailable for rank 1'}
    points = curve['observed']
    return {**{k: v for k, v in payload.items() if k != 'curves'}, **curve,
            'candidate': {k: candidate.get(k) for k in ('template', 'phase_days', 'native_class', 'metric', 'score', 'redshift', 'qualified')},
            'rank': 1, 'engine': run['engine'], 'mode': run['mode'], 'execution_id': run['execution_id'],
            'features': features(source['redshift'], points[0][0], points[-1][0], plan['config'].get('telluric_windows', []))}


def capture(source_dir, dest, label):
    started = now()
    source_dir = source_dir.resolve()
    plan = read_json(source_dir / 'plan.json')
    identity = plan.pop('plan_id')
    if plan.get('schema') != SCHEMA or digest(plan) != identity:
        raise ValueError(f'Plan integrity check failed: {source_dir}')
    plan['plan_id'] = identity
    dest.mkdir(parents=True)
    (dest / 'data').mkdir(); (dest / 'figures').mkdir()
    # Preserve the exact selected plan bytes, separately from the portable summary.
    (dest / 'plan.json').write_bytes((source_dir / 'plan.json').read_bytes())
    sources = {s['spectrum_id']: s for s in plan['spectra']}
    records, runs = {}, []
    by_spectrum = defaultdict(list)
    verified = 0
    for run in plan['runs']:
        state = 'blocked' if run['blocked_reason'] else 'pending'
        reason = run['blocked_reason'] or 'Queued or active at snapshot; no saved result'
        if reason.startswith('duplicate_of:'):
            state = 'duplicate'
        record = None if run['blocked_reason'] else current_record(source_dir, run)
        row = {**run, 'matches': [], 'curve_available': False}
        if record is not None:
            state, reason = record['status'], record['reason']
            compact = compact_record(record, plan['config']['top_n'])
            records[run['execution_id']] = compact
            row.update(matches=compact['candidates'][:plan['config']['top_n']],
                       candidate_count=len(record['candidates']), elapsed_seconds=record.get('elapsed_seconds'),
                       attempt_path=record['attempt_path'], record_sha256=file_hash(Path(record['attempt_path']) / 'record.json'),
                       artifacts=record['artifacts'], verified_at=now())
            for match, native in zip(row['matches'], record['candidates']):
                match['native'] = native.get('native', {})
            curve = best_curve(plan, run, record, sources[run['spectrum_id']])
            row['curve_available'] = bool(curve.get('available'))
            row['curve_reason'] = curve.get('reason', '')
            if curve.get('available'):
                by_spectrum[run['spectrum_id']].append(curve)
            verified += 1
            if verified % 250 == 0:
                print(f'{label}: verified {verified} attempts', flush=True)
        elif not run['blocked_reason'] and (source_dir / 'attempts' / run['execution_id'] / 'current.json').exists():
            state, reason = 'invalid_evidence', 'Saved attempt failed integrity verification; excluded from support'
        row.update(status=state, reason=reason)
        runs.append(row)
    refs = {}
    metadata_hash = None
    if (source_dir / 'review_metadata.json').exists():
        meta = read_json(source_dir / 'review_metadata.json')
        if meta.get('plan_id') != identity:
            raise ValueError('Phase metadata belongs to a different plan')
        refs = meta.get('objects', {})
        metadata_hash = file_hash(source_dir / 'review_metadata.json')
        (dest / 'review_metadata.json').write_bytes((source_dir / 'review_metadata.json').read_bytes())
    jobs = []
    for sid, curves in by_spectrum.items():
        source = sources[sid]
        path = dest / 'data' / (key(sid) + '.json')
        write_json(path, {'source': source, 'phase_context': phase_context(source, refs.get(source['object_id'], [])), 'curves': curves})
        jobs.append((str(path), str(dest / 'figures' / key(sid))))
    summary = aggregate(plan, records)
    result = {'schema': 'spectypus-spectralatlas/1', 'label': label, 'source': str(source_dir),
              'plan_id': identity, 'plan_sha256': file_hash(dest / 'plan.json'), 'metadata_sha256': metadata_hash,
              'started_at': started, 'checked_at': now(), 'config': plan['config'], 'provenance': plan['provenance'],
              'package_sha256': plan['package_sha256'], 'spectra': plan['spectra'], 'runs': runs, 'summary': summary,
              'phase_references': refs, 'counts': dict(Counter(r['status'] for r in runs)), 'jobs': jobs}
    write_json(dest / 'snapshot.json', result)
    print(f'{label}: {count_text(result["counts"])}; {len(jobs)} spectrum figures queued', flush=True)
    return result








def candidate_table(run):
    fields = ('rank', 'template', 'native_class', 'native_subtype', 'phase_days', 'redshift', 'metric', 'score', 'metric_direction', 'qualified')
    if not run['matches']:
        return '<p class="muted">No recorded candidates for this fit.</p>'
    ngsf = run['engine'] == 'ngsf'
    headers = ['Rank', 'Template', 'Native class', 'Subtype', 'Template phase (d)', 'Fit z', 'Metric', 'Score', 'Better', 'Qualified']
    if ngsf:
        headers += ['A_v (mag)', 'Galaxy template', 'SN fraction', 'Galaxy fraction']
    rows = []
    for match in run['matches']:
        row = [h(match.get(f)) for f in fields]
        if ngsf:
            row += [h(match.get('native', {}).get(f)) for f in ('A_v', 'GALAXY', 'Frac(SN)', 'Frac(gal)')]
        rows.append(row)
    return table(headers, rows)


def enrich_native(snapshot, snapshot_path):
    """Add native parameter columns to an earlier frozen export, never new fits."""
    changed = False
    for run in snapshot['runs']:
        if not run['matches'] or all('native' in m for m in run['matches']):
            continue
        path = Path(run['attempt_path']) / 'record.json'
        if file_hash(path) != run['record_sha256']:
            raise ValueError('Frozen attempt changed while adding native parameter columns')
        native = read_json(path)['candidates']
        for match, candidate in zip(run['matches'], native):
            if match['template'] != candidate['template'] or match['score'] != candidate['score']:
                raise ValueError('Frozen candidate mismatch')
            match['native'] = candidate.get('native', {})
        changed = True
    if changed:
        write_json(snapshot_path, snapshot)


def figure_card(sid, source, dest, results):
    stem = key(sid)
    result = results.get(stem)
    if not result:
        return '<div class="empty">No verified saved rank-1 curves for this spectrum. Fit statuses and reasons are listed below.</div>'
    if result['status'] != 'ready':
        return f'<p class="bad">Figure unavailable: {h(result.get("reason"))}</p>'
    jpg = dest / 'figures' / result['jpg']
    alt = f'{source["object_id"]}, MJD {source.get("mjd") or "unknown"}: recorded rank-1 observed/model overlays; engine and redshift mode labelled in each panel'
    image = data_uri(jpg.read_bytes(), 'image/jpeg')
    notes = ''.join(f'<p class="bad">Panel unavailable: {h(p.get("reason"))}</p>' for p in result['panels'] if p['status'] != 'rendered')
    clipped = sum(p.get('observed_samples_outside_limits', 0) for p in result['panels'])
    return f'''<figure><button type="button" class="enlarge" aria-label="Enlarge {h(alt)}"><img src="{image}" alt="{h(alt)}" loading="lazy"></button><figcaption>{notes}
<p>Rank 1 from each available fit. Template names, qualification and native scores appear below. Gold: saved telluric masks; dotted rose: catalogue-z host lines.</p><p>Display limits use the canonical 50 Å smoothing rule; plotted samples are unchanged. {clipped} observed samples outside panel limits.</p>
<div class="downloads">{download(jpg, 'JPG · 300 dpi')} {download(dest / 'data' / (stem + '.json'), 'Plotted arrays + metadata')}</div></figcaption></figure>'''


def source_article(source, runs, snapshot, dest, results):
    sid = source['spectrum_id']
    refs = snapshot['phase_references'].get(source['object_id'], [])
    context = phase_context(source, refs)
    from spectypus.fit_plots import phase_lines
    phase = ' · '.join(phase_lines(context))
    metadata = f'MJD {h(source.get("mjd"))} · {h(source.get("instrument"))} · {h(source.get("batch"))} · supplied z {h(source.get("redshift"))}'
    caution = '<p class="bad">Provisional frame assumption: observer frame; scientific review still required.</p>' if source.get('frame_assumed') in (True, 'true') else ''
    header = f'<article id="{key(sid)}"><h3>{h(sid)}</h3><p>{metadata}</p>{caution}<p class="muted">Input: {h(source.get("wavelength_frame"))} frame, {h(source.get("wavelength_unit"))}. Display: observer-frame Å. Redshift provenance: {h(source.get("redshift_source"))}.</p><p class="muted">{h(phase)}</p>'
    header += table(('Engine', 'z mode', 'Role in support', 'State', 'Reason'), [[h(r['engine']), h(r['mode']), 'primary' if r['primary'] else 'diagnostic only', badge(r['status']), h(r['reason']) if r['reason'] else 'None recorded'] for r in runs])
    content = figure_card(sid, source, dest, results)
    for run in runs:
        heading = f'{run["engine"]} · {run["mode"]}-z'
        content += f'<section class="fit"><h4>{h(heading)} {badge(run["status"])}</h4>'
        if not run['curve_available'] and run['matches']:
            content += f'<p class="bad">Model overlay unavailable: {h(run.get("curve_reason"))}</p>'
        content += candidate_table(run)
        if run.get('candidate_count'):
            content += f'<p class="muted">Showing {len(run["matches"])} of {run["candidate_count"]:,} recorded candidates. Template phase is the library phase, separate from the target catalogue phase.</p>'
        content += f'<details><summary>Fit provenance</summary><dl><dt>Execution ID</dt><dd>{h(run["execution_id"])}</dd><dt>Selected immutable attempt</dt><dd>{h(run.get("attempt_path"))}</dd><dt>Record SHA-256</dt><dd>{h(run.get("record_sha256"))}</dd></dl></details></section>'
    record = {'source': source, 'phase_context': context, 'fits': runs}
    content += '<div class="downloads">' + download_bytes((canonical(record) + '\n').encode(), key(sid) + '-evidence.json', 'Spectrum evidence + leading candidates') + '</div>'
    return header + content + '</article>'


def write_campaign(snapshot, dest, results, page_size):
    by_object, by_sid = defaultdict(list), defaultdict(list)
    for s in snapshot['spectra']: by_object[s['object_id']].append(s)
    for r in snapshot['runs']: by_sid[r['spectrum_id']].append(r)
    summaries = {o['object_id']: o for o in snapshot['summary']['objects']}
    inventory = []
    for name, sources in sorted(by_object.items(), key=lambda item: (0 if item[0].startswith('AT') else 1 if item[0].startswith('SN') else 2, item[0])):
        sources.sort(key=lambda s: (str(s.get('mjd') or ''), s['spectrum_id']))
        parts = [sources[i:i + page_size] for i in range(0, len(sources), page_size)]
        filenames = [key(name) + f'-{i + 1}.html' for i in range(len(parts))]
        obj = summaries[name]
        states = Counter(r['status'] for s in sources for r in by_sid[s['spectrum_id']])
        parts_nav = ' '.join(f'<a href="{fn}">Part {i+1}</a>' for i, fn in enumerate(filenames))
        for i, subset in enumerate(parts):
            body = f'<p><a href="../index.html#inventory">All objects</a> · {h(snapshot["label"])}</p><nav>{parts_nav}</nav>'
            body += f'<p>{len(sources):,} spectrum records · {h(count_text(states))}</p><p class="note">Suggestion: {h(obj["proposed_class"] or "none")} ({h(obj["status"])}). Combined support is uncalibrated evidence, with duplicate suppression and primary/diagnostic mode handling preserved. Campaigns are assessed separately.</p>'
            if obj['ranked_classes']:
                body += table(('Class label', 'Uncalibrated support'), [[h(c['class_label']), f'{c["support"]:.5g}'] for c in obj['ranked_classes']])
            body += f'<p class="muted">{obj["contributing_spectra"]} of {obj["unique_spectrum_count"]} unique spectra contribute classified evidence. Abstention mass: {obj["abstention_mass"]:.5g}. These values are dimensionless support weights, not class probabilities.</p><div class="downloads">' + download_bytes((canonical(obj) + '\n').encode(), key(name) + '-support.json', 'Object support record') + '</div>'
            if obj['frame_review_required']:
                body += '<p class="bad">Unvalidated wavelength-frame assumption: this object requires frame review.</p>'
            body += '<nav>' + ''.join(f'<a href="#{key(s["spectrum_id"])}">Spectrum {j+1+i*page_size}</a>' for j, s in enumerate(subset)) + '</nav>'
            body += table(('Spectrum record', 'MJD', 'Instrument', 'Fit states'), [[f'<a href="#{key(s["spectrum_id"])}">{h(s["spectrum_id"])}</a>', h(s.get('mjd')), h(s.get('instrument')), h(count_text(Counter(r['status'] for r in by_sid[s['spectrum_id']])))] for s in subset])
            # Gallery overview retains three columns; full evidence follows visibly.
            available = [s for s in subset if results.get(key(s['spectrum_id']), {}).get('status') == 'ready']
            if available:
                body += '<section><h2>Spectrum gallery</h2><div class="spectrum-grid">'
                for s in available:
                    jpg = dest / 'figures' / results[key(s['spectrum_id'])]['jpg']
                    body += f'<figure><button class="enlarge" type="button" aria-label="Enlarge spectrum at MJD {h(s.get("mjd"))}"><img src="{data_uri(jpg.read_bytes(), "image/jpeg")}" alt="{h(s["spectrum_id"])}; native saved best-match panels" loading="lazy"></button><figcaption><a href="#{key(s["spectrum_id"])}">MJD {h(s.get("mjd"))} · {h(s.get("instrument"))}</a></figcaption></figure>'
                body += '</div></section>'
            body += '<section id="evidence"><h2>Spectra &amp; fit evidence</h2>'
            for s in subset:
                body += source_article(s, by_sid[s['spectrum_id']], snapshot, dest, results)
            body += '</section><section id="record"><h2>Snapshot record</h2><p>Plan ID: ' + h(snapshot['plan_id']) + '</p><p>Evidence was read between ' + h(snapshot['started_at']) + ' and ' + h(snapshot['checked_at']) + '. This is a frozen export of per-fit observations, not an atomic live status report.</p><nav>' + parts_nav + '</nav></section>'
            atomic_text(dest / filenames[i], page(name + (f' / part {i+1}' if len(parts) > 1 else ''), body, snapshot['checked_at'], '../index.html'))
        inventory.append({'object_id': name, 'campaign': snapshot['label'], 'samples': sorted({s.get('batch', '') for s in sources}), 'aliases': sorted({s.get(k, '') for s in sources for k in ('ztf_id', 'tns_name')} - {''}), 'spectra': len(sources), 'unique_spectra': obj['unique_spectrum_count'], 'suggestion': obj['proposed_class'], 'assessment': obj['status'], 'frame_review_required': obj['frame_review_required'], 'counts': dict(states), 'href': dest.name + '/' + filenames[0], 'parts': len(parts)})
    return inventory


def write_archive(root, snapshots):
    """Retain supplied galleries as prior render revisions, outside current totals."""
    entries = []
    archive = root / 'retained-figures'
    for snapshot in snapshots:
        for gallery_path in sorted((Path(snapshot['source']) / 'review_figures').glob('*/gallery.json')):
            folder = gallery_path.parent
            request = read_json(folder / 'request.json')
            gallery = read_json(gallery_path)
            archive.mkdir(exist_ok=True)
            ident = digest({'source': snapshot['source'], 'gallery': folder.name})[:16]
            paths = [gallery['collage']] + gallery['plots']
            body = '<p><a href="../index.html#archive">Atlas overview</a></p><p class="note">Retained prior rendering. This revision is separate from the current snapshot and excluded from its fit and figure totals. Its request metadata and exact figure bytes are preserved below.</p><div class="spectrum-grid">'
            hashes = {}
            for i, item in enumerate(paths):
                jpg = folder / item['jpg']
                # Do not follow a gallery reference outside its render directory.
                if jpg.resolve().parent != folder.resolve():
                    raise ValueError('Invalid retained gallery path')
                title = 'Top candidates collage' if i == 0 else f'Candidate rank {item["rank"]}'
                validate_jpg(jpg)
                hashes[jpg.name] = file_hash(jpg)
                body += f'<figure><button class="enlarge" type="button" aria-label="Enlarge {h(title)}"><img src="{data_uri(jpg.read_bytes(), "image/jpeg")}" alt="{h(title)} for {h(request["source"]["object_id"])}" loading="lazy"></button><figcaption>{h(title)}<div class="downloads">{download(jpg, "Original JPG")}</div></figcaption></figure>'
            body += '</div><section><h2>Retained render record</h2><p>Source: ' + h(folder) + '</p><div class="downloads">' + download(folder / 'request.json', 'Original render request') + download(gallery_path, 'Original gallery manifest') + '</div></section>'
            title = f'{request["source"]["object_id"]} / {request["engine"]} {request["mode"]}-z / retained revision {folder.name[:8]}'
            atomic_text(archive / (ident + '.html'), page(title, body, snapshot['checked_at'], '../index.html'))
            entries.append({'title': title, 'href': 'retained-figures/' + ident + '.html', 'source': str(folder), 'figures': len(paths), 'request_sha256': file_hash(folder / 'request.json'), 'gallery_sha256': file_hash(gallery_path), 'request_digest_matches_directory': digest(request) == folder.name, 'product_hashes': hashes})
    return entries


def write_index(root, snapshots, inventory, rendering):
    stamp = max(s['checked_at'] for s in snapshots)
    campaigns = []
    issues = []
    for s in snapshots:
        campaigns.append([h(s['label']), str(len(s['summary']['objects'])), str(len(s['spectra'])), h(count_text(s['counts']))])
        reason_counts = Counter((r['status'], r['reason']) for r in s['runs'] if r['status'] in BAD)
        issues.extend([h(s['label']), badge(status), str(count), h(reason)] for (status, reason), count in reason_counts.most_common())
    objects_csv = root / 'objects.csv'
    write_csv(objects_csv, inventory, ['object_id', 'campaign', 'samples', 'aliases', 'spectra', 'unique_spectra', 'suggestion', 'assessment', 'frame_review_required', 'counts', 'href', 'parts'])
    body = '<p>Both classification campaigns, with saved native matches, spectrum overlays, unresolved inputs and failed attempts. Open any object to inspect every planned fit.</p><nav><a href="#campaigns">Campaigns</a><a href="#inventory">Object inventory</a><a href="#issues">Issues</a><a href="#method">Reading the evidence</a><a href="#record">Run record</a></nav>'
    body += '<section id="campaigns"><h2>Campaign inventory</h2>' + table(('Campaign', 'Object records', 'Spectrum records', 'Fit states'), campaigns) + '<p class="note">The supplementary Fritz campaign overlaps the main campaign and uses a provisional observer-frame assumption. Rows across these campaigns are not independent objects; support is never combined across campaigns.</p></section>'
    body += '<section id="inventory"><h2>Object inventory</h2><p>Search names, sample labels, suggestions or fit states. Without JavaScript the full inventory remains visible.</p><div class="filters"><label>Find an object <input type="search" id="search" placeholder="e.g. SN2018, chen, failed" autocomplete="off"></label><label>Campaign <select id="campaign"><option value="">All campaigns</option>' + ''.join(f'<option>{h(s["label"])}</option>' for s in snapshots) + '</select></label><label><input type="checkbox" id="issues-only"> Unresolved fits / frame review</label></div><p id="visible-count" aria-live="polite"></p>'
    rows = []
    for o in inventory:
        states = count_text(o['counts'])
        unresolved = o['frame_review_required'] or any(o['counts'].get(state) for state in BAD | {'pending'})
        search = ' '.join(str(o.get(k) or '') for k in ('object_id', 'suggestion', 'assessment', 'samples', 'aliases')) + ' ' + states
        cells = [f'<a href="{o["href"]}">{h(o["object_id"])}</a><br><span class="muted">{h(" / ".join(o.get("aliases", [])))}</span>', h(o['campaign']) + '<br>' + h(', '.join(o.get('samples', []))), str(o['spectra']), h(o['suggestion'] or 'No suggestion'), h(o['assessment']), h(states), '<span class="bad">Frame unvalidated</span>' if o['frame_review_required'] else 'No assumed-frame flag']
        rows.append(f'<tr data-search="{h(search.lower())}" data-campaign="{h(o["campaign"])}" data-unresolved="{str(bool(unresolved)).lower()}">' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
    body += '<div class="table-wrap"><table id="objects"><thead><tr>' + ''.join(f'<th scope="col">{c}</th>' for c in ('Object', 'Campaign', 'Spectra', 'Suggestion', 'Assessment', 'Fit states', 'Frame review')) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div><div class="downloads">' + download(objects_csv, 'Download object inventory CSV') + '</div></section>'
    body += '<section id="issues"><h2>Issues requiring review</h2>' + table(('Campaign', 'State', 'Fits', 'Recorded reason'), issues) + '</section>'
    body += '''<section id="method"><h2>Reading the evidence</h2><p><b>Completed</b> means an engine saved candidates. <b>No good match</b> is a valid finished outcome with no qualifying match. <b>Failed</b> means execution failed. <b>Blocked</b> means the declared input contract prevented a fit. <b>Pending</b> means no saved result was present when that fit was checked. <b>Duplicate</b> is a suppressed repeated spectrum. <b>Invalid evidence</b> is excluded after a failed integrity check.</p><p>Figures show saved rank-1 models, including unqualified candidates when retained. Leading-candidate tables preserve native class/subtype, redshift, template phase, score, score direction and qualification. Raw scores from different classifiers are not comparable. The existing equal-engine support calculation preserves abstentions, unique-spectrum weights and primary versus diagnostic redshift modes.</p><p>Wavelength axes use observer-frame Å. NGSF displays normalized flux; SNID-SAGE displays continuum residual flux. Gold bands are the saved telluric masks; dotted host lines use the supplied catalogue redshift, including on free-z fits. Plot limits follow the canonical 50 Å display-only smoothing rule; plotted flux arrays are unchanged. Supplied target phase references remain distinct from template phases.</p><p>Every object report embeds its images, 300-dpi JPG downloads and plotted arrays. Copy the whole export folder to keep object navigation. A single object-part HTML works independently for its displayed spectra. Original native result banks and retained trials remain at their recorded source paths and hashes; they are not reclassified or merged here.</p></section>'''
    retained = write_archive(root, snapshots)
    if retained:
        body += '<section id="archive"><h2>Retained figure revisions</h2><p>Previously supplied galleries, preserved separately from the current figures and fit totals.</p>' + table(('Prior rendering', 'Figures', 'Request digest'), [[f'<a href="{e["href"]}">{h(e["title"])}</a>', str(e['figures']), 'matches saved identifier' if e['request_digest_matches_directory'] else '<span class="bad">Unvalidated request identifier</span>'] for e in retained]) + '</section>'
    records = {'plot_output': PLOT_OUTPUT, 'schema': 'spectypus-spectralatlas-manifest/1', 'created_at': now(), 'snapshots': [{k: s[k] for k in ('label', 'source', 'plan_id', 'plan_sha256', 'metadata_sha256', 'started_at', 'checked_at', 'counts', 'config', 'provenance', 'package_sha256')} for s in snapshots], 'rendering': rendering, 'retained_galleries': retained, 'builder_sha256': file_hash(Path(__file__)), 'figure_renderer_sha256': file_hash(ROOT / 'scripts/spectral_atlas_figures.py'), 'canonical_plot_style_sha256': file_hash(ROOT / 'src/spectypus/plot_style.py'), 'display_limits_sha256': file_hash(ROOT / 'src/spectypus/fit_plots.py'), 'object_reports': len(inventory), 'html_parts': sum(o['parts'] for o in inventory), 'interpretation': 'Exploratory suggestions; support is not a probability; campaigns overlap and remain separate'}
    records['presentation_sha256'] = {name: file_hash(ASSETS / name) for name in ('atlas.css', 'atlas.js')}
    write_json(root / 'manifest.json', records)
    body += '<section id="record"><h2>Run record</h2><p>' + h(f'{rendering["ready"]:,} spectrum figures exported; {rendering["failed"]:,} figure exports unavailable. {len(inventory):,} campaign/object entries across {records["html_parts"]:,} portable object parts.') + '</p><div class="downloads">' + download(root / 'manifest.json', 'Snapshot manifest JSON') + '</div><p>Refresh with a new export directory to preserve this revision. A running campaign can advance after the snapshot; no classifier was invoked by this export.</p></section>'
    atomic_text(root / 'index.html', page('Classification atlas / ' + stamp[:10], body, stamp))
    return records


def write_welcome(root, snapshots, rendering):
    """A small portable entry page, also suitable for an inline preview."""
    stamp = max(s['checked_at'] for s in snapshots)
    states = ('completed', 'no_good_match', 'failed', 'pending')
    styles = '<style>.status-bar{display:flex;height:18px;border-radius:4px;overflow:hidden;background:var(--border);margin:10px 0}.status-bar span:nth-child(1){background:#497c61}.status-bar span:nth-child(2){background:#a78d63}.status-bar span:nth-child(3){background:#b42318}.status-bar span:nth-child(4){background:#c8ccc2}.welcome-figure{max-width:760px;margin:22px 0}.welcome-figure img{width:100%;height:auto}</style>'
    body = '<p>Inspect the recorded classifications, native model comparisons and unresolved fits across both campaigns.</p><nav><a href="index.html#inventory">Browse all objects</a><a href="index.html#issues">Review failures &amp; blocked inputs</a><a href="index.html#record">Snapshot provenance</a></nav><section><h2>Saved-fit inventory</h2>'
    body += table(('Campaign', 'Object records', 'Spectra', 'Fits eligible to run'), [[h(s['label']), str(len(s['summary']['objects'])), str(len(s['spectra'])), str(sum(s['counts'].get(k, 0) for k in states))] for s in snapshots])
    for s in snapshots:
        total = sum(s['counts'].get(k, 0) for k in states)
        body += '<h3>' + h(s['label']) + '</h3><div class="status-bar" role="img" aria-label="' + h(count_text({k:s['counts'].get(k,0) for k in states})) + '">'
        body += ''.join(f'<span style="width:{100*s["counts"].get(k,0)/max(1,total):.4f}%" title="{h(k)}: {s["counts"].get(k,0)}"></span>' for k in states) + '</div><p class="muted">' + h(count_text({k:s['counts'].get(k,0) for k in states})) + '</p>'
    body += '<p class="note">Green: candidates saved · ochre: no good match · red: execution failed · pale: pending. Blocked inputs and duplicates are listed separately in the full inventory. Campaigns overlap; Fritz frame assumptions remain provisional.</p></section>'
    first_job = next((j for s in snapshots for j in s['jobs']), None)
    if first_job:
        from spectral_atlas_figures import render_spectrum
        request = read_json(Path(first_job[0]))
        request['curves'] = request['curves'][:1]
        request_path = root / 'welcome-example.json'
        write_json(request_path, request)
        result = render_spectrum((str(request_path), str(root / 'welcome-example')))
        jpg = root / result['jpg']
        source, curve = request['source'], request['curves'][0]
        caption = f'{source["object_id"]} / MJD {source.get("mjd") or "unknown"} / {curve["engine"]} {curve["mode"]}-z / rank 1'
        body += '<section><h2>A view inside the atlas</h2><p>' + h(f'{rendering["ready"]:,} spectrum comparison figures; every planned fit remains visible with its recorded status.') + '</p><figure class="welcome-figure"><button class="enlarge" type="button" aria-label="Enlarge saved fit example"><img id="welcome-image" src="' + data_uri(jpg.read_bytes(), 'image/jpeg') + '" alt="' + h(caption) + '"></button><figcaption>' + h(caption) + '<p>Example only; the object reports include all available engine/redshift panels, leading candidates and plotted arrays. Gold bands mark saved telluric masks; axes use observer-frame Å and the engine flux convention.</p><div class="downloads"><a id="welcome-jpg" download="welcome-example.jpg" data-sha256="' + file_hash(jpg) + '" href="welcome-example.jpg">JPG · 300 dpi</a>' + '</div></figcaption></figure></section><script>document.querySelector("#welcome-jpg").href=document.querySelector("#welcome-image").src;</script>'
    body += '<p><a href="index.html">Open the complete searchable atlas →</a></p>'
    atomic_text(root / 'welcome.html', page('Classification atlas / ' + stamp[:10], styles + body, stamp))


def build(args):
    root = args.output.resolve()
    if args.resume:
        snapshots = [read_json(p) for p in sorted(root.glob('campaign-*/snapshot.json'))]
        if not snapshots:
            raise ValueError('No frozen snapshots to resume')
    else:
        if root.exists():
            raise ValueError('Choose a new output directory, or --resume for its frozen snapshot')
        root.mkdir(parents=True)
        snapshots = [capture(source, root / f'campaign-{i+1}', label) for i, (source, label) in enumerate(zip(args.campaign, args.label))]
    jobs = [job for s in snapshots for job in s['jobs']]
    results_path = root / 'figure-results.json'
    results = read_json(results_path) if results_path.exists() else {}
    contract = {'plot_output': PLOT_OUTPUT, 'products_sha256': file_hash(ASSETS.parent / 'products.py'), 'renderer_sha256': file_hash(ROOT / 'scripts/spectral_atlas_figures.py'),
                'style_sha256': file_hash(ROOT / 'src/spectypus/plot_style.py'),
                'limits_sha256': file_hash(ROOT / 'src/spectypus/fit_plots.py'),
                'requests': {str(Path(j[0]).relative_to(root)): file_hash(Path(j[0])) for j in jobs}}
    contract_path = root / 'render-contract.json'
    if contract_path.exists() and read_json(contract_path) != contract:
        raise ValueError('Frozen plot requests or renderer changed; choose a new export revision')
    if not contract_path.exists():
        if results:
            raise ValueError('Existing figures lack a render contract; choose a new export revision')
        write_json(contract_path, contract)
    def ready(job):
        result = results.get(job[1], {})
        if result.get('status') != 'ready':
            return False
        folder = Path(job[1]).parent
        return product_ready(folder, result)
    missing = [j for j in jobs if not ready(j)]
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', MPLBACKEND='Agg')
    # One shared cache for the export, outside immutable attempts.
    os.environ['MPLCONFIGDIR'] = str(root / '.plot-cache')
    from spectral_atlas_figures import render_spectrum
    print(f'Rendering {len(missing)} spectrum figures with {args.workers} workers', flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(render_spectrum, j): j for j in missing}
        for i, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                results[job[1]] = future.result()
                results[job[1]]['product_hashes'] = {k: file_hash(Path(job[1]).parent / results[job[1]][k]) for k in ('jpg',)}
            except Exception as exc:
                results[job[1]] = {'status': 'unavailable', 'reason': f'{type(exc).__name__}: {exc}'}
            if i % 25 == 0:
                write_json(results_path, results)
                print(f'Figures {i}/{len(missing)}; unavailable {sum(r["status"] != "ready" for r in results.values())}', flush=True)
    write_json(results_path, results)
    inventory = []
    for i, snapshot in enumerate(snapshots):
        dest = root / f'campaign-{i+1}'
        enrich_native(snapshot, dest / 'snapshot.json')
        selected = {Path(stem).name: result for stem, result in results.items() if Path(stem).parent == dest / 'figures'}
        inventory.extend(write_campaign(snapshot, dest, selected, args.page_size))
        print(f'HTML written: {snapshot["label"]}', flush=True)
    rendering = {'ready': sum(r['status'] == 'ready' for r in results.values()), 'failed': sum(r['status'] != 'ready' for r in results.values()), 'requested': len(jobs), 'workers': args.workers}
    manifest = write_index(root, snapshots, inventory, rendering)
    write_welcome(root, snapshots, rendering)
    # Byte manifest covers portable products, excluding only transient plotting caches.
    hashes = {str(p.relative_to(root)): file_hash(p) for p in sorted(root.rglob('*')) if p.is_file() and '.plot-cache' not in p.parts and p.name != 'checksums.json'}
    write_json(root / 'checksums.json', hashes)
    print(f'Atlas ready: {root / "index.html"}\n{canonical({"rendering": rendering, "object_reports": manifest["object_reports"], "html_parts": manifest["html_parts"]})}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, action='append', default=[])
    parser.add_argument('--label', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    parser.add_argument('--page-size', type=int, default=6)
    parser.add_argument('--resume', action='store_true', help='Resume this export, retaining its frozen evidence snapshot')
    args = parser.parse_args()
    if not args.resume and (not args.campaign or len(args.campaign) != len(args.label)):
        parser.error('Supply one --label for each --campaign')
    if args.page_size < 1:
        parser.error('--page-size must be positive')
    build(args)


if __name__ == '__main__':
    main()
