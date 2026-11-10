#!/usr/bin/env python3
"""SN-first offline browser with six saved native matches per engine/mode.

Consumes a verified frozen atlas export; never advances to newer current pointers
or invokes a classifier. HTML and figure/data assets travel as one directory.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import json
import math
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from spectral_atlas_products import PLOT_OUTPUT, product_ready
from spectypus.features import features
from spectypus.fit_plots import phase_lines
from spectypus.io import canonical, digest, file_hash, read_json, write_json, atomic_text
from spectypus.phases import phase_context, number
from build_spectral_atlas import h, key, badge, page, table, count_text

ASSETS = ROOT / 'assets/spectralatlas'


def target_phases(source, context):
    """Keep supplied rest phases and catalogue-derived phases distinct."""
    supplied = number(source.get('phase_rest_days'))
    lines = []
    if supplied is not None:
        lines.append(f'Supplied target phase: {supplied:+.1f} d (rest; spectrum metadata; zero-point reference unspecified)')
    if context['references'] or supplied is None:
        lines += [line.replace('Target:', 'Catalogue phase:', 1) for line in phase_lines(context)]
    return lines


def saved_matches(run, payload, source, config):
    """Match each displayed native rank, including NGSF's galaxy identity."""
    result = []
    for candidate in run['matches'][:6]:
        native = next((c for c in payload.get('curves', [])
                       if c['template'] == candidate['template']
                       and math.isclose(c['score'], candidate['score'], rel_tol=1e-5, abs_tol=1e-8)
                       and (run['engine'] != 'ngsf' or c.get('galaxy') == candidate.get('native', {}).get('GALAXY'))), None)
        curve = {'available': False, 'reason': 'No saved model curve for this native candidate'}
        if native and native.get('available'):
            points = native.get('observed', [])
            if len(points) > 1 and len(native.get('model', [])) > 1:
                curve = {**{k: v for k, v in payload.items() if k != 'curves'}, **native,
                         'rank': candidate['rank'], 'features': features(source['redshift'], points[0][0], points[-1][0], config.get('telluric_windows', []))}
        result.append({'candidate': candidate, 'curve': curve})
    return result


def saved_input(run):
    """Preserve the exact staged observer-frame input, before engine masking."""
    expected = run.get('artifacts', {}).get('spectrum.txt')
    if not expected:
        return {'available': False, 'reason': 'No verified staged input in this saved attempt'}
    path = Path(run['attempt_path']) / 'spectrum.txt'
    if file_hash(path) != expected:
        raise ValueError(f'Frozen input spectrum changed: {path}')
    return {'available': True, 'artifact': 'spectrum.txt', 'sha256': expected,
            'contents': path.read_bytes().decode('utf-8'), 'wavelength_frame': 'observer',
            'wavelength_unit': 'angstrom', 'flux_unit': 'input units',
            'origin': 'Exact staged spectrum before engine preprocessing; no display mask or refitting'}


