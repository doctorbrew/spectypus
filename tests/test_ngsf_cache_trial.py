"""Local cache contract tests; real-engine equality belongs to the benchmark."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

np = pytest.importorskip('numpy')


def trial():
    path = Path(__file__).resolve().parents[1] / 'scripts/benchmarks/ngsf_cache_trial.py'
    spec = importlib.util.spec_from_file_location('cache_trial', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_arrays(z, av, lam, sn_keys, sn, gal_keys, gal, alam):
    # Independent scalar reference; includes out-of-range NaNs.
    s = [np.interp(lam, sn[k][:, 0] * (1+z),
                   sn[k][:, 1] * 10**(-.4*av*alam[k]) / (1+z),
                   left=np.nan, right=np.nan) for k in sn_keys]
    g = [np.interp(lam, gal[k][:, 0] * (1+z), gal[k][:, 1] / (1+z),
                   left=np.nan, right=np.nan) for k in gal_keys]
    return np.asarray(s)[None, :, :], np.asarray(g)[:, None, :]


def functions():
    return SimpleNamespace(error_obj=lambda kind, lam, path: lam.copy(),
                           sn_hg_arrays=native_arrays, core=lambda: None,
                           all_parameter_space=lambda: None)


def test_error_cache_keys_and_mutation_isolation():
    f = functions()
    counts, _ = trial().install(f, 1)
    lam = np.array([4000., 5000., 6000.])
    result = f.error_obj('sg', lam, 'a')
    result[:] = 0
    np.testing.assert_array_equal(f.error_obj('sg', lam.copy(), 'a'), lam)
    f.error_obj('sg', lam+1, 'a')
    f.error_obj('linear', lam+1, 'a')
    f.error_obj('linear', lam+1, 'b')
    assert counts['error_computations'] == 4
    assert counts['error_hits'] == 1


def test_galaxy_cache_exactness_mask_isolation_and_redshift_invalidation():
    f = functions()
    counts, _ = trial().install(f, 2)
    lam = np.array([3000., 4000., 5000., 6000., 7000.])
    sn = {'sn': np.array([[3500., 2.], [5000., 5.], [6500., 1.]])}
    gal = {'gal': np.array([[3500., 1.], [5000., 2.], [6500., 3.]])}
    alam = {'sn': np.array([1.5, 1., .8])}
    for z in (0., .1):
        for av in (-4., 0., 4.):
            args = (z, av, lam, list(sn), sn, list(gal), gal, alam)
            actual = f.sn_hg_arrays(*args)
            expected = native_arrays(*args)
            for a, e in zip(actual, expected):
                np.testing.assert_array_equal(a, e)
            actual[1][:] = np.nan  # emulate the production mask bridge
    assert counts['galaxy_computations'] == 2
    assert counts['galaxy_hits'] == 4
    changed = lam + 20
    args = (.1, 0., changed, list(sn), sn, list(gal), gal, alam)
    np.testing.assert_array_equal(f.sn_hg_arrays(*args)[1], native_arrays(*args)[1])
    assert counts['galaxy_computations'] == 3


def test_baseline_does_not_cache():
    f = functions()
    counts, _ = trial().install(f, 0)
    for _ in range(2):
        f.error_obj('sg', np.array([1., 2.]), 'a')
    assert counts['error_computations'] == 2
    assert counts['error_hits'] == 0
