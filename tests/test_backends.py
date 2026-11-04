from collections import Counter
import importlib.util
from pathlib import Path
import sys

import pytest

from spectypus.config import load_config


def test_backend_defaults_options_and_unsupported_sage(config_factory, tmp_path):
    def cfg(name, backend=None):
        item = {'python': sys.executable, 'root': str(tmp_path)} if name == 'ngsf' else {
            'python': sys.executable, 'templates': str(tmp_path)}
        if backend is not None:
            item['backend'] = backend
        return load_config(config_factory(engines={name: item}))['engines'][name]
    assert cfg('ngsf')['backend'] == 'jax'
    assert cfg('snid_sage')['backend'] == 'native'
    for backend in ('native', 'numpy', 'jax'):
        assert cfg('ngsf', backend)['backend'] == backend
    with pytest.raises(ValueError, match='only for NGSF'):
        cfg('snid_sage', 'jax')
    with pytest.raises(ValueError, match='backend'):
        cfg('ngsf', 'float32')


def test_python_venv_symlink_is_preserved(config_factory, tmp_path):
    path = tmp_path / 'isolated-python'
    path.symlink_to(sys.executable)
    cfg = load_config(config_factory(engines={'snid_sage': {
        'python': str(path), 'templates': str(tmp_path)}}))
    assert cfg['engines']['snid_sage']['python'] == str(path)


def test_backend_choice_changes_execution_identity(config_factory, source_factory,
                                                   manifest_factory, fake_engine, tmp_path):
    from spectypus.pipeline import make_plan
    manifest = manifest_factory([source_factory(z='.1')])
    ids = []
    for backend in ('native', 'numpy', 'jax'):
        cfg = config_factory(engines={'ngsf': {'python': sys.executable, 'root': str(tmp_path), 'backend': backend}})
        ids.append(make_plan(manifest, cfg)['runs'][0]['execution_id'])
    assert len(set(ids)) == 3


def fixtures():
    path = Path(__file__).resolve().parents[1] / 'scripts/benchmarks/jax_ngsf_kernel.py'
    spec = importlib.util.spec_from_file_location('stress_fixtures', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.edge_fixtures()


def test_missing_jax_falls_back_visibly(monkeypatch):
    from spectypus.adapters import ngsf_backend as m
    def unavailable():
        raise ImportError('missing JAX')
    monkeypatch.setattr(m, 'make_jax_kernel', unavailable)
    report = {'counts': Counter()}
    m.Kernel('jax', report)
    assert report['effective'] == 'numpy'
    assert 'missing JAX' in report['fallback_reason']


def test_unknown_engine_source_is_not_transformed(tmp_path):
    from types import SimpleNamespace
    from spectypus.adapters.ngsf_backend import install
    source = tmp_path/'unknown.py'
    source.write_text('# independent version\n')
    original = lambda: None
    functions = SimpleNamespace(__file__=str(source), core=original)
    report = install(functions, 'jax')
    assert functions.core is original
    assert report['effective'] == 'native'
    assert 'unrecognized' in report['fallback_reason']


def test_jax_runtime_failure_is_recorded_and_disables_retry():
    np = pytest.importorskip('numpy')
    from spectypus.adapters.ngsf_backend import Kernel
    report = {'counts': Counter()}
    engine = Kernel('numpy', report)
    calls = []
    def broken(*args):
        calls.append(1)
        raise RuntimeError('test backend failure')
    engine.jax = broken
    args = fixtures()['ordinary']
    expected = engine.numpy(*args)
    for _ in range(2):
        actual = engine(*args, 1)
        for a, b in zip(expected, actual):
            np.testing.assert_array_equal(a, b)
    assert len(calls) == 1
    assert report['effective'] == 'numpy'
    assert 'test backend failure' in report['fallback_reason']


@pytest.mark.parametrize('case', ['ordinary', 'negative_coefficients', 'exact_overlap_boundary',
    'singular', 'near_singular', 'near_singular_positive_mixture', 'zero_sigma', 'underflow_sigma_squared'])
def test_guarded_jax_preserves_native_edge_results(case):
    np = pytest.importorskip('numpy')
    pytest.importorskip('jax')
    from spectypus.adapters.ngsf_backend import Kernel
    args = fixtures()[case]
    reference = Kernel('numpy', {'counts': Counter()})
    report = {'counts': Counter()}
    candidate = Kernel('jax', report)
    assert report['effective'] == 'jax'
    with np.errstate(all='ignore'):
        expected, actual = reference(*args, 1), candidate(*args, 1)
    for a, b in zip(expected, actual):
        np.testing.assert_array_equal(a, b)
    if 'near_singular' in case:
        assert report['counts']['native_rechecked_columns'] > 0


def test_native_recheck_restores_returned_scores():
    np = pytest.importorskip('numpy')
    from spectypus.adapters.ngsf_backend import Kernel
    rng = np.random.default_rng(47)
    sn, gal = rng.uniform(.1, 2, (1, 30, 40)), rng.uniform(.1, 2, (2, 1, 40))
    observed, sigma = rng.uniform(.1, 2, 40), np.ones(40)
    report = {'counts': Counter()}
    engine = Kernel('numpy', report)
    args = (sn, gal, observed, sigma, .7)
    expected = engine.numpy(*args)
    # Supply a slightly perturbed accelerated kernel.
    def approximate(sn_part, gal, obs, sigma, overlap, length):
        values = list(engine.numpy(sn_part, gal, obs, sigma, overlap))
        values[4] = values[4] * (1 + 1e-8)
        return (*values, np.zeros_like(values[4], dtype=bool))
    engine.jax = approximate
    with np.errstate(all='ignore'):
        actual = engine(*args, 10)
    indices = np.argsort(expected[4].ravel())[:10]
    assert np.array_equal(np.argsort(actual[4].ravel())[:10], indices)
    for a, b in zip(expected, actual):
        np.testing.assert_array_equal(a.ravel()[indices], b.ravel()[indices])


def test_near_tie_recheck_restores_native_candidate_order():
    np = pytest.importorskip('numpy')
    from spectypus.adapters.ngsf_backend import Kernel
    rng = np.random.default_rng(4)
    first = rng.uniform(.2, 2, 40)
    sn = np.stack([first, first + 1e-7*np.sin(np.arange(40))])[None, :, :]
    gal = rng.uniform(.2, 2, (1, 1, 40))
    observed = .5*first + .25*gal[0, 0] + .001*np.sin(np.arange(40))
    args = (sn, gal, observed, np.ones(40), .7)
    engine = Kernel('numpy', {'counts': Counter()})
    expected = engine.numpy(*args)
    assert np.isfinite(expected[4]).all()
    assert expected[4][0, 0] != expected[4][0, 1]
    def reversed_contenders(sn_part, gal, obs, sigma, overlap, length):
        values = list(engine.numpy(sn_part, gal, obs, sigma, overlap))
        values[4][:, :2] = values[4][:, :2][:, ::-1]
        return (*values, np.zeros_like(values[4], dtype=bool))
    engine.jax = reversed_contenders
    with np.errstate(all='ignore'):
        actual = engine(*args, 1)
    np.testing.assert_array_equal(actual[4], expected[4])
    assert np.argmin(actual[4]) == np.argmin(expected[4])
