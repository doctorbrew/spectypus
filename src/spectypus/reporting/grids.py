"""Compact six-match grids from saved evidence, using the project plot helper."""
import gzip
import json
from pathlib import Path
import re

# Retain the user's EFOSC spectrum palette alongside the canonical plot helper.
OBSERVED_COLOUR = '#000000'
MODEL_COLOUR = '#ef6666'
LABEL_SIZE = 22.
TICK_SIZE = RANK_SIZE = LABEL_SIZE
LEGEND_SIZE = LABEL_SIZE * .9
RANK_X = .07
LAYOUT = '3x2-matches-only'


def flux_label(source):
    from spectypus.fit_plots import tex
    unit = source.get('flux_unit')
    if unit == 'erg s^-1 cm^-2 Angstrom^-1':
        return r'Flux (erg s$^{-1}$ cm$^{-2}$ \AA$^{-1}$)'
    return tex(f'Flux ({unit or "input units"})')


def native_type_label(candidate):
    native = candidate.get('native_class') or 'type unknown'
    subtype = candidate.get('native_subtype')
    return f'{native} / {subtype}' if subtype and subtype != native else native


def legend_labels(request, candidate):
    from spectypus.phases import number
    source = request['source']
    phase = number(source.get('phase_rest_days'))
    return_target = None
    if number(source.get('discovery_mjd')) is not None and number(source.get('mjd')) is not None:
        delta = number(source['mjd']) - number(source['discovery_mjd'])
        return_target = f'{source["object_id"]}({delta:+.1f}d since discovery)'
    elif phase is not None:
        target_phase = f'{phase:+.1f} d rest'
    else:
        refs = request.get('phase_context', {}).get('references', [])
        peaks = {round(r['rest_days'], 6) for r in refs
                 if r['kind'] == 'maximum' and r.get('rest_days') is not None}
        target_phase = (f'{next(iter(peaks)):+.1f} d rest' if len(peaks) == 1
                        else 'phase ambiguous' if peaks else 'phase unknown')
    identity = candidate['template']
    found = re.search(r'(?:sn)?((?:19|20)\d{2}[A-Za-z]+)', identity, re.I)
    # NGSF encodes class/object/instrument; SAGE appends an epoch identifier.
    # Preserve named transients such as iPTF14atg and LSQ14mo without inventing
    # a different SN designation or repeating the template's path in the legend.
    fallback = identity.split('/')[1] if '/' in identity else re.split(r'_epoch_|_phase_', identity, maxsplit=1)[0]
    matched_name = 'SN' + found.group(1) if found else fallback
    template_phase = number(candidate.get('phase_days'))
    template_phase = f'{template_phase:+.1f} d' if template_phase is not None else 'phase unknown'
    if return_target is None:
        return_target = f'{source["object_id"]} ({target_phase})'
    return return_target, f'{matched_name} — {native_type_label(candidate)} ({template_phase})'


def smooth_observed(points, width=10.):
    """Display-only SG on finite contiguous support, including telluric regions.

    The full odd window spans at most `width` observer-frame Angstrom. Uniform
    working grids handle logarithmic sampling; return to the original sample
    positions afterwards. Never bridge native NaNs or large wavelength gaps.
    Segments too coarse/short for three samples retain their original fluxes.
    """
    import numpy as np
    from scipy.signal import savgol_filter
    data = np.asarray(points, dtype=float)
    x, y = data[:, 0], data[:, 1]
    if not np.all(np.isfinite(x)) or np.any(np.diff(x) <= 0):
        raise ValueError('Observed wavelengths must be finite and strictly increasing')
    if not np.isfinite(width) or width <= 0:
        raise ValueError('Smoothing width must be positive')
    finite = np.isfinite(y)
    steps = np.diff(x)
    spacing = np.median(steps) if len(steps) else width
    cuts = np.flatnonzero(~finite[1:] | ~finite[:-1] | (steps > 3 * spacing)) + 1
    smooth = y.copy()
    filtered = retained = 0
    for ids in np.split(np.arange(len(x)), cuts):
        ids = ids[finite[ids]]
        if not len(ids): continue
        if len(ids) < 3:
            retained += len(ids); continue
        grid = np.linspace(x[ids[0]], x[ids[-1]], len(ids))
        window = min(len(ids), int(np.floor(width / (grid[1] - grid[0]))) + 1)
        if window % 2 == 0: window -= 1
        if window < 3:
            retained += len(ids); continue
        values = np.interp(grid, x[ids], y[ids])
        # A quadratic on three samples is the identity; use a linear SG there.
        values = savgol_filter(values, window, min(2, window - 2), mode='interp')
        smooth[ids] = np.interp(x[ids], grid, values)
        filtered += len(ids)
    return np.column_stack((x, smooth)), {
        'savgol_width_angstrom': width, 'savgol_filtered_samples': filtered,
        'coarse_or_short_samples_retained': retained,
        'native_missing_samples': int(np.sum(~finite)),
        'telluric_samples_included': True, 'max_polynomial_order': 2,
        'savgol_edge_mode': 'interp', 'display_mask_applied': False}


