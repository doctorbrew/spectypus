"""Standalone NGSF launcher; compatibility and masks stay in this subprocess."""
import json
import math
import os
from pathlib import Path
import runpy
import sys


def window_mask(wavelength, windows):
    import numpy as np
    mask = np.zeros(len(wavelength), dtype=bool)
    for lo, hi in windows:
        mask |= (wavelength >= lo) & (wavelength <= hi)
    return mask


def install_masks(functions, windows, report_path, curve_path=None, top_n=10):
    """Exclude masked samples from object AND template normal equations."""
    import numpy as np
    original_core = functions.core
    original_arrays = functions.sn_hg_arrays
    active_mask = None
    calls = 0
    best_curves = {}
    last_arrays = None

    def remove_telluric(spectrum):
        result = np.array(spectrum, dtype=float, copy=True)
        result[window_mask(result[:, 0], windows), 1] = np.nan
        return result

    def arrays(*args, **kwargs):
        nonlocal last_arrays
        sn, gal = original_arrays(*args, **kwargs)
        sn[..., active_mask] = np.nan
        gal[..., active_mask] = np.nan
        last_arrays = (sn, gal)
        return sn, gal

    def core(int_obj, *args, **kwargs):
        nonlocal active_mask, calls
        lam = np.asarray(args[7])
        masked = np.array(int_obj, dtype=float, copy=True)
        excluded = window_mask(lam, windows)
        masked[excluded] = np.nan
        active_mask = ~np.isfinite(masked)
        if np.count_nonzero(~active_mask) < 35:
            raise ValueError("fewer than 35 usable NGSF grid samples after telluric masking")
        calls += 1
        if calls == 1:
            Path(report_path).write_text(json.dumps({"schema": "spectypus-ngsf-mask/1",
                "observer_angstrom_windows": windows, "grid_samples": len(lam),
                "telluric_grid_samples": int(excluded.sum()), "usable_grid_samples": int((~active_mask).sum()),
                "object_and_template_exclusion": True}, indent=2) + "\n")
        result = original_core(masked, *args, **kwargs)
        if curve_path and last_arrays is not None:
            sn, gal = last_arrays
            sn_keys = list(args[2])
            gal_keys = [os.path.basename(str(v)) for v in args[4]]
            for row in result[0]:
                key, score = str(row['SN']), float(row['CHI2/dof2'])
                if not math.isfinite(score) or score < 0 or (key in best_curves and best_curves[key]['score'] <= score):
                    continue
                if key not in best_curves and len(best_curves) >= top_n and score >= max(x['score'] for x in best_curves.values()):
                    continue
                si, gi = sn_keys.index(key), gal_keys.index(str(row['GALAXY']))
                model = float(row['CONST_SN']) * sn[0, si, :] + float(row['CONST_GAL']) * gal[gi, 0, :]
                def points(values):
                    return [[float(x), float(y) if np.isfinite(y) else None] for x, y in zip(lam, values)]
                best_curves[key] = dict(template=key, score=score, redshift=float(row['Z']), available=True,
                    observed=points(masked), model=points(model), galaxy=str(row['GALAXY']))
            while len(best_curves) > top_n:
                del best_curves[max(best_curves, key=lambda k: best_curves[k]['score'])]
        return result

    functions.sn_hg_arrays = arrays
    functions.core = core
    functions.remove_telluric = remove_telluric
    def save_curves():
        if curve_path:
            curves = sorted(best_curves.values(), key=lambda c: (c['score'], c['template']))
            Path(curve_path).write_text(json.dumps({'schema': 'spectypus-fit-curves/1', 'engine': 'ngsf',
                'wavelength_frame': 'observer', 'wavelength_unit': 'angstrom', 'flux_unit': 'native normalized flux',
                'origin': 'Native fit grid, template arrays and saved coefficients; no refitting',
                'curves': curves}, allow_nan=False) + '\n')
    return save_curves


def main():
    target, parameters = sys.argv[1:3]
    mask_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    settings = json.loads(mask_path.read_text()) if mask_path else {}
    backend = settings.get('backend', 'native')
    # Import the sibling module from this exact launcher checkout/runtime.
    sys.path.insert(0, str(Path(__file__).parent))
    from ngsf_backend import configure_cpu, install
    if backend != 'native':
        configure_cpu()
    import numpy as np
    np.math = math
    sys.path.insert(0, os.path.dirname(target))
    sys.argv = [target, parameters]
    save_curves = lambda: None
    from NGSF import SF_functions as functions
    report = install(functions, backend)
    windows = settings.get('telluric_windows', [])
    if windows or settings.get('save_fit_curves'):
        save_curves = install_masks(functions, windows, mask_path.with_name("mask_applied.json"),
            mask_path.with_name("fit_curves.json") if settings.get("save_fit_curves") else None, settings.get("top_n", 10))
    try:
        runpy.run_path(target, run_name="__main__")
        save_curves()
    finally:
        Path(parameters).with_name('backend.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == "__main__":
    main()
