"""Small, dependency-free HTML primitives shared by the two displays."""
import base64
import hashlib
from html import escape
from pathlib import Path

ASSETS = Path(__file__).parent / 'assets'
BAD = {'failed', 'blocked', 'invalid_evidence', 'unavailable'}


def h(value):
    return escape('unknown' if value is None or value == '' else str(value), quote=True)


def table(headers, rows):
    return '<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th scope="col">{h(c)}</th>' for c in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def badge(state):
    return f'<span class="badge {"bad" if state in BAD else ""}">{h(state.replace("_", " "))}</span>'


def data_uri(data, mime):
    return f'data:{mime};base64,' + base64.b64encode(data).decode()


def download_bytes(data, filename, label, mime='application/json'):
    checksum = hashlib.sha256(data).hexdigest()
    return f'<a download="{h(filename)}" data-sha256="{checksum}" href="{data_uri(data, mime)}">{h(label)}</a>'


def page(title, body, stamp=None, back='', *, display='SpectralAtlas', extra_css=''):
    css = (ASSETS / 'atlas.css').read_text() + extra_css
    js = (ASSETS / 'atlas.js').read_text()
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{h(title)} · {h(display)}</title><style>{css}</style></head>
<body><main><header><a class="brand" href="{h(back or '#top')}">Spectypus <span>/ {h(display)}</span></a></header>
<div id="top"><h1>{h(title)}</h1></div>{body}
</main>
<dialog aria-label="Enlarged spectrum figure"><button type="button" class="close">Close figure</button><button type="button" class="zoom" aria-pressed="false">Zoom to full resolution</button><img alt=""><p></p></dialog><script>{js}</script></body></html>'''