def smoothed_limits(smoothed):
    """Expand finite smoothed extrema away from the spectrum by factor 1.1."""
    import numpy as np
    values = np.asarray(smoothed)[:, 1]
    values = values[np.isfinite(values)]
    if not len(values): raise ValueError('No finite observed flux for display limits')
    minimum, maximum = float(values.min()), float(values.max())
    lo = minimum * 1.1 if minimum < 0 else minimum / 1.1
    hi = maximum * 1.1 if maximum > 0 else maximum / 1.1
    if lo == hi:
        pad = max(abs(lo) * .1, 1e-6)
        lo -= pad; hi += pad
    return [lo, hi], {'smoothed_minimum': minimum, 'smoothed_maximum': maximum,
                      'stretch_factor': 1.1, 'limit_rule': 'outward-factor-1.1'}


def plot_saved_curves(ax, curve, labels=('Saved observed', 'Matched model'), smoothed=None, observed=None, model=None):
    """Show exact saved observations behind their 10-Angstrom SG display curve."""
    import numpy as np
    from spectypus.fit_plots import tex
    observed = np.asarray(curve['observed'] if observed is None else observed, dtype=float)
    model = np.asarray(curve['model'] if model is None else model, dtype=float)
    if smoothed is None: smoothed, _ = smooth_observed(observed)
    ax.plot(observed[:, 0], observed[:, 1], color='0.5', alpha=.2, lw=.75,
            label='_nolegend_', zorder=2)
    ax.plot(smoothed[:, 0], smoothed[:, 1], color=OBSERVED_COLOUR, lw=.85,
            label=tex(labels[0]), zorder=3)
    ax.plot(model[:, 0], model[:, 1], color=MODEL_COLOUR, lw=1.15,
            label=tex(labels[1]), zorder=4)
    return observed


def mark_telluric(ax, windows):
    for lo, hi in windows:
        ax.plot([lo, hi], [.98, .98], transform=ax.get_xaxis_transform(),
                color='0.65', lw=2, solid_capstyle='butt', zorder=1)


