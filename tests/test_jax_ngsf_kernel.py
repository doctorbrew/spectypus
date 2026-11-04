import importlib.util
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')


def module():
    path = Path(__file__).resolve().parents[1] / 'scripts/benchmarks/jax_ngsf_kernel.py'
    spec = importlib.util.spec_from_file_location('trial_kernel', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def arrays():
    sn = np.array([[[1., 0., 1., 0.]*3]])
    gal = np.array([[[0., 1., 0., 1.]*3]])
    observed = .5*sn[0, 0] + .25*gal[0, 0]
    return sn, gal, observed, np.ones(12), .7


def test_known_mixture_and_native_zero_score_sentinel():
    m = module()
    actual = m.arithmetic(np, *arrays())
    assert actual[0][0, 0] == .5
    assert actual[1][0, 0] == .25
    assert actual[2][0, 0] == 12
    assert actual[3][0, 0] == 0
    assert actual[4][0, 0] == 1e10


def test_strict_overlap_boundary_and_invalid_coefficients():
    m = module()
    sn, gal, observed, sigma, _ = arrays()
    for a in (sn, gal):
        a[..., -3:] = np.nan
    observed[-3:] = np.nan
    actual = m.arithmetic(np, sn, gal, observed, sigma, .75)
    assert actual[2][0, 0] == 9
    assert np.isinf(actual[4][0, 0])  # equality to minimum overlap must reject
    with np.errstate(all='ignore'):
        negative = m.arithmetic(np, *[sn, gal, -observed, sigma, .7])
    assert np.isnan(negative[0]).all()


def test_comparison_rejects_semantic_changes_and_truncated_results():
    m = module()
    expected = m.arithmetic(np, *arrays())
    assert m.compare(expected, expected)['accepted']
    altered = [a.copy() for a in expected]
    altered[4][0, 0] = np.inf
    assert not m.compare(expected, altered)['accepted']
    altered = [a.copy() for a in expected]
    altered[0][0, 0] += .001
    assert not m.compare(expected, altered)['accepted']
    with pytest.raises(ValueError, match='incomplete'):
        m.compare(expected, altered[:-1])
    with pytest.raises(ValueError, match='shape'):
        m.compare(expected, [np.ones(2), *altered[1:]])


def test_jax_known_mixture_when_optional_backend_is_installed():
    pytest.importorskip('jax')
    m = module()
    actual = m.make_jax_kernel()(*arrays())
    expected = m.arithmetic(np, *arrays())
    assert m.compare(expected, actual)['accepted']


def test_jax_preserves_strict_decimal_overlap_boundary():
    pytest.importorskip('jax')
    m = module()
    args = m.edge_fixtures()['exact_overlap_boundary']
    expected = m.arithmetic(np, *args)
    actual = m.make_jax_kernel()(*args)
    assert expected[2][0, 0] == 7
    assert np.isinf(expected[4][0, 0])
    assert m.compare(expected, actual)['accepted']
