"""Verified native-template evaluation for display; never performs a fit."""
from functools import lru_cache
import math
import os
import sys
from pathlib import Path
from spectypus.io import digest, file_hash, tree_hash


def restore_missing_model(saved, evaluated, tolerance=2e-6):
    """Verify the original finite fit samples before adding any missing values."""
    import numpy as np
    old, new = np.asarray(saved, float), np.asarray(evaluated, float)
    if old.shape != new.shape or not np.array_equal(old[:, 0], new[:, 0]):
        raise ValueError('Reconstructed model has a different native wavelength grid')
    good = np.isfinite(old[:, 1])
    if not good.any() or not np.all(np.isfinite(new[good, 1])):
        raise ValueError('Reconstructed model lost saved finite support')
    scale = float(np.max(np.abs(old[good, 1]))) or 1.
    error = float(np.max(np.abs(old[good, 1] - new[good, 1])) / scale)
    if error > tolerance:
        raise ValueError(f'Reconstructed model differs from saved fit: relative error {error:.6g}')
    merged = old.copy()
    fill = ~good & np.isfinite(new[:, 1])
    merged[fill, 1] = new[fill, 1]
    ids = np.flatnonzero(np.isfinite(merged[:, 1]))
    gaps = int(np.sum(~np.isfinite(merged[ids[0]:ids[-1]+1, 1])))
    if gaps:
        raise ValueError(f'Reconstructed model still has {gaps} internal missing samples')
    return [[float(x), float(y) if np.isfinite(y) else None] for x, y in merged], {
        'saved_finite_samples_unchanged': int(good.sum()), 'restored_samples': int(fill.sum()),
        'verification_max_relative_error': error, 'verification_tolerance': tolerance,
        'internal_missing_samples': gaps, 'coverage_angstrom': [float(merged[ids[0], 0]), float(merged[ids[-1], 0])]}


def native_grid_value(value, grid):
    """Recover the unique float64 grid value represented by a saved float32 row."""
    import numpy as np
    selected = np.asarray(grid)[np.asarray(grid, dtype=np.float32) == np.float32(value)]
    if len(selected) != 1:
        raise ValueError('Saved parameter does not identify one native grid value')
    return float(selected[0])


def recover_curve_coefficients(saved, components):
    """Identify native float32 coefficients from an existing curve, not observations.

    This is an exact representation check for the bridge's first-versus-table
    tied-score case. Reject approximations: the recovered float32 coefficients
    must reproduce every finite saved sample to 1e-10 relative precision.
    """
    import numpy as np
    old = np.asarray(saved, float)
    good = np.isfinite(old[:, 1])
    matrix = np.asarray(components, float)[good]
    if not np.isfinite(matrix).all() or np.linalg.matrix_rank(matrix) != 2:
        return None
    coef = np.linalg.lstsq(matrix, old[good, 1], rcond=None)[0].astype(np.float32).astype(float)
    error = np.max(np.abs(matrix @ coef - old[good, 1])) / (np.max(np.abs(old[good, 1])) or 1.)
    return coef if np.all(coef >= 0) and error <= 1e-10 else None