def prepare(previous, root):
    checksums = read_json(previous / 'checksums.json')
    snapshots, jobs = [], []
    (root / 'data').mkdir(parents=True); (root / 'figures').mkdir(); (root / 'objects').mkdir()
    for index, path in enumerate(sorted(previous.glob('campaign-*/snapshot.json')), 1):
        if file_hash(path) != checksums[str(path.relative_to(previous))]:
            raise ValueError('Source snapshot failed integrity verification')
        snapshot = read_json(path)
        snapshot['browser_campaign'] = index
        sources = {s['spectrum_id']: s for s in snapshot['spectra']}
        for i, run in enumerate(snapshot['runs']):
            run['matches'] = run['matches'][:6]
            run['plot_key'] = f'c{index}-' + run['execution_id']
            run['curve_ranks'] = []
            if not run['matches']:
                continue
            payload = {}
            curve_file = Path(run['attempt_path']) / 'fit_curves.json'
            expected = run.get('artifacts', {}).get('fit_curves.json')
            if expected:
                if file_hash(curve_file) != expected:
                    raise ValueError(f'Frozen saved curves changed: {curve_file}')
                payload = read_json(curve_file)
            source = sources[run['spectrum_id']]
            matches = saved_matches(run, payload, source, snapshot['config'])
            run['curve_ranks'] = [m['candidate']['rank'] for m in matches if m['curve']['available']]
            request = {'schema': 'spectypus-six-matches/1', 'source': source, 'engine': run['engine'], 'mode': run['mode'],
                       'execution_id': run['execution_id'], 'record_sha256': run['record_sha256'], 'curve_source_sha256': expected,
                       'input_spectrum': saved_input(run),
                       'phase_context': phase_context(source, snapshot['phase_references'].get(source['object_id'], [])), 'matches': matches}
            if run['curve_ranks']:
                from spectral_atlas_full_observed import make_transform
                request['display_transform'] = make_transform(request, run)
            request_path = root / 'data' / (run['plot_key'] + '.json.gz')
            request_path.write_bytes(gzip.compress(canonical(request).encode(), compresslevel=3, mtime=0))
            if run['curve_ranks']:
                jobs.append((str(request_path), str(root / 'figures' / run['plot_key'])))
            if i % 250 == 0: print(f'{snapshot["label"]}: selected saved ranks through fit {i}', flush=True)
        snapshots.append(snapshot)
        print(f'{snapshot["label"]}: {sum(len(r["curve_ranks"]) for r in snapshot["runs"])} saved curve panels selected', flush=True)
    # Render a known useful object first, then stable path order.
    priorities = {f'c{s["browser_campaign"]}-{r["execution_id"]}' for s in snapshots for r in s['runs'] if r['object_id'] == 'SN2018avk'}
    jobs.sort(key=lambda j: (Path(j[1]).name not in priorities, j[1]))
    frozen = {'schema': 'spectypus-spectral-browser/1', 'previous_export': str(previous), 'created_at': datetime.now(timezone.utc).isoformat(), 'snapshots': snapshots, 'jobs': jobs}
    write_json(root / 'browser-snapshot.json', frozen)
    return frozen



def prepare_browser(previous, root):
    """Re-render verified frozen requests without native preprocessing or refits."""
    checks = read_json(previous / 'checksums.json')
    if file_hash(previous / 'browser-snapshot.json') != checks['browser-snapshot.json']:
        raise ValueError('Source browser snapshot failed integrity verification')
    frozen = read_json(previous / 'browser-snapshot.json')
    requests = sorted((previous / 'data').glob('*.json.gz'))
    if {str(p.relative_to(previous)) for p in requests} != {p for p in checks if p.startswith('data/')}:
        raise ValueError('Source browser numerical inventory changed')
    for path in requests:
        if file_hash(path) != checks[str(path.relative_to(previous))]:
            raise ValueError(f'Frozen browser request changed: {path}')
    (root / 'data').mkdir(parents=True)
    (root / 'figures').mkdir(); (root / 'objects').mkdir()
    for path in requests:
        # Hard links save space; frozen numerical evidence is never edited.
        # Copy only if the destination is on a different filesystem.
        try:
            os.link(path, root / 'data' / path.name)
        except OSError:
            shutil.copy2(path, root / 'data' / path.name)
    restoration = previous / 'model-restoration.json'
    if restoration.exists():
        if file_hash(restoration) != checks.get('model-restoration.json'):
            raise ValueError('Source model restoration audit changed')
        shutil.copy2(restoration, root / restoration.name)
    catalog = previous / 'template-locations.json'
    if catalog.exists():
        if file_hash(catalog) != checks.get(catalog.name):
            raise ValueError('Source template locations changed')
        shutil.copy2(catalog, root / catalog.name)
    frozen['jobs'] = [(str(root / 'data' / Path(request).name), str(root / 'figures' / Path(stem).name))
                      for request, stem in frozen['jobs']]
    frozen['presentation_source'] = {'directory': str(previous), 'snapshot_sha256': checks['browser-snapshot.json'],
                                     'note': 'Frozen scientific snapshots and numerical requests reused; only job output paths relocated.'}
    write_json(root / 'browser-snapshot.json', frozen)
    return frozen


