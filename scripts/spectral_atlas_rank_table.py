"""Compact presentation of immutable native candidate rows and local source links."""
import html
import re
from pathlib import Path
from spectypus.phases import number


def matched_name(candidate):
    identity = candidate['template']
    name = identity.split('/')[1] if '/' in identity else re.split(r'_epoch_|_phase_', identity, maxsplit=1)[0]
    found = re.fullmatch(r'(?:sn)?((?:19|20)\d{2}[A-Za-z]+)', name, re.I)
    return 'SN' + found.group(1) if found else name


def compact_identity(candidate):
    kind = candidate.get('native_subtype') or candidate.get('native_class') or 'type unknown'
    phase = number(candidate.get('phase_days'))
    phase_text = f'{phase:+g}d' if phase is not None else 'phase unknown'
    return f'{matched_name(candidate)} ({kind}, {phase_text})'


def decimal_cell(value, places=3):
    numeric = number(value)
    if numeric is None:
        return '—'
    return f'<span title="{html.escape(str(value), quote=True)}">{numeric:.{places}f}</span>'


def template_cell(candidate, location=None):
    label = html.escape(compact_identity(candidate))
    title = f"Native template: {candidate['template']}; class: {candidate.get('native_class')}; subtype: {candidate.get('native_subtype') or 'none'}"
    if not location:
        return f'<span title="{html.escape(title, quote=True)}">{label}</span>'
    path = Path(location['path'])
    if not path.is_absolute():
        raise ValueError('Template location must be an absolute verified path')
    title += f"; file: {path}"
    if location.get('group'):
        title += f"; HDF5 group: {location['group']} (opens containing file)"
    return f'<a class="template-location" href="{html.escape(path.as_uri(), quote=True)}" title="{html.escape(title, quote=True)}" target="_blank" rel="noopener">{label}</a>'


def galaxy_cell(native):
    galaxy = native.get('GALAXY')
    if not galaxy:
        return '—'
    fraction = number(native.get('Frac(gal)'))
    label = f'{galaxy} ({fraction * 100:.0f}%)' if fraction is not None else f'{galaxy} (unknown)'
    title = f"Native galaxy flux fraction: {native.get('Frac(gal)', 'unknown')}"
    return f'<span title="{html.escape(title, quote=True)}">{html.escape(label)}</span>'
