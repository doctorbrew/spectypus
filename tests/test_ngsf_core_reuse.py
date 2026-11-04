import ast
import importlib.util
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')

# Native numerical operations isolated from file I/O and output tables, so
# degeneracies can be tested without a classifier installation or template bank.
SOURCE = '''
def core(sn, gal, int_obj, sigma):
    c = 1 / (np.nansum(sn**2, 2) * np.nansum(gal**2, 2) - np.nansum(gal * sn, 2)**2)
    b = c * (np.nansum(gal**2, 2) * np.nansum(sn * int_obj, 2) - np.nansum(gal * sn, 2) * np.nansum(gal * int_obj, 2))
    d = c * (np.nansum(sn**2, 2) * np.nansum(gal * int_obj, 2) - np.nansum(gal * sn, 2) * np.nansum(sn * int_obj, 2))
    b[b < 0] = np.nan
    d[d < 0] = np.nan
    sn_b = b[:, :, np.newaxis]
    gal_d = d[:, :, np.newaxis]
    a = ((int_obj - (sn_b * sn + gal_d * gal)) / sigma)**2
    a = np.isnan(a)
    times = len(int_obj) - np.nansum(a, 2)
    chi2 = np.nansum(((int_obj - (sn_b * sn + gal_d * gal))**2 / sigma**2), 2)
    return b, d, times, chi2, chi2 / (times - 2)**2
'''


def optimizer():
    path = Path(__file__).resolve().parents[1] / 'scripts/benchmarks/ngsf_core_reuse.py'
    spec = importlib.util.spec_from_file_location('core_reuse', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('edge', ['finite', 'masked', 'singular', 'overflow'])
def test_reused_intermediates_are_exact_including_nan_and_overflow(edge):
    baseline, optimized = {'np': np}, {'np': np}
    exec(SOURCE, baseline)
    exec(compile(optimizer().transform(SOURCE), '<test>', 'exec'), optimized)
    rng = np.random.default_rng(21)
    sn, gal = rng.random((1, 7, 30)), rng.random((3, 1, 30))
    observed, sigma = rng.random(30), np.ones(30)
    if edge == 'masked':
        sn[:, :, :3] = np.nan
        gal[:, :, -4:] = np.nan
        observed[10:12] = np.nan
    elif edge == 'singular':
        sn[:] = 1
        gal[:] = 1
    elif edge == 'overflow':
        sigma[:5] = 0
        sigma[5:10] = 1e-200
    with np.errstate(all='ignore'):
        expected = baseline['core'](sn, gal, observed, sigma)
        actual = optimized['core'](sn, gal, observed, sigma)
    for left, right in zip(expected, actual):
        np.testing.assert_array_equal(left, right)


def test_unexpected_native_source_fails_closed():
    with pytest.raises(ValueError, match='unexpected native'):
        optimizer().transform(SOURCE.replace('np.nansum(sn**2, 2)', 'np.sum(sn**2, 2)', 1))
    tree = optimizer().transform(SOURCE)
    sums = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == 'nansum']
    assert len(sums) == 7  # five reused reductions, overlap count, chi2