def candidate_rows(run, locations=None):
    from spectral_atlas_rank_table import template_cell, decimal_cell, galaxy_cell
    locations = locations or {}
    headers = ['Rank', 'Template', 'Fit z', 'Native score']
    if run['engine'] == 'ngsf': headers += ['Aᵥ (mag)', 'Galaxy type (fraction)']
    rows = []
    for m in run['matches']:
        native = m.get('native', {})
        identity = template_cell(m, locations.get(str(m['rank'])))
        score = decimal_cell(m['score']) + ('' if m['qualified'] else '<br><span class="bad">Unqualified</span>')
        row = [str(m['rank']), identity, decimal_cell(m['redshift']), score]
        if run['engine'] == 'ngsf': row += [h(native.get('A_v')), galaxy_cell(native)]
        rows.append(row)
    return table(headers, rows)


def sidebar(objects, selected, prefix):
    rows = []
    for obj in objects:
        terms = ' '.join([obj['name'], *obj['aliases']]).lower()
        current = 'aria-current="page"' if obj['name'] == selected else ''
        rows.append(f'<a href="{prefix}objects/{key(obj["name"])}.html" data-sn="{h(terms)}" {current}><span>{h(obj["name"])}</span><small>{obj["spectra"]} records · {len(obj["campaigns"])} campaign(s)</small></a>')
    return f'<aside class="sn-sidebar" aria-label="Supernova navigation"><a class="sidebar-brand" href="{prefix}index.html">Spectypus<br><span>SpectralAtlas</span></a><label for="sn-search">Find a supernova</label><input id="sn-search" type="search" placeholder="SN name or ZTF alias" autocomplete="off"><p id="sn-count" class="muted">{len(objects)} objects</p><nav class="sn-list">'+''.join(rows)+f'</nav><a class="summary-link" href="{prefix}summary.html">Campaign summary &amp; provenance</a></aside>'


def browser_page(title, body, frozen, objects, selected, prefix):
    stamp = max(s['checked_at'] for s in frozen['snapshots'])
    html = page(title, body, stamp, prefix + 'index.html')
    html = html.replace('<body>', '<body class="sn-browser">' + sidebar(objects, selected, prefix), 1)
    html = html.replace('</style>', (ASSETS / 'browser.css').read_text() + '</style>', 1)
    return html.replace('</body>', '<script>' + (ASSETS / 'browser.js').read_text() + '</script></body>', 1)


