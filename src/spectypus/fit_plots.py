"""Batch Matplotlib figures from verified saved curves; never runs a classifier."""
from pathlib import Path
import json
import math
import re
import textwrap
from .io import write_json


def display_limits(points, windows=(), width=25.):
    """SG polynomial order 2 on contiguous, uniformly resampled wavelength segments.

    Resampling/smoothing is used ONLY to determine limits. Never bridge a mask,
    missing sample or a wavelength gap >3 median spacings. Coarse/short segments
    that cannot support three points in 25 Angstrom retain their original flux.
    """
    import numpy as np
    from scipy.signal import savgol_filter
    data = np.asarray(points, dtype=float)
    x, y = data[:, 0], data[:, 1]
    valid = np.isfinite(x) & np.isfinite(y)
    for lo, hi in windows: valid &= ~((x >= lo) & (x <= hi))
    steps = np.diff(x)
    if np.any(steps <= 0): raise ValueError('Plot wavelengths must increase strictly')
    spacing = np.median(steps) if len(steps) else width
    cuts = np.flatnonzero((~valid[1:]) | (~valid[:-1]) | (steps > 3 * spacing)) + 1
    smoothed, unchanged = [], 0
    for ids in np.split(np.arange(len(x)), cuts):
        ids = ids[valid[ids]]
        if not len(ids): continue
        if len(ids) < 3:
            smoothed.extend(y[ids]); unchanged += 1; continue
        grid = np.linspace(x[ids[0]], x[ids[-1]], len(ids))
        dx = grid[1] - grid[0]
        n = min(len(ids), int(math.floor(width / dx)) + 1)
        if n % 2 == 0: n -= 1
        if n < 3:
            smoothed.extend(y[ids]); unchanged += 1; continue
        smoothed.extend(savgol_filter(np.interp(grid, x[ids], y[ids]), n, 2, mode='interp'))
    if not smoothed: raise ValueError('No usable spectrum samples for axis limits')
    lo, hi = 1.25 * float(np.min(smoothed)), 1.25 * float(np.max(smoothed))
    degenerate = lo == hi
    if degenerate:
        pad = max(abs(lo) * .05, 1e-6); lo -= pad; hi += pad
    return [lo, hi], {'savgol_width_angstrom': width, 'polynomial_order': 2,
                     'unsmoothed_segments': unchanged, 'constant_range_padded': degenerate,
                     'observed_samples_outside_limits': int(np.sum(valid & ((y < lo) | (y > hi))))}


def tex(value):
    replacements = {'\\': r'\textbackslash{}', '_': r'\_', '%': r'\%', '&': r'\&',
                    '#': r'\#', '$': r'\$', '{': r'\{', '}': r'\}', '^': r'\textasciicircum{}', '~': r'\textasciitilde{}'}
    return ''.join(replacements.get(c, c) for c in str(value)).replace('Å', r'\AA{}')


def phase_lines(context):
    rows = context.get('references', [])
    if not rows: return ['Target phase: unknown (no maximum/discovery reference)']
    groups = {}
    for row in rows:
        key = (row['kind'], row['band'], row['mjd'])
        groups.setdefault(key, []).append(row)
    lines = []
    for (kind, band, mjd), refs in groups.items():
        row = refs[0]; phase = row['rest_days']; frame = 'rest'
        if phase is None: phase, frame = row['observer_days'], 'observer'
        delta = 'unknown' if phase is None else f'{phase:+.1f} d ({frame})'
        sources = ', '.join(sorted({Path(r['source']).parent.name for r in refs}))
        conflict = '; conflicting catalogue dates' if any(r['conflicting'] for r in refs) else ''
        lines.append(f'Target: {delta} from {band + " " if band else ""}{kind} MJD {mjd:.2f} [{sources}{conflict}]')
    return lines


