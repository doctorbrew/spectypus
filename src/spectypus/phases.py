"""Explicit catalogue phase references, separate from immutable classifier results."""
from datetime import datetime, timezone
import math


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def references(row, provenance):
    out = []
    peak, field = number(row.get('peak_mjd')), 'peak_mjd'
    if peak is None:
        peak, field = number(row.get('source_peak_time')), 'source_peak_time'
        system = row.get('source_peak_time_system', '').lower()
        if peak is not None:
            if system == 'jd': peak -= 2400000.5
            elif system == 'bts_peakt': peak += 57999.5
            elif system != 'mjd': peak = None
    if peak is not None:
        out.append(dict(kind='maximum', mjd=peak, band=row.get('peak_band') or 'unspecified band',
                        source=provenance, field=field))
    discovery = number(row.get('discovery_mjd'))
    field = 'discovery_mjd'
    if discovery is None:
        field = 'discovery_date_ut'
        try:
            dt = datetime.fromisoformat(str(row.get(field, '')).replace('Z', '+00:00'))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            discovery = dt.timestamp() / 86400 + 40587
        except ValueError:
            pass
    if discovery is not None:
        out.append(dict(kind='discovery', mjd=discovery, band='', source=provenance, field=field))
    return out


def phase_context(source, refs=()):
    mjd, z = number(source.get('mjd')), number(source.get('redshift'))
    rows = []
    for ref in refs:
        delta = None if mjd is None else mjd - ref['mjd']
        rows.append({**ref, 'observer_days': delta,
                     'rest_days': delta / (1 + z) if delta is not None and z is not None and z > -1 else None})
    # Different bands can have distinct maxima; only flag conflicting dates within a reference group.
    for row in rows:
        peers = [r['mjd'] for r in rows if (r['kind'], r['band']) == (row['kind'], row['band'])]
        row['conflicting'] = max(peers) - min(peers) > 1 / 86400
    return {'mjd': mjd, 'redshift': z, 'references': rows,
            'note': 'Catalogue dates; no new light-curve fit. Discovery is not explosion time.'}
