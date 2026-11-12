"""Sourced display metadata; never changes a saved fit's inputs or redshift."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from ..io import digest, file_hash, read_json, write_json
from ..phases import number


def tns_name(name):
    match = re.fullmatch(r'(?:AT|SN)?\s*((?:19|20)\d{2}[a-z]+)', str(name), re.I)
    return match.group(1).lower() if match else None


def mjd_from_utc(value):
    stamp = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp() / 86400 + 40587


def discovery_fields(payload, expected):
    if payload.get('id_code') != 200:
        raise ValueError('TNS did not return a successful object response')
    obj = payload['data']
    obj = obj.get('reply', obj)
    if obj.get('objname', '').lower() != expected:
        raise ValueError('TNS object identity differs from requested name')
    fields = {'tns_url': 'https://www.wis-tns.org/object/' + expected}
    if obj.get('discoverydate'):
        fields.update(discovery_date_ut=obj['discoverydate'], discovery_mjd=mjd_from_utc(obj['discoverydate']),
                      discovery_source=fields['tns_url'])
    survey = obj.get('discovery_data_source') or {}
    if isinstance(survey, dict) and survey.get('group_name'):
        fields['discovery_survey'] = survey['group_name']
    # TNS object redshift is not automatically a host measurement.
    if obj.get('hostname'):
        fields['host_name'] = obj['hostname']
        fields['host_source'] = fields['tns_url']
        if number(obj.get('host_redshift')) is not None:
            fields['host_redshift'] = number(obj['host_redshift'])
    return fields


def cached_tns(output):
    index = Path(output) / 'metadata' / 'tns.json'
    if not index.exists():
        return {}
    payload = read_json(index)
    if payload.get('schema') != 'spectypus-tns-cache/1':
        raise ValueError('Unknown TNS cache schema')
    result = {}
    for name, receipt in payload['objects'].items():
        path = (index.parent / receipt['file']).resolve()
        if not path.is_relative_to(index.parent.resolve()) or file_hash(path) != receipt['sha256']:
            raise ValueError('TNS cached response integrity check failed')
        result[name] = {**discovery_fields(read_json(path), name), 'tns_response_sha256': receipt['sha256'],
                        'tns_fetched_at': receipt['fetched_at']}
    return result


def fetch_tns(output, sources, *, refresh=False, opener=urllib.request.urlopen):
    """Fetch exact named objects once using the user's bot; preserve response bytes.

    Credentials are read only from the environment and never stored in results.
    Missing credentials/network failures leave the classification report usable.
    Caller holds the output lock. Normal report refreshes use cached data only.
    """
    cached = cached_tns(output)
    names = sorted({tns_name(s.get('tns_name') or s['object_id']) for s in sources} - {None})
    needed = [n for n in names if refresh or n not in cached]
    result = {'fetched': 0, 'cached': len(names) - len(needed), 'errors': []}
    if not needed:
        return result
    keys = ('TNS_API_KEY', 'TNS_BOT_ID', 'TNS_BOT_NAME')
    if not all(os.environ.get(k) for k in keys):
        return {**result, 'status': 'unconfigured'}
    marker = {'tns_id': int(os.environ['TNS_BOT_ID']), 'type': 'bot', 'name': os.environ['TNS_BOT_NAME']}
    index = Path(output) / 'metadata' / 'tns.json'
    cache = read_json(index) if index.exists() else {'schema': 'spectypus-tns-cache/1', 'objects': {}}
    for name in needed:
        data = urllib.parse.urlencode({'api_key': os.environ['TNS_API_KEY'], 'data': json.dumps(
            {'objname': name, 'photometry': '0', 'spectra': '0'})}).encode()
        request = urllib.request.Request('https://www.wis-tns.org/api/get/object', data=data,
                                         headers={'User-Agent': 'tns_marker' + json.dumps(marker)})
        try:
            with opener(request, timeout=30) as response:
                payload = json.load(response)
            discovery_fields(payload, name)
            path = index.parent / 'tns' / (name + '-' + digest(payload)[:16] + '.json')
            if not path.exists():
                write_json(path, payload)
            cache['objects'][name] = {'file': str(path.relative_to(index.parent)), 'sha256': file_hash(path),
                                      'fetched_at': datetime.now(timezone.utc).isoformat()}
            write_json(index, cache)
            result['fetched'] += 1
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Never print a request/body, which contains the API credential.
            result['errors'].append({'object': name, 'error': type(exc).__name__,
                                     'http_status': getattr(exc, 'code', None)})
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403, 429):
                break
    return result


def display_sources(output, sources):
    from ..efosc import FLUX_UNIT, UNIT_SOURCE, typing_metadata
    metadata = cached_tns(output)
    reductions = {}
    result = []
    for source in sources:
        extra = metadata.get(tns_name(source.get('tns_name') or source['object_id']), {})
        # Explicit reduction/reviewer metadata takes precedence over TNS hosts.
        row = {**extra, **source}
        # Legacy plans already identify this physical-flux export contract.
        # Enrich display metadata without modifying their immutable fit inputs.
        if not row.get('flux_unit') and source.get('unit_source') == UNIT_SOURCE:
            row.update(flux_unit=FLUX_UNIT,
                       flux_unit_source='EFOSpec native_raw_calibration_daily_standards export contract')
        if source.get('efosc_manifest'):
            key = (source['efosc_manifest'], source['efosc_manifest_sha256'])
            if key not in reductions:
                reductions[key] = typing_metadata(Path(key[0]), key[1])
            fields = reductions[key].get(source['path'], {})
            if fields and fields['object_id'] != source['object_id']:
                raise ValueError('EFOSpec typing metadata object identity mismatch')
            # Updated display metadata may describe the host, but the redshift
            # supplied to a completed fit must retain its original value.
            row.update({k: v for k, v in fields.items() if k not in {'redshift', 'redshift_source', 'redshift_kind'}})
        for field in ('discovery_mjd', 'discovery_date_ut', 'discovery_source', 'discovery_survey'):
            if extra.get(field) is not None:
                row[field] = extra[field]
        result.append(row)
    return result