def fit_card(run, results, prefix, curve_notes=(), locations=None, *, asset_url=None, compact=False):
    url = asset_url or (lambda name: prefix + name)
    engine = 'NGSF' if run['engine'] == 'ngsf' else 'SNID-SAGE'
    heading = f'{engine} · {run["mode"]}-z'
    body = f'<section class="fit-card" data-execution="{h(run["execution_id"])}" data-engine="{h(run["engine"])}" data-mode="{h(run["mode"])}"><h4>' + h(heading) + ' ' + badge(run['status']) + '</h4><p class="muted">' + ('Primary evidence' if run['primary'] else 'Diagnostic fit; excluded from primary support') + '</p>'
    if run['reason']: body += '<p class="' + ('bad' if run['status'] in {'blocked', 'failed', 'invalid_evidence'} else 'muted') + '">' + h(run['reason']) + '</p>'
    if not run['matches']: return body + '<p class="empty">No saved candidates for this fit.</p></section>'
    first = run['matches'][0]
    body += '<p class="muted">' + h(first['metric']) + ' · ' + h(first['metric_direction']) + ' is better. Showing ' + str(len(run['matches'])) + ' of ' + str(run.get('candidate_count', len(run['matches']))) + ' native candidates.</p>'
    result = results.get(run['plot_key'])
    if result and result['status'] == 'ready':
        title = f'{run["object_id"]} / {heading}: best {len(run["matches"])} saved native candidates'
        figure_url = h(url('figures/' + result['jpg']))
        image_download = f'download="{h(result["jpg"])}"' if asset_url else 'target="_blank" rel="noopener"'
        image_label = 'Download JPG' if asset_url else 'Open JPG'
        panels = [p for p in result['panels'] if p['status'] == 'rendered']
        smoothing_note = ''
        if panels and 'savgol_filtered_samples' in panels[0]:
            supported = sum(p['savgol_filtered_samples'] > 0 for p in panels)
            smoothing_note = (f' 10 Å smoothing is supported on {supported} of {len(panels)} panels; coarse portions retain native flux.'
                              if supported else ' Saved sampling is too coarse or short for 10 Å smoothing; black observed curves retain native flux.')
        clipped = panels[0].get('limit_raw_samples_outside', 0) if panels else 0
        offscale = sum(p.get('model_entirely_outside_limits', False) for p in panels)
        if offscale:
            smoothing_note += f' {offscale} saved model(s) lie entirely outside the observed-spectrum y-range and are labelled in their panels; their native arrays are unchanged.'
        smoothing_note += f' Robust y-limits place {clipped} raw input samples outside the visible range; all samples remain in the numerical download.'
        body += f'<figure><button class="enlarge" type="button" aria-label="Enlarge {h(title)}"><img src="{figure_url}" loading="lazy" alt="{h(title)}"></button><figcaption>Up to six ranked matches: full input observations in black, raw input in grey (alpha 0.2), and coral models restored to input flux units. Legends give the target and matched SN names, the matched template’s native type, and recorded phases. Unknown or ambiguous target phases are explicit. Short grey bars mark telluric intervals; observed samples there are retained. Matched models are displayed through the excluded fit bands without a display mask; original template coverage still limits their wavelength extent. Dotted lines: catalogue-z host positions.{h(smoothing_note)}</figcaption></figure><div class="downloads"><a href="{figure_url}" {image_download}>{image_label} · 300 dpi</a></div>'
        if compact:
            body = body.replace('<figcaption>', '<figcaption>Up to six ranked native matches · full observed spectrum and unmasked models.<details><summary>Plot display details</summary>', 1).replace('</figcaption>', '</details></figcaption>', 1)
    elif not run['curve_ranks']:
        body += '<p class="bad">Saved model curves unavailable. Candidate scores remain visible below.</p>'
    else:
        body += '<p class="bad">Figure unavailable: ' + h((result or {}).get('reason', 'Figure generation incomplete')) + '</p>'
    body += candidate_rows(run, locations)
    for note in curve_notes:
        body += '<p class="muted">' + h(f"Rank {note['rank']}: the saved model curve uses Aᵥ={note['evaluated_parameters']['A_v']:.3g} from an equal-score native solution; the results table retains its original Aᵥ={note['saved_parameters']['A_v']} row. Both parameter records are preserved in the numerical download.") + '</p>'
    missing = [m['rank'] for m in run['matches'] if m['rank'] not in run['curve_ranks']]
    if missing: body += '<p class="bad">No saved model for rank(s): ' + ', '.join(map(str, missing)) + '.</p>'
    evidence_url = h(url('data/' + run['plot_key'] + '.json.gz'))
    body += f'<div class="downloads"><a href="{evidence_url}" download="{h(run["plot_key"])}.json.gz">Six-candidate evidence + plotted arrays (.json.gz)</a></div><details><summary>Fit provenance</summary><p>Execution: {h(run["execution_id"])}</p><p>Record SHA-256: {h(run.get("record_sha256"))}</p><p>{h(run.get("attempt_path"))}</p></details></section>'
    return body


