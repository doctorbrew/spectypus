"""Small, batchable figures of verified saved fits; never invokes an engine."""
from pathlib import Path
import json
from spectral_atlas_products import save_jpg


def render_spectrum(job):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from spectypus.fit_plots import display_limits, tex
    from spectypus.plot_style import HIROSHIGE, set_plotparams, styled_legend

    path, destination = map(Path, job)
    request = json.loads(path.read_text())
    curves = request['curves']
    cols = min(2, len(curves))
    rows = (len(curves) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(6.4 * cols, 3.7 * rows), squeeze=False)
    diagnostics = []
    # Font sizes are display choices; the canonical SciencePlots/LaTeX style,
    # colors, axes, display-limit algorithm and 300-dpi JPG exports remain.
    for ax, curve in zip(axes.flat, curves):
        windows = curve['features']['telluric_windows']
        try:
            limits, info = display_limits(curve['observed'], windows)
            obs = np.asarray(curve['observed'], dtype=float).copy()
            model = np.asarray(curve['model'], dtype=float).copy()
            for values in (obs, model):
                for lo, hi in windows:
                    values[(values[:, 0] >= lo) & (values[:, 0] <= hi), 1] = np.nan
            ax.plot(obs[:, 0], obs[:, 1], color=HIROSHIGE(.05), lw=.8, label='Observed')
            ax.plot(model[:, 0], model[:, 1], color=HIROSHIGE(.85), lw=1.1, label='Matched model')
            for lo, hi in windows:
                ax.axvspan(lo, hi, color='goldenrod', alpha=.15)
            for line in curve['features']['host_lines']:
                ax.axvline(line['observed_angstrom'], color='xkcd:rose', lw=.5, ls=':', alpha=.7)
            ax.set_xlim(obs[0, 0], obs[-1, 0]); ax.set_ylim(*limits)
            set_plotparams(ax, xticks=(2000, 500), yticks=None, tick_fs=12)
            ax.set_xlabel(r'Observer wavelength (\AA)', fontsize=13)
            ax.set_ylabel('Normalized flux' if curve['engine'] == 'ngsf' else 'Continuum residual flux', fontsize=12)
            name = 'NGSF' if curve['engine'] == 'ngsf' else 'SNID-SAGE'
            ax.set_title(name + ' / ' + curve['mode'] + '-z / rank 1', fontsize=14)
            styled_legend(ax, loc='lower right', fontsize=9)
            diagnostics.append({'execution_id': curve['execution_id'], 'status': 'rendered', 'limits': limits, **info})
        except (ValueError, IndexError, KeyError) as exc:
            ax.set_axis_off()
            ax.text(.5, .5, 'Plot unavailable: insufficient or invalid support', ha='center', va='center', fontsize=10)
            diagnostics.append({'execution_id': curve['execution_id'], 'status': 'unavailable', 'reason': str(exc)})
    for ax in list(axes.flat)[len(curves):]:
        ax.set_axis_off()
    source = request.get('source', {})
    fig.suptitle(tex(f"{source.get('object_id', 'Spectrum')} / MJD {source.get('mjd') or 'unknown'}"), fontsize=16)
    fig.tight_layout(pad=1.3, rect=(0, 0, 1, .95))
    try:
        save_jpg(fig, destination)
    finally:
        plt.close(fig)
    return {'status': 'ready', 'jpg': destination.name + '.jpg', 'panels': diagnostics}