def create_figure(request):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from spectypus.fit_plots import tex
    from spectypus.plot_style import set_plotparams, styled_legend
    matches = request['matches'][:6]
    fig, grid = plt.subplots(3, 2, figsize=(15, 13.4), sharex=True, sharey=True)
    axes = list(grid.flat)
    support = [m['curve'] for m in matches if m['curve'].get('available')]
    if not support:
        plt.close(fig)
        raise ValueError('No saved curves for this match grid')
    from spectypus.reporting.display import input_points, model_input_flux
    observed = input_points(request)
    transform = request['display_transform']
    if transform['input_sha256'] != request['input_spectrum']['sha256']:
        raise ValueError('Display transform belongs to a different observed input')
    smoothed, smooth_info = smooth_observed(observed)
    from spectypus.reporting.limits import robust_limits
    limits, range_info = robust_limits(observed)
    xlimits = [float(observed[0, 0]), float(observed[-1, 0])]
    diagnostics = []
    for i, (ax, match) in enumerate(zip(axes, matches)):
        curve = match['curve']; rank = match['candidate']['rank']
        if not curve.get('available'):
            ax.set_axis_off()
            ax.text(.5, .5, f'Rank {rank}\nSaved model unavailable', transform=ax.transAxes,
                    ha='center', va='center', fontsize=11)
            diagnostics.append({'rank': rank, 'status': 'unavailable', 'reason': curve['reason']})
            continue
        labels = legend_labels(request, match['candidate'])
        model = model_input_flux(curve, transform)
        import numpy as np
        model_ids = np.flatnonzero(np.isfinite(model[:, 1]))
        if not len(model_ids):
            plt.close(fig)
            raise ValueError('Matched model has no finite display samples')
        internal_gaps = int(np.sum(~np.isfinite(model[model_ids[0]:model_ids[-1]+1, 1]))) if len(model_ids) else 0
        if internal_gaps:
            plt.close(fig)
            raise ValueError('Matched model has internal missing values; prepare verified unmasked models before rendering')
        plot_saved_curves(ax, curve, labels, smoothed, observed, model)
        finite_model = model[np.isfinite(model[:, 1]), 1]
        model_outside = int(np.sum((finite_model < limits[0]) | (finite_model > limits[1])))
        model_entirely_outside = bool(len(finite_model) and (np.min(finite_model) > limits[1] or np.max(finite_model) < limits[0]))
        if model_entirely_outside:
            ax.text(.03, .06, 'Saved model outside y-range', transform=ax.transAxes, fontsize=9,
                    bbox={'facecolor': 'white', 'alpha': .85, 'edgecolor': 'none'}, zorder=6)
        mark_telluric(ax, curve['features']['telluric_windows'])
        for line in curve['features']['host_lines']:
            ax.axvline(line['observed_angstrom'], color='0.6', lw=.5, ls=':', alpha=.6, zorder=1)
        ax.set_xlim(*xlimits); ax.set_ylim(*limits)
        # This project's helper uses the supplied point size without scaling.
        set_plotparams(ax, xticks=(1000, 250), yticks=None, tick_fs=TICK_SIZE)
        ax.xaxis.get_offset_text().set_fontsize(TICK_SIZE)
        ax.yaxis.get_offset_text().set_fontsize(TICK_SIZE)
        bottom = not any(j % 2 == i % 2 and j > i and matches[j]['curve'].get('available') for j in range(len(matches)))
        ax.tick_params(axis='x', which='both', labelbottom=bottom, labeltop=False)
        ax.tick_params(axis='y', which='both', labelleft=i % 2 == 0, labelright=False)
        ax.text(RANK_X, .93, f'Rank {rank}', transform=ax.transAxes, va='top', fontsize=RANK_SIZE)
        styled_legend(ax, loc='lower right', bbox_to_anchor=(1., 1.015), shadow=False,
                      fontsize=LEGEND_SIZE, handlelength=1.5, borderpad=.35, labelspacing=.25)
        info = {**smooth_info, **range_info, 'raw_observed_colour': '0.5', 'raw_observed_alpha': .2,
                'observed_source': 'full-staged-input', 'input_sha256': request['input_spectrum']['sha256'],
                'observed_samples': len(observed), 'observed_wavelength_range': xlimits,
                'model_display_transform': transform['kind'], 'model_samples_outside_limits': model_outside,
                'model_entirely_outside_limits': model_entirely_outside, 'model_mask_applied': False,
                'model_internal_missing_samples': internal_gaps, 'model_restored_samples': curve.get('display_model_provenance', {}).get('restored_samples', 0)}
        diagnostics.append({'rank': rank, 'status': 'rendered', 'limits': limits,
                            'legend_labels': list(labels), 'matched_native_type': native_type_label(match['candidate']), 'legend_location': 'above panel, right', 'legend_shadow': False,
                            'tick_label_points': TICK_SIZE,
                            'legend_points': LEGEND_SIZE, 'wavelength_major_tick_angstrom': 1000,
                            'rank_points': RANK_SIZE, 'rank_x_axes_fraction': RANK_X,
                            'x_ticklabels_visible': bottom, 'display_mask_applied': False, **info})
    for ax in axes[len(matches):]: ax.set_axis_off()
    source = request['source']
    engine = 'NGSF' if request['engine'] == 'ngsf' else 'SNID-SAGE'
    from spectypus.phases import number
    mjd = number(source.get('mjd'))
    date = f'{mjd:.3f}' if mjd is not None else 'unknown'
    fig.suptitle(tex(f'{source["object_id"]} / MJD {date} / {engine} / {request["mode"]}-z'), fontsize=20, y=.98)
    fig.supxlabel(r'Observer wavelength (\AA)', fontsize=LABEL_SIZE, y=.015)
    fig.supylabel(flux_label(source), fontsize=LABEL_SIZE, x=.025)
    fig.subplots_adjust(left=.085, right=.985, bottom=.07, top=.86, wspace=.06, hspace=.40)
    return fig, diagnostics


def render_matches(job):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from spectypus.reporting.products import save_jpg
    request_path, destination = map(Path, job)
    request = json.loads(gzip.decompress(request_path.read_bytes()))
    fig, diagnostics = create_figure(request)
    try:
        save_jpg(fig, destination)
    finally:
        plt.close(fig)
    return {'status': 'ready', 'jpg': destination.name + '.jpg',
            'panels': diagnostics, 'layout': LAYOUT, 'tick_label_points': TICK_SIZE,
            'legend_points': LEGEND_SIZE, 'wavelength_major_tick_angstrom': 1000,
            'axis_label_points': LABEL_SIZE, 'rank_points': RANK_SIZE, 'rank_x_axes_fraction': RANK_X,
            'y_label': flux_label(request['source']), 'flux_unit': request['source'].get('flux_unit'),
            'colours': {'observed': OBSERVED_COLOUR, 'model': MODEL_COLOUR}}