def write_browser(frozen, root, results):
    groups = defaultdict(list)
    locations = read_json(root / 'template-locations.json').get('locations', {}) if (root / 'template-locations.json').exists() else {}
    curve_notes = defaultdict(list)
    if (root / 'model-restoration.json').exists():
        for note in read_json(root / 'model-restoration.json').get('curve_parameter_recoveries', []):
            curve_notes[note['plot_key']].append(note)
    for s in frozen['snapshots']:
        by_sid = defaultdict(list)
        for run in s['runs']: by_sid[run['spectrum_id']].append(run)
        for source in s['spectra']:
            groups[source['object_id']].append((s, source, by_sid[source['spectrum_id']]))
    objects = [{'name': name, 'spectra': len(rows), 'campaigns': sorted({s['browser_campaign'] for s, source, runs in rows}),
                'aliases': sorted({source.get(k, '') for s, source, runs in rows for k in ('ztf_id', 'tns_name')} - {''})} for name, rows in sorted(groups.items())]
    featured = 'SN2018avk' if 'SN2018avk' in groups else objects[0]['name']
    for name, rows in groups.items():
        rows.sort(key=lambda item: (item[0]['browser_campaign'], number(item[1].get('mjd')) if number(item[1].get('mjd')) is not None else float('inf'), item[1]['spectrum_id']))
        for prefix, path in ([('../', root / 'objects' / (key(name) + '.html'))] + ([('', root / 'index.html')] if name == featured else [])):
            body = '<p>Every available spectrum, with up to six native candidates from SNID-SAGE and NGSF. Target phase and template phase are shown separately.</p><div class="epoch-controls"><label>Spectrum / epoch <select id="epoch-jump"><option value="">Choose an epoch</option>'
            for s, source, runs in rows:
                ident = f'c{s["browser_campaign"]}-' + key(source['spectrum_id'])
                body += f'<option value="{ident}">{h(s["label"])} · MJD {h(source.get("mjd"))} · {h(source.get("instrument"))}</option>'
            body += '</select></label><button type="button" id="expand-epochs">Expand all spectra</button><button type="button" id="collapse-epochs">Collapse all spectra</button></div>'
            body += '<p class="muted">Table redshifts and scores are rounded to three decimals; full precision is retained in the numerical download and tooltips. Galaxy percentages are native model flux contributions. Template links open original files in the local bank; SNID links open an HDF5 container, with its group/epoch in the tooltip. These optional source links require the bank on this computer.</p>'
            previous_campaign = None; opened = False
            for s, source, runs in rows:
                if s['browser_campaign'] != previous_campaign:
                    previous_campaign = s['browser_campaign']
                    obj = next(o for o in s['summary']['objects'] if o['object_id'] == name)
                    body += f'<section class="campaign-heading"><h2>{h(s["label"])}</h2><p>{h(count_text(Counter(r["status"] for cs, _, rr in rows if cs["browser_campaign"]==previous_campaign for r in rr)))}</p><p class="muted">Automated suggestion: {h(obj["proposed_class"] or "none")} ({h(obj["status"])}). Support is uncalibrated and assessed separately for each campaign.</p></section>'
                context = phase_context(source, s['phase_references'].get(name, []))
                phases = target_phases(source, context)
                ident = f'c{s["browser_campaign"]}-' + key(source['spectrum_id'])
                initial_open = not opened and any(r['matches'] for r in runs)
                opened |= initial_open
                states = Counter(r['status'] for r in runs)
                body += f'<details class="epoch" id="{ident}" {"open" if initial_open else ""}><summary><span class="epoch-title">MJD {h(source.get("mjd"))} · {h(source.get("instrument"))}</span><span class="epoch-phase">{h(" · ".join(phases))}</span><span class="muted">{h(count_text(states))}</span></summary><div class="epoch-content">'
                if source.get('frame_assumed') in (True, 'true'):
                    body += '<p class="bad">Observer-frame assumption is provisional; wavelength-frame review is still required.</p>'
                body += f'<p class="muted">{h(source["spectrum_id"])}<br>Supplied z: {h(source.get("redshift"))} · input {h(source.get("wavelength_frame"))} frame / {h(source.get("wavelength_unit"))} · display observer-frame Å.</p><details><summary>Target phase references and redshift provenance</summary><p>{h(source.get("redshift_source"))}</p>'
                for ref in context['references']:
                    body += '<p>' + h(f'{ref["kind"]}, {ref["band"]}, reference MJD {ref["mjd"]}; {ref["source"]}:{ref["field"]}; rest days {ref["rest_days"]}, observer days {ref["observer_days"]}') + '</p>'
                body += '</details><div class="fit-grid">' + ''.join(fit_card(r, results, prefix, curve_notes[r['plot_key']], locations.get(r['plot_key'])) for r in sorted(runs, key=lambda r: (r['mode'] != 'fixed', r['engine'] != 'snid_sage'))) + '</div></div></details>'
            body += '<p class="note">Dark observed curves use 10 Å Savitzky–Golay display smoothing of the full staged input; every original input sample appears behind them in grey at alpha 0.2. The full input wavelength range is displayed. NGSF masked model samples are reconstructed from verified templates and saved fit coefficients, then normalization is reversed. SNID models are displayed using the replay-verified observed continuum and flux offset; this is a display conversion, not a flux-calibrated template SED, and the native model taper remains. No observation mask is applied to either matched-model display. Shared y-limits use a separate 50 Å running-median and Savitzky–Golay trend, omit filter-edge support, retain its central 99% range, allow three times a robust first-difference scatter scale for ordinary noise, and expand it outward by a factor of 1.1. This is display clipping, not rejection of scientific samples. Short or coarse input uses an explicitly recorded fallback. Telluric regions remain eligible; no extra plotting mask is applied. Native gaps remain gaps; samples too coarse for a 10 Å filter are retained unsmoothed. Ranks are engine-native rankings, not six necessarily distinct supernovae. A saved candidate is not a confirmed classification. Unknown target phases remain unknown; discovery time is not explosion time.</p>'
            atomic_text(path, browser_page(name, body, frozen, objects, name, prefix))
    summary = '<p>Frozen saved evidence. The main and provisional Fritz campaigns overlap; their support scores remain separate.</p>'
    summary += table(('Campaign', 'Objects', 'Spectrum records', 'Fit states'), [[h(s['label']), str(len(s['summary']['objects'])), str(len(s['spectra'])), h(count_text(s['counts']))] for s in frozen['snapshots']])
    summary += '<section><h2>How to read matches</h2><p>Each spectrum expands to show SNID-SAGE and NGSF, with fixed/free redshift modes separately labelled. Native scores preserve their direction and qualification; they are not interchangeable between engines. Template phase comes from the template library; target phase uses the recorded catalogue reference and frame.</p><p>Completed, no good match, failed, blocked, pending, duplicate and invalid evidence remain distinct. Missing curves are explicit. No classification was rerun to create this browser.</p></section>'
    summary += '<section><h2>Offline files</h2><p>Copy this entire directory. Pages, 300-dpi JPG figures and compressed numerical evidence use local relative links; no server, network, CDN or remote fonts are required.</p><div class="downloads"><a href="manifest.json" download>Browser manifest</a><a href="browser-snapshot.json" download>Frozen evidence snapshot</a></div></section>'
    atomic_text(root / 'summary.html', browser_page('Classification results', summary, frozen, objects, '', ''))
    return objects