class NativeNGSF:
    def __init__(self, root, parameters, provenance):
        import numpy as np
        self.root = root.resolve()
        self.bank_hash = tree_hash(root / 'bank')
        self.source_hash = digest({'run': file_hash(root / 'run.py'), 'NGSF': tree_hash(root / 'NGSF', suffixes={'.py', '.csv', '.json'})})
        self.verify(provenance)
        np.math = math  # The frozen native implementation uses this compatibility alias.
        os.chdir(root)
        sys.path.insert(0, str(root))
        sys.argv = ['saved-model-display', str(parameters)]
        from NGSF.SF_functions import sn_hg_arrays, Alam
        from NGSF.Header_Binnings import bin_spectrum_bank, kill_header
        from NGSF.get_metadata import Metadata
        self.arrays, self.alam, self.bin, self.load = sn_hg_arrays, Alam, bin_spectrum_bank, kill_header
        meta = Metadata()
        self.mapping = {meta.shorhand_dict[k]: v for k, v in meta.dictionary_all_trunc_objects.items()}
        self.files = {}

    def verify(self, provenance):
        if provenance['bank_sha256'] != self.bank_hash or provenance['source_sha256'] != self.source_hash:
            raise ValueError('NGSF bank/source differs from the saved fit provenance')

    @lru_cache(maxsize=8192)
    def template(self, key, resolution, galaxy=False, bank_resolution=None):
        import numpy as np
        if galaxy:
            bank_resolution = resolution if bank_resolution is None else bank_resolution
            base = self.root / 'bank' / ('binnings/' + str(bank_resolution) + 'A' if bank_resolution in (10, 30) else 'original_resolution') / 'gal' / key
            values = self.bin(np.loadtxt(base), resolution)
        else:
            original = self.mapping[key]
            if resolution in (10, 30):
                base = self.root / 'bank/binnings' / (str(resolution) + 'A') / original[original.find('sne'):]
                values = np.loadtxt(base)
            else:
                base = self.root / original
                values = self.bin(self.load(base), resolution)
        if not base.resolve().is_relative_to(self.root / 'bank'):
            raise ValueError('Template path escaped the verified bank')
        self.files[str(base)] = file_hash(base)
        return values, str(base)

    def reconstruct(self, match, params, resolution):
        import numpy as np
        row = match['candidate']['native']; key = match['candidate']['template']
        sn, sn_path = self.template(key, resolution)
        # Native 30-A retry retains Parameters.templates_gal_trunc from the
        # original resolution, then bins those same galaxy files at 30 A.
        gal, gal_path = self.template(row['GALAXY'], resolution, True, params['resolution'])
        lam = np.asarray(match['curve']['model'], float)[:, 0]
        z_grid = ([params['z_exact']] if params['use_exact_z'] else np.linspace(
            params['z_range_begin'], params['z_range_end'],
            int((params['z_range_end'] - params['z_range_begin']) / params['z_int']) + 1))
        av_grid = np.linspace(params['Alam_low'], params['Alam_high'],
                              int((params['Alam_high'] - params['Alam_low']) / params['Alam_interval']) + 1)
        z = native_grid_value(row['Z'], z_grid)
        av = native_grid_value(row['A_v'], av_grid)
        if np.float32(match['curve']['redshift']) != np.float32(z):
            raise ValueError('Saved curve and candidate redshifts disagree')
        def components(extinction):
            templates, galaxies = self.arrays(z, extinction, lam,
                [key], {key: sn}, [gal_path], {gal_path: gal}, {key: self.alam(sn[:, 0])})
            return np.column_stack((templates[0, 0], galaxies[0, 0]))
        # Native result columns are float32. Recover those exact saved coefficients.
        coefficients = np.array([row['CONST_SN'], row['CONST_GAL']], dtype=np.float32).astype(float)
        arrays = components(av)
        model = coefficients[0] * arrays[:, 0] + coefficients[1] * arrays[:, 1]
        recovered = False
        try:
            points, info = restore_missing_model(match['curve']['model'], np.column_stack((lam, model)))
        except ValueError as original_error:
            if np.float32(match['curve']['score']) != np.float32(row['CHI2/dof2']):
                raise original_error
            identities = []
            # The bridge keeps the first equal-score curve; Astropy's table
            # uniqueness/sorting can retain another tied row. Recover only an
            # exact, unique representation of that saved curve on its native Av
            # grid. No observed spectrum, new template or redshift is searched.
            for trial_av in av_grid:
                trial = components(trial_av)
                coef = recover_curve_coefficients(match['curve']['model'], trial)
                if coef is not None:
                    trial_model = coef[0] * trial[:, 0] + coef[1] * trial[:, 1]
                    restored, check = restore_missing_model(match['curve']['model'],
                        np.column_stack((lam, trial_model)), tolerance=1e-10)
                    identities.append((float(trial_av), coef, restored, check))
            if len(identities) != 1:
                raise ValueError(f'{original_error}; exact saved-curve identities: {len(identities)}') from original_error
            av, coefficients, points, info = identities[0]
            recovered = True
        return points, {**info, 'method': 'native NGSF template evaluation; no observed-spectrum fitting',
                       'sn_template': sn_path, 'galaxy_template': gal_path, 'resolution_angstrom': resolution,
                       'sn_template_sha256': self.files[sn_path], 'galaxy_template_sha256': self.files[gal_path],
                       'bank_sha256': self.bank_hash, 'source_sha256': self.source_hash,
                       'saved_parameters': {k: row[k] for k in ('Z', 'A_v', 'CONST_SN', 'CONST_GAL', 'GALAXY')},
                       'evaluated_parameters': {'Z': z, 'A_v': av, 'CONST_SN': float(coefficients[0]), 'CONST_GAL': float(coefficients[1])},
                       'curve_parameters_recovered': recovered,
                       'curve_parameter_note': ('Unique exact float32 representation of saved curve; tied-score table row retained separately'
                                                if recovered else 'Saved table parameters on original native grid')}
