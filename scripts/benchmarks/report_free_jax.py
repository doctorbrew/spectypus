"""Report full free-z equivalence separately from experimental arithmetic speed."""
import argparse
import csv
import json
from pathlib import Path
import statistics


def report(free_root, jax_root, output):
    free = json.loads((free_root / 'comparison.json').read_text())
    trial = json.loads((jax_root / 'results.json').read_text())
    if not free['complete'] or not free['all_exact'] or not trial['complete']:
        raise ValueError('report requires completed evidence; JAX numerical failures are retained')
    rows = []
    for row in trial['rows']:
        pairs = row['paired_timings']
        rows.append({
            'object_id': row['object_id'], 'kind': row['kind'], 'z': row['z'], 'dtype': row['dtype'],
            'accepted': row['assessment']['accepted'],
            'top10_exact': row['assessment']['top10_indices_exact'],
            'native_cpu_seconds': statistics.median(p['native']['cpu'] for p in pairs),
            'reuse_cpu_seconds': statistics.median(p['reuse']['cpu'] for p in pairs),
            'jax_cpu_seconds': statistics.median(p['jax']['cpu'] for p in pairs),
            'chunked_cpu_seconds': statistics.median(p['chunked_reuse']['cpu'] for p in pairs),
            'reuse_relative_cpu': statistics.median(100*p['reuse']['cpu']/p['native']['cpu'] for p in pairs),
            'chunked_relative_cpu': statistics.median(100*p['chunked_reuse']['cpu']/p['native']['cpu'] for p in pairs),
            'jax_relative_cpu': statistics.median(100*p['jax']['cpu']/p['native']['cpu'] for p in pairs),
            'reuse_cpu_speed_ratio': statistics.median(p['native']['cpu']/p['reuse']['cpu'] for p in pairs),
            'jax_cpu_speed_ratio': row['paired_cpu_speed_ratio'],
            'jax_vs_reuse_cpu_speed_ratio': row['paired_reuse_cpu_speed_ratio'],
            'jax_vs_chunked_cpu_speed_ratio': row['paired_chunked_reuse_cpu_speed_ratio'],
            'first_call_seconds': row['first_shape_call_seconds'],
            'new_compilation_shape': row['new_compilation_shape'],
            'cpu_to_wall': row['observed_cpu_to_wall']})
    double = [r for r in rows if r['dtype'] == 'float64']
    summary = {
        'free_spectra': len(free['rows']),
        'free_grid_points': sum(r['metrics']['counts']['core_calls'] for r in free['rows']),
        'free_all_exact': free['all_exact'],
        'float64_accepted': sum(r['accepted'] for r in double),
        'float64_total': len(double),
        'float32_accepted': sum(r['accepted'] for r in rows if r['dtype'] == 'float32'),
        'failed_edge_cases': [k for k, v in trial['edge_checks'].items() if not v['accepted']],
        'numerical_acceptance': trial['numerical_acceptance'],
        'median_jax_cpu_speed_ratio': statistics.median(r['jax_cpu_speed_ratio'] for r in double),
        'median_jax_vs_reuse_cpu_speed_ratio': statistics.median(r['jax_vs_reuse_cpu_speed_ratio'] for r in double),
        'median_jax_vs_chunked_cpu_speed_ratio': statistics.median(r['jax_vs_chunked_cpu_speed_ratio'] for r in double),
        'max_cpu_to_wall': max(r['cpu_to_wall'] for r in rows),
        'limitations': 'A_v=0 arithmetic replay only. Full free-z checks use NumPy intermediate reuse. JAX is not a production backend or a whole-search speed measurement.',
        'rows': rows}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    with (output / 'per_fixture.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    html = '''<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;font-family:var(--font-sans,system-ui);color:var(--foreground);font-size:14px;line-height:1.5}
    p{margin:10px 0}.muted{color:var(--muted-foreground);font-size:12px}
    label{display:block;margin:18px 0 8px}select{font:inherit;color:var(--foreground);background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:6px;max-width:100%}
    .chart{height:190px}.row{height:46px;display:grid;grid-template-columns:140px 1fr 60px;align-items:center;gap:10px}
    .track{background:var(--secondary,ButtonFace);height:20px;border-radius:3px}.bar{height:20px;border-radius:3px;background:var(--chart-1,currentColor)}
    .reuse{background:var(--chart-2,currentColor)}.chunked{background:var(--chart-3,currentColor)}.jax{background:var(--chart-4,currentColor)}.value{font-family:var(--font-mono,monospace);font-size:12px;text-align:right}
    .note{background:var(--card);padding:16px;border-radius:var(--radius);margin-top:18px}
    .warn{color:var(--warning)}table{border-collapse:collapse;width:100%;font-size:12px;margin:14px 0}td,th{text-align:left;padding:6px 4px;border-bottom:1px solid var(--border)}
    @media(max-width:450px){.row{grid-template-columns:110px 1fr 50px;gap:5px;font-size:12px}}
    </style></head><body>
    <p><strong id="free"></strong><br><span class="muted">Full native redshift and extinction grid; statuses, candidates, CSVs, curves and masks agree exactly.</span></p>
    <label for="fixture">Arithmetic CPU cost · native = 100% · lower is faster</label>
    <select id="fixture"><option value="all">Median across all 20 saved grid points</option></select>
    <div class="chart" role="img" aria-label="Relative arithmetic CPU cost">
    <div class="row"><span>Native NumPy</span><div class="track"><div id="native" class="bar" style="width:100%"></div></div><span class="value">100%</span></div>
    <div class="row"><span>Reuse reductions</span><div class="track"><div id="reuse" class="bar reuse"></div></div><span id="reusevalue" class="value"></span></div>
    <div class="row"><span>Reuse in blocks</span><div class="track"><div id="chunked" class="bar chunked"></div></div><span id="chunkedvalue" class="value"></span></div>
    <div class="row"><span>JAX float64</span><div class="track"><div id="jax" class="bar jax"></div></div><span id="jaxvalue" class="value"></span></div>
    </div><p id="timing" class="muted"></p>
    <div class="note"><strong class="warn">JAX remains experimental</strong><p id="acceptance"></p>
    <p class="muted">These bars exclude interpolation, loading templates, reconstructing native tables, and compilation. Five alternating-order timing pairs per fixture. They do not predict whole-campaign throughput.</p></div>
    <table><thead><tr><th>Free-z spectrum</th><th>Grid points</th><th>Native result preserved</th></tr></thead><tbody id="spectra"></tbody></table>
    <p class="muted">The SLSN campaign keeps its existing code and configuration. Tests use copied data in a separate worktree.</p>
    <script>
    const data=__DATA__, free=__FREE__, rows=data.rows.filter(r=>r.dtype==='float64');
    const median=a=>{const b=[...a].sort((x,y)=>x-y);return (b[Math.floor((b.length-1)/2)]+b[Math.floor(b.length/2)])/2};
    const el=id=>document.getElementById(id), select=el('fixture');
    el('free').textContent=`${data.free_spectra}/5 full free-redshift fits match · ${data.free_grid_points.toLocaleString()} grid points checked`;
    rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${r.object_id} · ${r.kind} z=${r.z}`;select.append(o)});
    function draw(){const chosen=select.value==='all'?rows:[rows[+select.value]];
      const values=Object.fromEntries(['reuse','chunked','jax'].map(k=>[k,median(chosen.map(r=>r[k+'_relative_cpu']))]));const max=Math.max(100,...Object.values(values));el('native').style.width=10000/max+'%';
      for(const [k,value] of Object.entries(values)){el(k).style.width=(100*value/max)+'%';el(k+'value').textContent=value.toFixed(1)+'%'}
      el('timing').textContent=select.value==='all'?'Median of per-fixture paired CPU ratios; 5 fixed-z and 15 free-z fixtures, all at A_v=0.':`Native ${chosen[0].native_cpu_seconds.toFixed(3)} s · reuse ${chosen[0].reuse_cpu_seconds.toFixed(3)} s · JAX ${chosen[0].jax_cpu_seconds.toFixed(3)} s per grid point (median CPU).`;
    }
    select.addEventListener('change',draw);draw();
    el('acceptance').textContent=`Float64 passes ${data.float64_accepted}/${data.float64_total} real fixtures. Float32 passes ${data.float32_accepted}/${data.float64_total}. Failed edge cases: ${data.failed_edge_cases.map(s=>s.replaceAll('_',' ')).join(', ')||'none'}. No production backend was enabled.`;
    free.forEach(r=>{const tr=document.createElement('tr');for(const value of [r.object_id,r.metrics.counts.core_calls,'Exact']){const td=document.createElement('td');td.textContent=value;tr.append(td)}el('spectra').append(tr)});
    </script></body></html>'''
    html = html.replace('__DATA__', json.dumps(summary).replace('</', '<\\/')).replace('__FREE__', json.dumps(free['rows']).replace('</', '<\\/'))
    (output / 'comparison.html').write_text(html)
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--free-root', required=True, type=Path)
    parser.add_argument('--jax-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report(args.free_root, args.jax_root, args.output)
