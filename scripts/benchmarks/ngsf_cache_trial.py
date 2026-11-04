"""Experimental per-fit caches; never imported by the production launcher.

Run in a fresh subprocess for one immutable input/configuration. The external
NGSF checkout is read only. Stage 0 measures native behavior, stage 1 caches
error_obj, and stage 2 also caches galaxy interpolation at the last redshift.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import resource
import runpy
import sys
import time


def install(functions, stage, capture_path=None, capture_redshifts=None):
    import numpy as np

    if stage not in (0, 1, 2, 3):
        raise ValueError("stage must be 0, 1, 2 or 3")
    counts, seconds = Counter(), defaultdict(float)
    error_native, arrays_native = functions.error_obj, functions.sn_hg_arrays
    error_key = error_value = galaxy_key = galaxy_value = None
    latest_sigma = latest_arrays = None

    def error(kind, lam, original):
        nonlocal error_key, error_value, latest_sigma
        started = time.perf_counter()
        counts['error_calls'] += 1
        try:
            key = (kind, str(original), lam.dtype.str, lam.shape, lam.tobytes())
            if stage and key == error_key:
                counts['error_hits'] += 1
                latest_sigma = error_value.copy()
                return latest_sigma
            counts['error_computations'] += 1
            value = error_native(kind, lam, original)
            latest_sigma = value
            if stage:
                error_key, error_value = key, value.copy()
            return value
        finally:
            seconds['error'] += time.perf_counter() - started

    def arrays(z, extcon, lam, sn_keys, sn_dict, gal_keys, gal_dict, alam_dict):
        nonlocal galaxy_key, galaxy_value, latest_arrays
        started = time.perf_counter()
        counts['arrays_calls'] += 1
        try:
            if stage < 2:
                counts['galaxy_computations'] += 1
                return arrays_native(z, extcon, lam, sn_keys, sn_dict, gal_keys, gal_dict, alam_dict)
            # Same operations and order as native SF_functions.sn_hg_arrays.
            # Cache only the galaxy component, which is independent of extcon.
            sn = []
            for name in sn_keys:
                one = sn_dict[name]
                redshifted = one[:, 0] * (z + 1)
                flux = one[:, 1] * 10 ** (-0.4 * extcon * alam_dict[name]) / (1 + z)
                sn.append(np.interp(lam, redshifted, flux, left=np.nan, right=np.nan))
            key = (z, lam.dtype.str, lam.shape, lam.tobytes(), tuple(gal_keys), id(gal_dict))
            if key != galaxy_key:
                counts['galaxy_computations'] += 1
                gal = []
                for name in gal_keys:
                    one = gal_dict[name]
                    gal.append(np.interp(lam, one[:, 0] * (z + 1), one[:, 1] / (1 + z),
                                         left=np.nan, right=np.nan))
                galaxy_key, galaxy_value = key, np.array(gal)[:, np.newaxis, :]
            else:
                counts['galaxy_hits'] += 1
            # The production mask bridge mutates these arrays: never expose
            # cache-owned data to it, or masks would leak between evaluations.
            latest_arrays = np.array(sn)[np.newaxis, :, :], galaxy_value.copy()
            return latest_arrays
        finally:
            seconds['arrays'] += time.perf_counter() - started

    functions.error_obj, functions.sn_hg_arrays = error, arrays
    for name in ('core', 'all_parameter_space'):
        native = getattr(functions, name)

        def timed(*args, _native=native, _name=name, **kwargs):
            started = time.perf_counter()
            counts[_name + '_calls'] += 1
            try:
                result = _native(*args, **kwargs)
            finally:
                seconds[_name] += time.perf_counter() - started
            destination = capture_path
            if _name == 'core' and capture_path is not None and capture_redshifts is not None:
                match = next((z for z in capture_redshifts if abs(float(args[1])-z) < 1e-12), None)
                destination = (capture_path.with_name(f'kernel_z{match:.2f}.npz')
                               if match is not None else None)
                if counts['core_calls'] % 41 == 0:
                    capture_path.with_name('benchmark_progress.json').write_text(json.dumps({
                        'core_calls': counts['core_calls'], 'redshift': float(args[1]),
                        'core_seconds': seconds['core']}, indent=2) + '\n')
            if (_name == 'core' and destination is not None and args[2] == 0
                    and not destination.exists()):
                # Save one actual, fully masked grid point for a paired replay
                # of arithmetic, separate from imports and interpolation.
                np.savez(destination, observed=args[0], sigma=latest_sigma,
                         sn=latest_arrays[0], gal=latest_arrays[1], lam=args[8])
                destination.with_suffix('.json').write_text(json.dumps({
                    'z': float(args[1]), 'extcon': float(args[2]), 'sn_keys': list(args[3]),
                    'gal_keys': [str(k) for k in args[5]], 'resolution': args[9],
                    'iterations': args[10], 'kwargs': kwargs,
                    'native_source': str(Path(functions.__file__).resolve())}, indent=2) + '\n')
            return result

        setattr(functions, name, timed)
    return counts, seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=int, choices=(0, 1, 2, 3), required=True)
    parser.add_argument('--capture-redshifts', type=float, nargs='+')
    parser.add_argument('target', type=Path)
    parser.add_argument('parameters', type=Path)
    parser.add_argument('features', type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    import numpy as np
    import spectypus
    from spectypus.adapters.ngsf_bridge import install_masks

    np.math = math  # same compatibility treatment as the production bridge
    sys.path.insert(0, str(args.target.parent))
    sys.argv = [str(args.target), str(args.parameters)]
    from NGSF import SF_functions as functions

    if args.stage == 3:
        from ngsf_core_reuse import install as install_core_reuse
        install_core_reuse(functions)
    counts, seconds = install(functions, args.stage,
                               args.features.with_name('kernel_inputs.npz') if args.stage == 3 else None,
                               args.capture_redshifts)
    settings = json.loads(args.features.read_text())
    save = install_masks(functions, settings['telluric_windows'],
                         args.features.with_name('mask_applied.json'),
                         args.features.with_name('fit_curves.json'), settings['top_n'])
    try:
        runpy.run_path(str(args.target), run_name='__main__')
        save()
    finally:
        metrics = {'stage': args.stage, 'counts': dict(counts), 'inclusive_seconds': dict(seconds),
                   'spectypus_package': str(Path(spectypus.__file__).resolve().parent),
                   'launcher_wall_seconds': time.perf_counter() - started,
                   'process_cpu_seconds': time.process_time(),
                   'max_rss_native_units': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                   'max_rss_units': 'bytes' if sys.platform == 'darwin' else 'KiB',
                   'native_functions_sha256': hashlib.sha256(Path(functions.__file__).read_bytes()).hexdigest()}
        args.features.with_name('benchmark_metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')


if __name__ == '__main__':
    main()
