"""Show complete-fit observations separately from arithmetic microbenchmarks."""
import argparse
import json
from pathlib import Path
import statistics


def report(root, output):
    data = json.loads((root/'complete.json').read_text())
    if not data['all_exact'] or len(data['rows']) != 20:
        raise ValueError('requires completed equivalent integration evidence')
    fixed = [r for r in data['rows'] if r['mode']=='fixed']
    free = [r for r in data['rows'] if r['mode']=='free']
    totals = {k:sum(r['seconds'] for r in fixed if r['backend']==k) for k in ('native','numpy','jax')}
    cases = []
    for object_id in sorted({r['object_id'] for r in fixed}):
        cases.append({'object_id':object_id, **{r['backend']:r['seconds'] for r in fixed if r['object_id']==object_id}})
    summary = {'fixed_totals':totals,'fixed_cases':cases,
        'seconds_saved':totals['native']-totals['jax'],
        'percent_time_saved':100*(1-totals['jax']/totals['native']),
        'total_speed_ratio':totals['native']/totals['jax'],
        'median_spectrum_speed_ratio':statistics.median(r['native']/r['jax'] for r in cases),
        'free_seconds':{r['object_id']:r['seconds'] for r in free},
        'all_15_comparisons_exact':True,
        'free_grid_points':sum(r['backend_report']['counts']['grid_calls'] for r in free),
        'scope':'Recorded fixed-z attempt time; one rotated observation per spectrum/backend under concurrent load. No paired free-z speed claim.'}
    output.mkdir(parents=True,exist_ok=False)
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    html = '''<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;font:14px var(--font-sans,system-ui);color:var(--foreground)}p{line-height:1.5}.muted{font-size:12px;color:var(--muted-foreground)}
    select{padding:6px;color:var(--foreground);background:var(--card);border:1px solid var(--border);border-radius:var(--radius);font:inherit}
    .chart{height:150px;margin:14px 0}.row{height:45px;display:grid;grid-template-columns:140px 1fr 70px;gap:10px;align-items:center}.track{height:20px;background:var(--secondary,ButtonFace)}.bar{height:20px;background:var(--chart-1,currentColor)}#numpy{background:var(--chart-2,currentColor)}#jax{background:var(--chart-3,currentColor)}.number{text-align:right;font:12px var(--font-mono,monospace)}
    .note{padding:16px;background:var(--card);border-radius:var(--radius);line-height:1.6}table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:7px;text-align:left;border-bottom:1px solid var(--border)}
    @media(max-width:450px){.row{grid-template-columns:110px 1fr 55px;gap:5px;font-size:12px}}
    </style></head><body><p><strong>Complete fixed-redshift fitting time</strong><br><span class="muted">Same five copied spectra · lower is faster · full extinction grid</span></p>
    <select id="select"><option value="all">Total across five spectra</option></select><div class="chart">
    <div class="row"><span>Native NGSF</span><div class="track"><div id="native" class="bar"></div></div><span id="nativevalue" class="number"></span></div>
    <div class="row"><span>Blocked NumPy</span><div class="track"><div id="numpy" class="bar"></div></div><span id="numpyvalue" class="number"></span></div>
    <div class="row"><span>Guarded JAX</span><div class="track"><div id="jax" class="bar"></div></div><span id="jaxvalue" class="number"></span></div></div>
    <p id="saving"></p><p class="muted">One rotated observation per spectrum and backend under concurrent load. Includes startup and runtime verification; excludes planning and final artifact hashing. These observations do not guarantee campaign throughput.</p>
    <p class="note">All ten fixed-z comparisons and five full free-z comparisons preserve native candidates, scores, CSVs, curves and masks exactly. JAX recomputes risky mixtures and candidate contenders with native NumPy.</p>
    <table><thead><tr><th>Full free-z fit</th><th>Guarded JAX time</th><th>Grid points</th></tr></thead><tbody id="free"></tbody></table>
    <p class="muted">Free-z timings have historical references only, so no speedup factor is inferred. SNID-SAGE remains on its native FFT backend.</p>
    <script>const data=__DATA__,el=id=>document.getElementById(id);data.fixed_cases.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=r.object_id;el('select').append(o)});
    function draw(){const r=el('select').value==='all'?data.fixed_totals:data.fixed_cases[+el('select').value],max=Math.max(r.native,r.numpy,r.jax);for(const k of ['native','numpy','jax']){el(k).style.width=(100*r[k]/max)+'%';el(k+'value').textContent=r[k].toFixed(1)+' s'}el('saving').textContent=`Native → JAX: ${(r.native-r.jax).toFixed(1)} s saved · ${(100*(1-r.jax/r.native)).toFixed(1)}% less time · ${(r.native/r.jax).toFixed(2)}× speed ratio.`}el('select').addEventListener('change',draw);draw();
    for(const [name,seconds] of Object.entries(data.free_seconds)){const tr=document.createElement('tr');for(const value of [name,seconds.toFixed(1)+' s','4,141']){const td=document.createElement('td');td.textContent=value;tr.append(td)}el('free').append(tr)}</script></body></html>'''
    (output/'comparison.html').write_text(html.replace('__DATA__',json.dumps(summary).replace('</','<\\/')))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    report(args.root,args.output)
