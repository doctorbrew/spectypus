#!/usr/bin/env python3
"""Prepare a separate Fritz batch under a recorded, provisional observer-frame assumption."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import shutil

from spectypus.io import file_hash, read_csv, read_json, write_csv, write_json

API_UNIT_SOURCE = 'https://github.com/skyportal/skyportal/blob/main/skyportal/models/spectrum.py'


def derive_ascii(raw, destination):
    """Extract complete finite API arrays; missing flux stays blocked, never imputed."""
    wave, flux = raw.get('wavelengths'), raw.get('fluxes')
    if not isinstance(wave, list) or not isinstance(flux, list) or len(wave) != len(flux) or len(wave) < 2:
        return 'missing, mismatched or empty wavelength/flux arrays'
    try:
        points = [(float(x), float(y)) for x, y in zip(wave, flux)]
    except (ValueError, TypeError):
        return 'missing or nonnumeric wavelength/flux samples'
    if any(not math.isfinite(x) or not math.isfinite(y) or x <= 0 for x,y in points):
        return 'nonfinite wavelength/flux samples; no rows removed'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(''.join(f'{x:.17g} {y:.17g}\n' for x,y in points))
    return ''


def inspect_metadata(raw):
    """Flag contradictions, not absence of non-existent API frame fields."""
    flags = []
    alt = raw.get('altdata') or {}
    if not isinstance(alt, dict): alt = {}
    for key, value in {**alt, **{k:v for k,v in raw.items() if k in ('wavelength_frame', 'wavelength_unit')}}.items():
        if isinstance(value, dict): value = value.get('value')
        key, value = str(key).lower(), str(value or '').strip().lower()
        if key in {'cunit1', 'wave_unit', 'wave_units', 'wavelength_unit'} and value in {'nm', 'nanometer', 'nanometers', 'micron', 'um', 'microns'}:
            flags.append(f'Original {key}={value} conflicts with API Angstrom contract')
        rest_label = key in {'frame', 'waveframe', 'wavelength_frame', 'specframe'} and value in {'rest', 'restframe', 'rest-frame'}
        rest_switch = key in {'restframe', 'rest_frame', 'restfram', 'restfr', 'restshift', 'deredshift'} and value in {'rest', 'restframe', 'rest-frame', 'true', 'yes', '1'}
        if rest_label or rest_switch:
            flags.append(f'Explicit possible rest-frame declaration: {key}={value}')
    original = raw.get('original_file_string')
    if isinstance(original, str):
        comments = '\n'.join(line for line in original.splitlines() if line.lstrip().startswith(('#', ';', '%')))
        if re.search(r'\brest[- _]?frame\b|\bde[-_ ]?redshift', comments, re.I):
            flags.append('Original header mentions rest frame or de-redshifting; inspect before fitting')
    return sorted(set(flags))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observer-assumption-note', required=True,
                        help='Exact provenance for treating otherwise unspecified Fritz arrays as observer-frame')
    args = parser.parse_args()
    previous, output = args.previous.resolve(), args.output.resolve()
    if output.exists(): parser.error('output already exists; keep prior evidence intact')
    rows = [r for r in read_csv(previous/'spectra.csv') if r['batch']=='fritz']
    if not rows: parser.error('no Fritz records')
    output.mkdir(parents=True)
    audit = []
    for row in rows:
        metadata_path = Path(row['source_metadata_path'])
        if file_hash(metadata_path) != row['source_metadata_sha256']:
            parser.error(f'Metadata changed for {row["spectrum_id"]}')
        raw = read_json(metadata_path)
        flags = inspect_metadata(raw)
        conversion = None
        if Path(row['path']).suffix.lower() == '.json':
            destination = output/'derived_inputs'/(row['spectrum_id'].replace(':','_')+'.dat')
            error = derive_ascii(raw, destination)
            conversion = {'source':str(metadata_path), 'reason':error}
            if not error:
                row['path'] = str(destination)
                conversion.update(derived=str(destination), derived_sha256=file_hash(destination))
        row.update(wavelength_frame='unknown' if flags else 'observer', wavelength_unit='angstrom',
                   frame_assumed='true', frame_source=args.observer_assumption_note,
                   frame_review_required='true', frame_review_flags=json.dumps(flags),
                   wavelength_unit_source=API_UNIT_SOURCE + ': Spectrum.wavelengths [Angstrom]; units refers to flux')
        audit.append({'spectrum_id':row['spectrum_id'], 'metadata_sha256':file_hash(metadata_path),
                      'flags':flags, 'frame_assumed':True, 'json_conversion':conversion})
    write_csv(output/'spectra.csv', rows, list(rows[0]))
    cfg = read_json(previous/'config.json')
    cfg['redshift_mode'] = 'both'
    if set(cfg['engines']) != {'ngsf','snid_sage'}: parser.error('previous config must contain both classifiers')
    write_json(output/'config.json', cfg)
    write_json(output/'frame_assumptions.json', {'schema':'spectypus-frame-assumption/1',
        'assumption':'observer', 'verification':'provisional, not individually confirmed',
        'user_statement':args.observer_assumption_note, 'api_unit_source':API_UNIT_SOURCE,
        'previous_campaign':str(previous), 'spectra':audit,
        'flagged_records':sum(bool(a['flags']) for a in audit),
        'policy':'Run unflagged inputs conditionally as observer-frame. Block explicit contradictions. No numerical frame-error probability assigned.'})
    # Freeze the current implementation, keeping the active older campaign untouched.
    runtime = output/'runtime'; runtime.mkdir()
    shutil.copytree(Path(__file__).resolve().parents[1]/'src/spectypus', runtime/'spectypus',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(Path(__file__).with_name('run_saved_campaign.py'),runtime/'run_saved_campaign.py')
    print(json.dumps({'records':len(rows), 'flagged':sum(bool(a['flags']) for a in audit),
                      'flag_reasons':dict(Counter(f for a in audit for f in a['flags']))}))


if __name__ == '__main__': main()