def render_contract(root, jobs):
    return {'plot_output': PLOT_OUTPUT, 'products': file_hash(ROOT / 'scripts/spectral_atlas_products.py'), 'atlas_limits': file_hash(ROOT / 'scripts/spectral_atlas_limits.py'), 'renderer': file_hash(ROOT / 'scripts/spectral_atlas_top5_figures.py'), 'full_observed': file_hash(ROOT / 'scripts/spectral_atlas_full_observed.py'), 'style': file_hash(ROOT / 'src/spectypus/plot_style.py'), 'limits': file_hash(ROOT / 'src/spectypus/fit_plots.py'), 'requests': {str(Path(j[0]).relative_to(root)): file_hash(Path(j[0])) for j in jobs}}


def build(args):
    root = args.output.resolve()
    if args.resume:
        frozen = read_json(root / 'browser-snapshot.json')
    else:
        if root.exists(): raise ValueError('Use a fresh output directory, or --resume')
        frozen = (prepare_browser(args.from_browser.resolve(), root) if getattr(args, 'from_browser', None)
                  else prepare(args.from_export.resolve(), root))
    jobs = frozen['jobs']
    if jobs and not (root / 'model-restoration.json').exists():
        raise ValueError('Prepare verified unmasked models with prepare_unmasked_spectral_browser.py before rendering this browser')
    if jobs and read_json(root / 'model-restoration.json').get('status') != 'passed':
        raise ValueError('Model restoration has not passed verification')
    contract = render_contract(root, jobs)
    contract_path = root / 'render-contract.json'
    if contract_path.exists() and read_json(contract_path) != contract: raise ValueError('Render contract changed; create a new revision')
    if not contract_path.exists() and (root / 'figure-results.json').exists():
        raise ValueError('Existing figures lack a render contract; create a new revision')
    write_json(contract_path, contract)
    results_path = root / 'figure-results.json'; results = read_json(results_path) if results_path.exists() else {}
    def ready(j):
        return product_ready(root / 'figures', results.get(Path(j[1]).name, {}))
    missing = [j for j in jobs if not ready(j)]
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', MPLBACKEND='Agg', MPLCONFIGDIR=str(root / '.plot-cache'))
    # Reuse the existing generated TeX/font cache, never an attempt cache.
    cache_source = Path(frozen.get('presentation_source', {}).get('directory', frozen['previous_export'])) / '.plot-cache'
    if not (root / '.plot-cache').exists() and cache_source.exists(): shutil.copytree(cache_source, root / '.plot-cache')
    from spectral_atlas_top5_figures import render_matches
    print(f'Rendering {len(missing)} six-match figures with {args.workers} workers', flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(render_matches, job): job for job in missing}
        for i, future in enumerate(as_completed(futures), 1):
            job = futures[future]; ident = Path(job[1]).name
            try:
                result = future.result(); result['product_hashes'] = {k: file_hash(root / 'figures' / result[k]) for k in ('jpg',)}
                results[ident] = result
            except Exception as exc: results[ident] = {'status': 'unavailable', 'reason': f'{type(exc).__name__}: {exc}'}
            if i % 50 == 0:
                write_json(results_path, results); print(f'Figures {i}/{len(missing)}; unavailable {sum(r["status"] != "ready" for r in results.values())}', flush=True)
    write_json(results_path, results)
    publish(frozen, root, results)


