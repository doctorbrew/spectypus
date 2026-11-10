"""Robust axis bounds only; never change the observed or model display arrays."""
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import savgol_filter

LIMIT_RULE = 'median50-sg50-central99-noise3-outward1.1'


def robust_limits(points, width=50.):
    """Use the central 99% of a 50-Angstrom median/SG trend for axis bounds.

    Each finite continuous segment is processed independently; telluric samples
    remain eligible. Omit filter-edge support from bounds, not from the plot.
    Coarse/short inputs fall back explicitly to finite native samples. Percentile
    bounds include a three-times robust first-difference scatter allowance, then
    outward scaling. They are display clipping, not data rejection; return counts of raw samples
    outside the axes so the browser can disclose this tradeoff.
    """
    data = np.asarray(points, dtype=float)
    x, y = data[:, 0], data[:, 1]
    if len(x) < 2 or not np.all(np.isfinite(x)) or np.any(np.diff(x) <= 0):
        raise ValueError('Limit wavelengths must be finite and strictly increasing')
    good = np.isfinite(y)
    if not good.any():
        raise ValueError('No finite input flux for display limits')
    scale = float(np.max(np.abs(y[good]))) or 1.
    normalized = y / scale
    steps = np.diff(x)
    cuts = np.flatnonzero(~good[:-1] | ~good[1:] | (steps > 3 * np.median(steps))) + 1
    support, differences, filtered, excluded = [], [], 0, 0
    for ids in np.split(np.arange(len(x)), cuts):
        ids = ids[good[ids]]
        differences.extend(np.diff(normalized[ids]))
        if len(ids) < 3:
            excluded += len(ids)
            continue
        grid = np.linspace(x[ids[0]], x[ids[-1]], len(ids))
        n = min(len(ids), int(np.floor(width / (grid[1] - grid[0]))) + 1)
        n -= int(n % 2 == 0)
        if n < 3:
            excluded += len(ids)
            continue
        values = np.interp(grid, x[ids], normalized[ids])
        trend = savgol_filter(median_filter(values, size=n, mode='nearest'), n, min(2, n - 2), mode='mirror')
        half = n // 2
        support.extend(trend[half:-half])
        filtered += len(ids)
        excluded += 2 * half
    fallback = not support
    values = np.asarray(support) if support else normalized[good]
    # Very short inputs cannot support useful tail statistics.
    percentiles = [0.5, 99.5] if len(values) >= 20 else [0., 100.]
    low, high = np.percentile(values, percentiles) * scale
    differences = np.asarray(differences)
    # A robust allowance for ordinary scatter keeps low-SNR spectra from being
    # cropped to their median trend. This is a display scale, not an uncertainty.
    noise = (1.4826 * np.median(np.abs(differences - np.median(differences))) / np.sqrt(2) * scale
             if len(differences) >= 20 else 0.)
    padded_low, padded_high = low - 3 * noise, high + 3 * noise
    lo = padded_low * 1.1 if padded_low < 0 else padded_low / 1.1
    hi = padded_high * 1.1 if padded_high > 0 else padded_high / 1.1
    if lo == hi:
        pad = abs(lo) * .1 if lo else 1e-6
        lo -= pad; hi += pad
    limits = [float(lo), float(hi)]
    return limits, {'limit_rule': LIMIT_RULE, 'limit_smoothing_width_angstrom': width,
                    'limit_percentiles': percentiles, 'limit_support_samples': len(values),
                    'limit_filtered_samples': filtered, 'limit_edge_or_short_samples_excluded': excluded,
                    'limit_fallback': 'finite-native-samples' if fallback else None,
                    'limit_telluric_samples_eligible': True, 'limit_robust_range': [float(low), float(high)],
                    'limit_display_noise_scale': float(noise), 'limit_noise_multiplier': 3.,
                    'limit_raw_samples_outside': int(np.sum(good & ((y < lo) | (y > hi)))),
                    'limit_raw_finite_samples': int(good.sum()), 'stretch_factor': 1.1}
