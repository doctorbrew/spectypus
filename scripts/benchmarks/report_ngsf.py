"""Render measured trial results; refuses partial or non-equivalent evidence."""
import argparse
import csv
from html import escape
import json
from pathlib import Path
import statistics


def report(cache_root, core_root, output, paired_path=None):
    first = json.loads((cache_root / 'fixed/comparison.json').read_text())
    second = json.loads((core_root / 'fixed/comparison.json').read_text())
    if not first['all_exact'] or not second['all_exact'] or not second['complete']:
        raise ValueError('only complete equivalent trials can be reported')
    rows = first['rows'] + second['rows']
    names = ['Native', 'Error cache', '+ Galaxy cache', '+ Reuse intermediates']
    stages = []
    for stage, name in enumerate(names):
        cases = [r for r in rows if r['stage'] == stage]
        if len(cases) != 5 or len({r['spectrum_id'] for r in cases}) != 5:
            raise ValueError('expected five distinct spectra per stage')
        stages.append({'stage': stage, 'label': name,
                       'core_seconds': sum(r['metrics']['inclusive_seconds']['core'] for r in cases),
                       'attempt_seconds': sum(r['attempt_seconds'] for r in cases),
                       'cpu_seconds': sum(r['metrics']['process_cpu_seconds'] for r in cases),
                       'error_computations': sum(r['metrics']['counts']['error_computations'] for r in cases),
                       'galaxy_computations': sum(r['metrics']['counts']['galaxy_computations'] for r in cases)})
    comparison = []
    for sid in sorted({r['spectrum_id'] for r in rows}):
        cases = sorted((r for r in rows if r['spectrum_id'] == sid), key=lambda r: r['stage'])
        row = {'spectrum_id': sid, 'object_id': cases[0]['object_id'], 'status': cases[0]['status']}
        for r in cases:
            row[f"stage_{r['stage']}_core_seconds"] = r['metrics']['inclusive_seconds']['core']
            row[f"stage_{r['stage']}_attempt_seconds"] = r['attempt_seconds']
        comparison.append(row)
    ratios = [r['stage_0_core_seconds'] / r['stage_3_core_seconds'] for r in comparison]
    summary = {'scope': 'Five known-redshift spectra; 41 extinction points each; unchanged native bank, masks and scores.',
               'all_exact': True, 'comparison_count': len(first['checks']) + len(second['checks']),
               'stages': stages, 'spectra': comparison,
               'median_paired_core_speed_ratio': statistics.median(ratios),
               'core_total_speed_ratio': stages[0]['core_seconds'] / stages[3]['core_seconds'],
               'attempt_total_speed_ratio': stages[0]['attempt_seconds'] / stages[3]['attempt_seconds'],
               'limitation': 'One run per spectrum and stage, background priority, concurrent production campaigns. Observed timings, not a controlled throughput benchmark. Recorded attempt time excludes planning and final artifact hashing. Free-redshift searches and JAX are untested.'}
    if paired_path:
        paired = json.loads(paired_path.read_text())
        if not paired['all_exact'] or len(paired['rows']) != 5:
            raise ValueError('paired replay must cover all five spectra exactly')
        summary['paired_arithmetic'] = paired
    output.mkdir(parents=True, exist_ok=False)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    with (output / 'per_spectrum.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparison[0]))
        writer.writeheader()
        writer.writerows(comparison)

    def chart(key, title):
        maximum = max(s[key] for s in stages)
        bars = ''.join(f'<div class="barrow"><span>{escape(s["label"])}</span>'
                       f'<div class="track"><div class="bar" style="width:{100*s[key]/maximum:.2f}%;'
                       f'background:var(--chart-{s["stage"]+1},currentColor)"></div></div>'
                       f'<b>{s[key]:.1f} s</b></div>' for s in stages)
        return f'<section><h3>{title}</h3><p class="muted">Total for the same five spectra · lower is faster</p>{bars}</section>'

    table = ''.join(f'<tr><td>{escape(r["object_id"])}</td><td>{r["status"]}</td>'
                    f'<td>{r["stage_0_core_seconds"]:.2f}</td><td>{r["stage_3_core_seconds"]:.2f}</td>'
                    f'<td>{r["stage_0_core_seconds"]/r["stage_3_core_seconds"]:.2f}×</td></tr>' for r in comparison)
    html = '''<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;color:var(--foreground);font-family:var(--font-sans,system-ui);font-size:14px}
    section{margin:20px 0}h3{font-size:16px;margin:0 0 6px}.muted{color:var(--muted-foreground);font-size:12px}
    .barrow{display:grid;grid-template-columns:160px 1fr 65px;align-items:center;gap:10px;height:36px}
    .track{height:16px;background:var(--secondary);border-radius:3px}.bar{height:16px;border-radius:3px}
    b{text-align:right;font-family:var(--font-mono,monospace);font-size:12px}
    table{width:100%;border-collapse:collapse;font-size:12px}td,th{text-align:left;padding:8px 4px;border-bottom:1px solid var(--border)}
    .result{background:var(--card);padding:16px;border-radius:var(--radius);line-height:1.6}
    @media(max-width:450px){.barrow{grid-template-columns:120px 1fr 60px;gap:5px;font-size:12px}}
    </style></head><body>'''
    html += '<p class="result">Five copied SLSN spectra · fixed catalogue redshifts · full extinction grid.<br>'
    html += f'<strong>{summary["comparison_count"]} exact comparisons passed:</strong> candidates, native CSV, fit curves, masks and staged input.</p>'
    if paired_path:
        html += '<section><h3>Paired arithmetic replay</h3><p class="muted">Same saved arrays; alternating order; five measured pairs per spectrum. Excludes interpolation, error estimation and I/O.</p>'
        html += '<table><thead><tr><th>Object</th><th>Native CPU (s)</th><th>Reuse CPU (s)</th><th>Median paired ratio</th></tr></thead><tbody>'
        for row in paired['rows']:
            html += f'<tr><td>{escape(row["object_id"])}</td><td>{row["median_native_cpu_seconds"]:.3f}</td><td>{row["median_reuse_cpu_seconds"]:.3f}</td><td>{row["median_paired_cpu_ratio"]:.2f}×</td></tr>'
        html += '</tbody></table></section>'
    html += '<p class="muted">Full-fit timings below were observed under varying concurrent load; their differences do not establish causal cache speedups.</p>'
    html += chart('core_seconds', 'Observed native fitting-core time') + chart('attempt_seconds', 'Observed recorded attempt time')
    html += '<section><h3>Native versus reused intermediates</h3><table><thead><tr><th>Object</th><th>Outcome</th><th>Native core (s)</th><th>Reuse core (s)</th><th>Ratio</th></tr></thead><tbody>' + table + '</tbody></table></section>'
    html += '<p class="muted">' + escape(summary['limitation']) + '</p></body></html>'
    (output / 'comparison.html').write_text(html)
    display = {k: v for k, v in summary.items() if k not in ('spectra', 'paired_arithmetic')}
    if paired_path:
        display['paired_arithmetic_median_ratio'] = paired['median_spectrum_cpu_ratio']
    print(json.dumps(display, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--core-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--paired', type=Path)
    args = parser.parse_args()
    report(args.cache_root, args.core_root, args.output, args.paired)
