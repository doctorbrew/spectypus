"""Batch Matplotlib figures from verified saved curves; never runs a classifier."""
from pathlib import Path
import json
import math
import re
from .io import write_json


def display_limits(points, windows=(), width=50.):
    """Display-only SG smoothing in Angstrom; never alters plotted/native arrays.

    Exclude isolated spikes using a three-point median/MAD check before SG,
    and exclude filter-edge and unsupported short/coarse segments from extrema.
    No interpolation across telluric masks, NaNs or large wavelength gaps.
    """
    import numpy as np
    from scipy.signal import savgol_filter
    if not math.isfinite(width) or not 25 <= width <= 50:
        raise ValueError('Display smoothing width must be 25–50 Angstrom')
    data = np.asarray(points, dtype=float)
    x, y = data[:, 0], data[:, 1]
    valid = np.isfinite(x) & np.isfinite(y)
    for lo, hi in windows: valid &= ~((x >= lo) & (x <= hi))
    steps = np.diff(x)
    if np.any(steps <= 0): raise ValueError('Plot wavelengths must increase strictly')
    spacing = np.median(steps) if len(steps) else width
    cuts = np.flatnonzero((~valid[1:]) | (~valid[:-1]) | (steps > 3 * spacing)) + 1
    smoothed, excluded, spikes = [], 0, 0
    for ids in np.split(np.arange(len(x)), cuts):
        ids = ids[valid[ids]]
        if not len(ids): continue
        if len(ids) < 3:
            excluded += len(ids); continue
        grid = np.linspace(x[ids[0]], x[ids[-1]], len(ids))
        dx = grid[1] - grid[0]
        n = min(len(ids), int(math.floor(width / dx)) + 1)
        if n % 2 == 0: n -= 1
        if n < 3:
            excluded += len(ids); continue
        values = np.interp(grid, x[ids], y[ids])
        left = np.r_[values[1], values[:-1]]
        right = np.r_[values[1:], values[-2]]
        local = np.median(np.stack([left, values, right]), axis=0)
        residual = values - local
        scale = 1.4826 * np.median(np.abs(residual - np.median(residual)))
        floor = np.finfo(float).eps * max(1., float(np.max(np.abs(values)))) * 100
        bad = np.abs(residual) > 6 * max(scale, floor)
        # Limit suppression to isolated one/two-bin excursions; preserve broad features.
        for group in np.split(np.flatnonzero(bad), np.flatnonzero(np.diff(np.flatnonzero(bad)) > 1) + 1):
            if len(group) <= 2:
                values[group] = local[group]; spikes += len(group)
        # A quadratic through three samples is the identity, not smoothing.
        order = min(2, n - 2)
        smooth = savgol_filter(values, n, order, mode='mirror')
        half = n // 2
        smoothed.extend(smooth[half:-half])
        excluded += 2 * half
    if not smoothed: raise ValueError('Insufficient wavelength support for 25–50 Angstrom smoothing; no raw-spike limit fallback')
    minimum, maximum = float(np.min(smoothed)), float(np.max(smoothed))
    # Stretch away from zero on both sides; positive minima move downward.
    lo = minimum * 1.1 if minimum < 0 else minimum / 1.1
    hi = maximum * 1.1 if maximum > 0 else maximum / 1.1
    degenerate = lo == hi
    if degenerate:
        pad = max(abs(lo) * .05, 1e-6); lo -= pad; hi += pad
    return [lo, hi], {'savgol_width_angstrom': width, 'max_polynomial_order': 2,
                     'isolated_spikes_replaced_for_limits': spikes,
                     'edge_or_unsupported_samples_excluded_from_limits': excluded,
                     'stretch_factor': 1.1, 'constant_range_padded': degenerate,
                     'observed_samples_outside_limits': int(np.sum(valid & ((y < lo) | (y > hi))))}


def figure_title(object_name, context, engine, mode):
    name = {'ngsf': 'NGSF', 'snid_sage': 'SNID-SAGE'}.get(engine, engine)
    mjd = context.get('mjd')
    mjd = 'unknown' if mjd is None else f'{mjd:.2f}'.rstrip('0').rstrip('.')
    title = f'{object_name} - MJD {mjd} - {name} ({"Fixed" if mode == "fixed" else "Free"}-z)'
    if mode == 'fixed':
        z = context.get('redshift')
        title += f' (z={z:g})' if z is not None else ' (z=unknown)'
    return title


def match_label(candidate):
    matched = re.search(r'(?:sn)?((?:19|20)\d{2}[A-Za-z]+)', candidate['template'], re.I)
    name = 'SN' + matched.group(1) if matched else candidate['template'].split('/')[1] if '/' in candidate['template'] else candidate['template']
    phase = candidate['phase_days']
    return f'{name} : {phase:+.1f} d' if phase is not None else f'{name} : phase unknown'


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
        set_plotparams(ax, xticks=(1000, 200), yticks=None, tick_fs=27)
        ax.set_xlabel(r'Observer wavelength (\AA)')
        ax.set_ylabel('Normalized flux' if engine == 'ngsf' else 'Continuum residual flux')
        candidate = curve['candidate']
        ax.text(.97, .95, tex(match_label(candidate)), transform=ax.transAxes,
                ha='right', va='top', fontsize=20,
                bbox=dict(boxstyle='round,pad=.4', facecolor='white', edgecolor='0.7', alpha=.9))
        if not compact:
            styled_legend(ax, loc='lower right')
        return candidate
    stamp = figure_title(object_name, context, engine, mode)
    for curve in curves:
        fig, ax = plt.subplots(figsize=(14, 8))
        candidate = panel(ax, curve)
        ax.set_title(tex(stamp), fontsize=20, pad=18)
        fig.subplots_adjust(top=.88, bottom=.16, left=.12, right=.97)
        stem = f'FitSpectrum_{safe}_{engine}_{mode}_rank{curve["rank"]:02d}'
        savefig_light(fig, directory / stem); plt.close(fig)
        exports.append({'rank': curve['rank'], 'jpg': stem + '.jpg', 'pdf': stem + '.pdf'})
    cols, rows = 2, math.ceil(len(curves) / 2)
    fig, axes = plt.subplots(rows, cols, figsize=(22, 5.2 * rows), squeeze=False)
    for ax, curve in zip(axes.flat, curves): panel(ax, curve, compact=True)
    for ax in list(axes.flat)[len(curves):]: ax.set_visible(False)
    fig.suptitle(tex(stamp), fontsize=22, y=1.01)
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.5, .985), ncol=2)
    fig.tight_layout(h_pad=2.5, w_pad=2)
    stem = f'FitSpectrum_{safe}_{engine}_{mode}_top10'
    savefig_light(fig, directory / stem); plt.close(fig)
    write_json(directory / 'gallery.json', {'status': 'ready', 'collage': {'jpg': stem+'.jpg', 'pdf': stem+'.pdf'},
        'plots': exports, 'limits': limits, 'limits_info': limits_info, 'phase_context': context})


if __name__ == '__main__':
    import sys
    render(sys.argv[1], sys.argv[2])
