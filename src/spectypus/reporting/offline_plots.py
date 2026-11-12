"""Pixel maps for extracting complete single matches from embedded master JPGs.

Only layout is measured; no new images or classifier/preprocessing products are
created. Browser exports copy pixels at their original 300-dpi scale.
"""
import gzip
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from ..io import digest, file_hash, read_json, write_json


def measure(job):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.transforms import Bbox
    from PIL import Image
    from .grids import create_figure, LAYOUT
    if job['layout'] != LAYOUT:
        raise ValueError('This master layout does not support offline single-match export')
    for path, checksum in [(job['request'], job['request_sha256']), (job['jpg'], job['jpg_sha256'])]:
        if file_hash(Path(path)) != checksum:
            raise ValueError('Master plot data changed before layout measurement')
    request = json.loads(gzip.decompress(Path(job['request']).read_bytes()))
    with Image.open(job['jpg']) as image:
        width, height = image.size
        if image.format != 'JPEG' or image.info.get('dpi') != (300, 300):
            raise ValueError('Expected a 300-dpi master JPG')
    fig, diagnostics = create_figure(request)
    try:
        fig.set_dpi(300)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        crop = fig.get_tightbbox(renderer).padded(float(plt.rcParams['savefig.pad_inches']))
        if abs(crop.width * 300 - width) > 1 or abs(crop.height * 300 - height) > 1:
            raise ValueError('Saved JPG dimensions disagree with the canonical layout')

        def rect(box, padding=3):
            x0 = math.floor(box.x0 - crop.x0 * 300) - padding
            y0 = math.floor(crop.y1 * 300 - box.y1) - padding
            x1 = math.ceil(box.x1 - crop.x0 * 300) + padding
            y1 = math.ceil(crop.y1 * 300 - box.y0) + padding
            if not 0 <= x0 < x1 <= width or not 0 <= y0 < y1 <= height:
                raise ValueError('Plot annotation falls outside the saved JPG')
            return [x0, y0, x1-x0, y1-y0]

        def text_rect(artist):
            return rect(artist.get_window_extent(renderer), 5)

        axes = [(ax, d) for ax, d in zip(fig.axes, diagnostics) if d['status'] == 'rendered']
        first = axes[0][0]
        if any(ax.get_xlim() != first.get_xlim() or ax.get_ylim() != first.get_ylim() for ax, _ in axes):
            raise ValueError('Single-match extraction requires shared master axes')
        xref = next(ax for ax, _ in axes if any(t.get_visible() for t in ax.get_xticklabels()))
        yref = next(ax for ax, _ in axes if any(t.get_visible() for t in ax.get_yticklabels()))

        def ticks(ax, axis):
            limits = ax.get_xlim() if axis == 'x' else ax.get_ylim()
            labels = ax.get_xticklabels() if axis == 'x' else ax.get_yticklabels()
            ticks = [t for t in labels if t.get_visible() and t.get_text()
                     and limits[0] <= t.get_position()[0 if axis == 'x' else 1] <= limits[1]]
            return [text_rect(t) for t in ticks]

        xticks, yticks = ticks(xref, 'x'), ticks(yref, 'y')
        xr, yr = rect(xref.bbox), rect(yref.bbox)
        offset = yref.yaxis.get_offset_text()
        if offset.get_visible() and offset.get_text():
            yticks.append(text_rect(offset))
        title, xlabel, ylabel = [text_rect(t) for t in (fig._suptitle, fig._supxlabel, fig._supylabel)]
        panels = []
        for ax, info in axes:
            plot, legend = rect(ax.bbox), rect(ax.get_legend().get_window_extent(renderer), 6)
            left = ylabel[2] + max(yr[0]-t[0] for t in yticks) + 45
            right = max(25, max(t[0]+t[2] - xr[0]-xr[2] for t in xticks) + 20)
            out_width = max(left+plot[2]+right, title[2]+40, legend[2]+left+right, xlabel[2]+40)
            left = out_width-right-plot[2]
            legend_y = title[3]+48
            top_gap = max(25, max(yr[1]-t[1] for t in yticks)+12)
            top = max(legend_y+legend[3]+top_gap, (ylabel[3]-plot[3])//2+24)
            tick_bottom = max(t[1]+t[3]-xr[1]-xr[3] for t in xticks)
            xlabel_y = top+plot[3]+tick_bottom+25
            out_height = max(xlabel_y+xlabel[3]+24, top+(plot[3]+ylabel[3])//2+24)
            pieces = []
            def piece(role, source, x, y):
                pieces.append({'role':role, 'source':source, 'at':[int(x), int(y)]})
            piece('title', title, (out_width-title[2])//2, 20)
            piece('legend', legend, left+plot[2]-legend[2], legend_y)
            piece('plot', plot, left, top)
            for t in xticks:
                piece('x_tick', t, left+t[0]-xr[0], top+plot[3]+t[1]-xr[1]-xr[3])
            for t in yticks:
                piece('y_tick', t, left+t[0]-yr[0], top+t[1]-yr[1])
            piece('x_label', xlabel, left+(plot[2]-xlabel[2])//2, xlabel_y)
            piece('y_label', ylabel, 20, top+(plot[3]-ylabel[3])//2)
            for p in pieces:
                x, y = p['at']; w, h = p['source'][2:]
                if not 0 <= x < x+w <= out_width or not 0 <= y < y+h <= out_height:
                    raise ValueError('Single-match annotation would be clipped')
            panels.append({'rank':info['rank'], 'width':out_width, 'height':out_height, 'pieces':pieces})
        return {'status':'ready', 'schema':'spectypus-panel-map/1', 'dpi':300,
                'width':width, 'height':height, 'jpg_sha256':job['jpg_sha256'], 'panels':panels}
    finally:
        plt.close(fig)


def ensure_map(output, figure):
    """Cache lightweight crop coordinates separately from existing master products."""
    try:
        if figure.get('layout') != '3x2-matches-only':
            raise ValueError('Offline extraction needs a current three-row master grid')
        folder = Path(figure['directory'])
        jpg, request = folder / figure['jpg'], folder / 'request.json.gz'
        jpg_hash = file_hash(jpg)
        if jpg_hash != figure['product_hashes']['jpg'] or file_hash(request) != figure['request_sha256']:
            raise ValueError('Master plot failed verification')
        root = Path(__file__).parent
        identity = digest({'jpg':jpg_hash, 'request':figure['request_sha256'],
                           'map_code':file_hash(Path(__file__)), 'renderer':file_hash(root / 'grids.py')})
        directory = Path(output) / '.selected-plots' / 'maps' / identity
        target = directory / 'map.json'
        checksum = directory / 'map.sha256'
        if target.is_file() and checksum.is_file() and file_hash(target) == checksum.read_text().strip():
            return read_json(target)
        directory.mkdir(parents=True, exist_ok=True)
        job = {'jpg':str(jpg), 'jpg_sha256':jpg_hash, 'request':str(request),
               'request_sha256':figure['request_sha256'], 'layout':figure['layout'], 'result':str(target)}
        write_json(directory / 'job.json', job)
        env = {**os.environ, 'MPLBACKEND':'Agg', 'PYTHONDONTWRITEBYTECODE':'1',
               'MPLCONFIGDIR':str(Path(output) / '.plot-cache' / 'matplotlib'),
               'XDG_CACHE_HOME':str(Path(output) / '.plot-cache' / 'xdg')}
        code = 'import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("spectypus.reporting.offline_plots",run_name="__main__")'
        with (directory / 'layout.log').open('w') as stream:
            process = subprocess.run([os.environ.get('SPECTYPUS_PLOT_PYTHON', sys.executable), '-c', code,
                                      str(root.parents[1]), str(directory / 'job.json')],
                                     env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=300)
        if process.returncode:
            raise ValueError(f'Offline plot layout unavailable; see {directory / "layout.log"}')
        checksum.write_text(file_hash(target) + '\n')
        return read_json(target)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        return {'status':'unavailable', 'reason':str(exc)}


if __name__ == '__main__':
    job = read_json(Path(sys.argv[1]))
    write_json(Path(job['result']), measure(job))