def render(request_path, directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from spectypus.plot_style import set_plotparams, styled_legend, savefig_light, HIROSHIGE
    request = json.loads(Path(request_path).read_text())
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    curves = request['curves']; source = request['source']
    context = request['phase_context']
    phase_text = phase_lines(context)
    object_name = source['object_id']
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', object_name)
    engine = request['engine']; mode = request['mode']
    limits, limits_info = display_limits(curves[0]['observed'], curves[0]['features']['telluric_windows'])
    exports = []
    def panel(ax, curve, compact=False):
        obs, model = np.array(curve['observed'], float), np.array(curve['model'], float)
        for array in (obs, model):
            for lo, hi in curve['features']['telluric_windows']:
                array[(array[:, 0] >= lo) & (array[:, 0] <= hi), 1] = np.nan
        ax.plot(obs[:, 0], obs[:, 1], color=HIROSHIGE(.05), lw=1.2, label=tex(object_name), zorder=3)
        ax.plot(model[:, 0], model[:, 1], color=HIROSHIGE(.85), lw=1.8, label='Matched model', zorder=4)
        for lo, hi in curve['features']['telluric_windows']: ax.axvspan(lo, hi, color='goldenrod', alpha=.15)
        for line in curve['features']['host_lines']:
            ax.axvline(line['observed_angstrom'], color='xkcd:rose', lw=.6, ls=':', alpha=.7)
        ax.set_xlim(obs[0, 0], obs[-1, 0]); ax.set_ylim(*limits)
        set_plotparams(ax, xticks=(1000, 200), yticks=None)
        ax.set_xlabel(r'Observer wavelength (\AA)')
        ax.set_ylabel('Normalized flux' if engine == 'ngsf' else 'Continuum residual flux')
        candidate = curve['candidate']
        phase = candidate['phase_days']
        phase = 'unknown' if phase is None else f'{phase:+.1f} d'
        matched = re.search(r'(?:sn)?((?:19|20)\d{2}[A-Za-z]+)', candidate['template'], re.I)
        name = 'SN' + matched.group(1) if matched else candidate['template'].split('/')[1] if '/' in candidate['template'] else candidate['template']
        ax.set_title(tex(f"#{curve['rank']} {name} | template phase {phase}"), pad=14)
        if not compact:
            styled_legend(ax, loc='upper center', bbox_to_anchor=(.5, 1.02), ncol=2)
        return candidate
    stamp = f'{object_name} | {engine} {mode}-z | observed MJD {context.get("mjd")} | supplied z {context.get("redshift")}'
    notes = '25 Angstrom SG smoothing sets limits only; curves unchanged. Gold: telluric masks; pink: expected host lines.'
    notes += f' {limits_info["observed_samples_outside_limits"]} spectrum samples outside displayed y limits.'
    if limits_info['unsmoothed_segments']: notes += f' {limits_info["unsmoothed_segments"]} short/coarse segments unsmoothed.'
    notes += ' Template phases retain the native library reference; do not assume they share the target reference.'
    for curve in curves:
        fig, ax = plt.subplots(figsize=(14, 8))
        candidate = panel(ax, curve)
        fig.suptitle(tex(stamp), fontsize=18)
        detail = [f"Template: {candidate['template']}",
                  f"{candidate['native_class']} | {candidate['metric']} = {candidate['score']:.4g} | fit z = {candidate['redshift']} | {'accepted candidate' if candidate.get('qualified') else 'candidate not accepted'}"]
        footer = '\n'.join(textwrap.fill(line, 125) for line in phase_text + detail + [notes])
        fig.text(.1, -.02, tex(footer), ha='left', va='top', fontsize=12)
        fig.subplots_adjust(top=.82, bottom=.16, left=.1, right=.97)
        stem = f'FitSpectrum_{safe}_{engine}_{mode}_rank{curve["rank"]:02d}'
        savefig_light(fig, directory / stem); plt.close(fig)
        exports.append({'rank': curve['rank'], 'jpg': stem + '.jpg', 'pdf': stem + '.pdf'})
    cols, rows = 2, math.ceil(len(curves) / 2)
    fig, axes = plt.subplots(rows, cols, figsize=(22, 5.2 * rows), squeeze=False)
    for ax, curve in zip(axes.flat, curves): panel(ax, curve, compact=True)
    for ax in list(axes.flat)[len(curves):]: ax.set_visible(False)
    fig.suptitle(tex(stamp + '\nTop saved matches'), fontsize=22, y=1.01)
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.5, .985), ncol=2)
    fig.tight_layout(h_pad=2.5, w_pad=2)
    fig.text(.04, -.01, tex('\n'.join(phase_text + [textwrap.fill(notes, 160)])), fontsize=14, va='top')
    stem = f'FitSpectrum_{safe}_{engine}_{mode}_top10'
    savefig_light(fig, directory / stem); plt.close(fig)
    write_json(directory / 'gallery.json', {'status': 'ready', 'collage': {'jpg': stem+'.jpg', 'pdf': stem+'.pdf'},
        'plots': exports, 'limits': limits, 'limits_info': limits_info, 'phase_context': context})


if __name__ == '__main__':
    import sys
    render(sys.argv[1], sys.argv[2])