def publish(frozen, root, results):
    contract_path = root / 'render-contract.json'
    objects = write_browser(frozen, root, results)
    manifest = {'plot_output': PLOT_OUTPUT, 'schema': frozen['schema'], 'created_at': frozen['created_at'], 'objects': len(objects), 'campaign_object_records': sum(len(s['summary']['objects']) for s in frozen['snapshots']),
                'spectra': sum(len(s['spectra']) for s in frozen['snapshots']), 'fits': sum(len(s['runs']) for s in frozen['snapshots']),
                'displayed_candidates': sum(len(r['matches']) for s in frozen['snapshots'] for r in s['runs']), 'saved_curves': sum(len(r['curve_ranks']) for s in frozen['snapshots'] for r in s['runs']),
                'figures': len(results), 'unavailable_figures': sum(r['status'] != 'ready' for r in results.values()), 'source_export': frozen['previous_export'], 'presentation_source': frozen.get('presentation_source'),
                'plot_presentation': {'top_k': 6, 'layout': '2x3-matches-only', 'tick_label_points': 13.5, 'savgol_width_angstrom': 10., 'panels_with_smoothing_support': sum(p.get('savgol_filtered_samples', 0) > 0 for r in results.values() for p in r.get('panels', [])), 'limit_rule': 'median50-sg50-central99-noise3-outward1.1', 'limit_smoothing_width_angstrom': 50., 'limit_percentiles': [0.5, 99.5], 'limit_noise_multiplier': 3., 'legend_native_type': True, 'raw_observed_colour': '0.5', 'raw_observed_alpha': .2, 'observed_display': '10 Angstrom SG over full staged input flux', 'observed_source': 'full-staged-input', 'model_display': 'unmasked verified native models in input flux units', 'model_masking': 'none', 'telluric_display': 'all saved samples; no additional display mask',
                                      'telluric_markers': 'short grey bars; no shaded blocks',
                                      'legend_location': 'upper right', 'legend_shadow': False, 'y_label': 'Flux',
                                      'palette_reference': 'EFOSpec/scripts/preview_spectrum_style.py',
                                      'observed_colour': '#000000', 'model_colour': '#ef6666',
                                      'model_colour_definition': '60% xkcd:red mixed with 40% white, opaque'},
                'snapshots': [{k: s[k] for k in ('label', 'plan_id', 'started_at', 'checked_at', 'counts')} for s in frozen['snapshots']],
                'builder_sha256': file_hash(Path(__file__)), 'render_contract_sha256': file_hash(contract_path), 'presentation_sha256': {n: file_hash(ASSETS / n) for n in ('atlas.css', 'atlas.js', 'browser.css', 'browser.js')}}
    if (root / 'model-restoration.json').exists():
        manifest['model_restoration_sha256'] = file_hash(root / 'model-restoration.json')
    manifest['rank_table'] = {'schema': 'spectypus-compact-ranks/1', 'redshift_decimals': 3, 'score_decimals': 3,
                             'galaxy_fraction': 'native Frac(gal), rounded integer percent',
                             'formatter_sha256': file_hash(ROOT / 'scripts/spectral_atlas_rank_table.py')}
    if (root / 'template-locations.json').exists():
        manifest['rank_table']['template_locations_sha256'] = file_hash(root / 'template-locations.json')
    if (root / 'jpg-migration.json').exists():
        manifest['jpg_migration'] = {'path': 'jpg-migration.json', 'sha256': file_hash(root / 'jpg-migration.json'),
                                     'note': 'Existing JPG bytes reused from the recorded legacy renderer; numerical evidence unchanged.'}
    write_json(root / 'manifest.json', manifest)
    checks = {str(p.relative_to(root)): file_hash(p) for p in sorted(root.rglob('*')) if p.is_file() and '.plot-cache' not in p.parts and p.name != 'checksums.json'}
    write_json(root / 'checksums.json', checks)
    print(f'Browser ready: {root / "index.html"}\n{canonical(manifest)}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument('--from-export', type=Path)
    sources.add_argument('--from-browser', type=Path, help='Reuse verified compressed requests from an existing browser; no preprocessing')
    parser.add_argument('--output', type=Path, required=True)
    maximum_workers = min(8, os.cpu_count() or 1)
    parser.add_argument('--workers', type=int, choices=range(1, maximum_workers + 1), default=min(4, maximum_workers))
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if not args.resume and not (args.from_export or args.from_browser): parser.error('--from-export or --from-browser is required for a new browser')
    build(args)


if __name__ == '__main__': main()
