"""Full staged observations and verified, reversible model display conversions.

No template search, new redshift fit, or saved-result modification is performed.
SNID preprocessing is replayed solely to recover the continuum/offset; its
apodized observations must reproduce the saved result before using the continuum.
"""
import argparse
from functools import lru_cache
import hashlib
import io
import json
import logging
from pathlib import Path
import numpy as np


def input_points(request):
    raw = request['input_spectrum']
    if not raw.get('available'):
        raise ValueError('Full staged observed spectrum unavailable')
    if hashlib.sha256(raw['contents'].encode()).hexdigest() != raw['sha256']:
        raise ValueError('Full observed input hash mismatch')
    data = np.loadtxt(io.StringIO(raw['contents']), ndmin=2)[:, :2]
    if len(data) < 2 or not np.all(np.isfinite(data[:, 0])) or np.any(np.diff(data[:, 0]) <= 0):
        raise ValueError('Full observed wavelengths must be finite and strictly increasing')
    return data


def sage_options(command):
    # The bridge separates its own flags from the native CLI with '--'.
    if '--' in command: command = command[command.index('--') + 1:]
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--profile', dest='profile_id', default='optical')
    parser.add_argument('--no-spike-masking', dest='spike_masking', action='store_false')
    for flag, default, cast in [('spike-floor-z', 50., float), ('spike-baseline-window', 501, int),
                              ('spike-baseline-width', None, float), ('spike-rel-edge-ratio', 2., float),
                              ('spike-min-separation', 2, int), ('spike-max-removals', None, int),
                              ('spike-min-abs-resid', None, float), ('savgol-window', 0, int),
                              ('savgol-order', 3, int), ('emclip-z', -1., float),
                              ('emwidth', 40., float), ('apodize-percent', 10., float)]:
        parser.add_argument('--' + flag, default=default, type=cast)
    for flag in ('aband-remove', 'skyclip', 'emclip'):
        parser.add_argument('--' + flag, action='store_true')
    parser.add_argument('--forced-redshift', type=float)
    parser.add_argument('--wavelength-masks', nargs='*', default=[])
    options = vars(parser.parse_known_args(command)[0])
    forced = options.pop('forced_redshift')
    if options.pop('emclip') and options['emclip_z'] < 0 and forced is not None:
        options['emclip_z'] = forced
    options['wavelength_masks'] = [list(map(float, s.split(':'))) for s in options['wavelength_masks']]
    return options


@lru_cache(maxsize=8)
def _sage_replay(contents, options_json):
    from snid_sage.snid.snid import preprocess_spectrum
    data = np.loadtxt(io.StringIO(contents), ndmin=2)
    logger = logging.getLogger('snid_sage.snid.pipeline')
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        return preprocess_spectrum(input_spectrum=(data[:, 0], data[:, 1]), **json.loads(options_json))
    finally:
        logger.setLevel(previous)


def make_transform(request, run):
    raw = input_points(request)
    support = [m['curve'] for m in request['matches'] if m['curve'].get('available')]
    if not support: return None
    first = np.asarray(support[0]['observed'], float)
    for curve in support[1:]:
        if not np.array_equal(first, np.asarray(curve['observed'], float), equal_nan=True):
            raise ValueError('Candidates have differing observed preprocessing')
    base = {'input_sha256': request['input_spectrum']['sha256'], 'observed_source': 'full-staged-input'}
    if request['engine'] == 'ngsf':
        projected = np.interp(first[:, 0], raw[:, 0], raw[:, 1], left=np.nan, right=np.nan)
        good = np.isfinite(projected) & np.isfinite(first[:, 1]) & (abs(first[:, 1]) > 1e-12)
        if good.sum() < 3: raise ValueError('Insufficient NGSF support to verify flux normalization')
        scale = float(np.median(projected[good] / first[good, 1]))
        if not np.isfinite(scale) or scale == 0 or not np.allclose(projected[good] / scale, first[good, 1], rtol=2e-6, atol=1e-8):
            raise ValueError('NGSF normalization does not reproduce the saved observations')
        return {**base, 'kind': 'ngsf-scale', 'scale': scale,
                'verification_max_absolute_error': float(np.max(abs(projected[good] / scale - first[good, 1])))}
    record_path = Path(run['attempt_path']) / 'record.json'
    if hashlib.sha256(record_path.read_bytes()).hexdigest() != run['record_sha256']:
        raise ValueError('SNID record changed before continuum replay')
    options = sage_options(json.loads(record_path.read_text())['command'])
    proc, trace = _sage_replay(request['input_spectrum']['contents'], json.dumps(options, sort_keys=True))
    wave = np.asarray(proc['log_wave'])
    reproduced = np.interp(first[:, 0], wave, proc['tapered_flux'], left=np.nan, right=np.nan)
    if not np.allclose(reproduced, first[:, 1], rtol=1e-7, atol=1e-9, equal_nan=True):
        raise ValueError('SNID preprocessing replay does not reproduce saved observed residuals')
    import snid_sage
    return {**base, 'kind': 'snid-continuum-restored', 'continuum': [[float(x), float(y) if np.isfinite(y) else None] for x, y in zip(wave, proc['continuum'])],
            'flux_offset': float(trace['flux_offset']), 'preprocessing_options': options,
            'snid_sage_version': str(snid_sage.__version__),
            'fit_windows': trace.get('pending_mask_ranges', []),
            'verification_max_absolute_error': float(np.nanmax(abs(reproduced - first[:, 1]))),
            'note': 'Display-only restoration with the observed continuum; not a flux-calibrated template SED. Native taper remains.'}


def model_input_flux(curve, transform):
    model = np.asarray(curve.get('display_model', curve['model']), float).copy()
    if transform['kind'] == 'ngsf-scale':
        model[:, 1] *= transform['scale']
    elif transform['kind'] == 'snid-continuum-restored':
        cont = np.asarray(transform['continuum'], float)
        c = np.interp(model[:, 0], cont[:, 0], cont[:, 1], left=np.nan, right=np.nan)
        model[:, 1] = (model[:, 1] + 1) * c - transform['flux_offset']
        # Native SAGE display spectra retain values through excluded fit bands.
        # Do not reapply the observation masks to the matched template display.
    else:
        raise ValueError('Unknown model display transform')
    return model
