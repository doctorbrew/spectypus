"""Experimental JAX arithmetic only; no engine, interpolation or ranking patch.

The NumPy reference is extracted from the installed native source. The JAX
function retains its equations, unusual CHI2/dof2, overlap and NaN semantics.
Compilation can still change floating-point results; callers must validate.
"""
import ast
import copy
import numpy as np

FIELDS = ('sn_coefficient', 'gal_coefficient', 'samples', 'chi2', 'score', 'chi2_dof')
RTOL, ATOL = 1e-9, 1e-10


def native_reference(source):
    native = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'core')
    block, started = [], False
    for node in native.body:
        target = (node.targets[0].id if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) else '')
        if target == 'reduchi2_1d':
            break
        if target == 'c':
            started = True
        if started:
            block.append(copy.deepcopy(node))
    if not started or not any(isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                              and n.targets[0].id == 'reduchi2_once' for n in block):
        raise ValueError('unrecognized native numerical core')
    tree = ast.parse('def core(sn, gal, int_obj, sigma, minimum_overlap):\n    lam = int_obj\n')
    tree.body[0].body += block + ast.parse('return b, d, times, chi2, reduchi2, reduchi2_once').body
    namespace = {'np': np}
    exec(compile(ast.fix_missing_locations(tree), '<native-ngsf-arithmetic>', 'exec'), namespace)
    return namespace['core']


def arithmetic(xp, sn, gal, observed, sigma, minimum_overlap, sample_count=None):
    sn2 = xp.nansum(sn**2, axis=2)
    gal2 = xp.nansum(gal**2, axis=2)
    cross = xp.nansum(gal*sn, axis=2)
    sn_obs = xp.nansum(sn*observed, axis=2)
    gal_obs = xp.nansum(gal*observed, axis=2)
    c = 1 / (sn2*gal2 - cross**2)
    b = c * (gal2*sn_obs - cross*gal_obs)
    d = c * (sn2*gal_obs - cross*sn_obs)
    b, d = xp.where(b < 0, xp.nan, b), xp.where(d < 0, xp.nan, d)
    residual = observed - (b[:, :, None]*sn + d[:, :, None]*gal)
    # Keep both native expressions; deriving NaNs from chi2 instead can change
    # behavior for zero/tiny sigma and overflow.
    invalid = xp.isnan((residual/sigma)**2)
    count = observed.size - xp.sum(invalid, axis=2)
    chi2 = xp.nansum(residual**2 / sigma**2, axis=2)
    divisor = observed.size if sample_count is None else sample_count
    chi2 = xp.where(count / divisor > minimum_overlap, chi2, xp.inf)
    score, once = chi2 / (count-2)**2, chi2 / (count-2)
    return b, d, count, chi2, xp.where(score == 0, 1e10, score), xp.where(once == 0, 1e10, once)


def compare(reference, candidate):
    if len(reference) != len(FIELDS) or len(candidate) != len(FIELDS):
        raise ValueError('incomplete kernel result')
    fields = {}
    for name, expected, actual in zip(FIELDS, reference, candidate):
        expected, actual = np.asarray(expected), np.asarray(actual)
        if expected.shape != actual.shape:
            raise ValueError('kernel output shape changed')
        nonfinite = (np.array_equal(np.isnan(expected), np.isnan(actual))
                     and np.array_equal(np.isposinf(expected), np.isposinf(actual))
                     and np.array_equal(np.isneginf(expected), np.isneginf(actual)))
        valid = np.isfinite(expected) & np.isfinite(actual)
        delta = np.abs(actual[valid] - expected[valid])
        close = bool(np.allclose(expected[valid], actual[valid], rtol=RTOL, atol=ATOL))
        fields[name] = {'nonfinite_equal': nonfinite, 'within_tolerance': close,
                        'max_absolute_error': float(delta.max()) if delta.size else 0.,
                        'max_scaled_error': float(np.max(delta/(ATOL+RTOL*np.abs(expected[valid])))) if delta.size else 0.,
                        'exact': bool(np.array_equal(expected, actual, equal_nan=True))}
    left, right = np.asarray(reference[4]).ravel(), np.asarray(candidate[4]).ravel()
    native_top, trial_top = np.argsort(left)[:10], np.argsort(right)[:10]
    top_equal = bool(np.array_equal(native_top, trial_top))
    count_exact = bool(np.array_equal(reference[2], candidate[2]))
    passed = top_equal and count_exact and all(f['nonfinite_equal'] and f['within_tolerance'] for f in fields.values())
    return {'accepted': passed, 'fields': fields, 'sample_counts_exact': count_exact,
            'top10_indices_exact': top_equal, 'native_top10': native_top.tolist(),
            'trial_top10': trial_top.tolist(), 'finite_score_count': int(np.isfinite(left).sum()),
            'all_score_order_exact': bool(np.array_equal(np.argsort(left), np.argsort(right)))}


def make_jax_kernel(*, dynamic_overlap_divisor=True):
    import jax
    import jax.numpy as jnp
    jax.config.update('jax_enable_x64', True)
    if not dynamic_overlap_divisor:
        return jax.jit(lambda sn, gal, observed, sigma, overlap:
                       arithmetic(jnp, sn, gal, observed, sigma, overlap))
    # A static divisor can become reciprocal multiplication under XLA, moving
    # values exactly on the strict overlap boundary. Keep the divisor dynamic
    # so the compiled division follows the native operation. This does not
    # address reduction-order changes or near-singular mixtures.
    compiled = jax.jit(lambda sn, gal, observed, sigma, overlap, length:
                       arithmetic(jnp, sn, gal, observed, sigma, overlap, length))

    def evaluate(sn, gal, observed, sigma, overlap):
        return compiled(sn, gal, observed, sigma, overlap,
                        np.asarray(observed.size, dtype=observed.dtype))

    return evaluate


def edge_fixtures():
    """Deterministic numerical cases, including the exact overlap boundary."""
    sn = np.array([[[1., 2., 1., 3., 2., 1., 3., 2., 1., 2.]]])
    gal = np.array([[[3., 1., 2., 1., 3., 2., 1., 2., 3., 1.]]])
    observed = .5*sn[0, 0] + .25*gal[0, 0] + np.arange(10)*.001
    result = {'ordinary': (sn, gal, observed, np.ones(10), .7)}
    result['negative_coefficients'] = (sn, gal, -observed, np.ones(10), .7)
    masked = [a.copy() for a in (sn, gal, observed)]
    for a in masked:
        a[..., -3:] = np.nan
    result['exact_overlap_boundary'] = (*masked, np.ones(10), .7)
    result['singular'] = (sn, sn.copy(), observed, np.ones(10), .7)
    result['near_singular'] = (sn, sn + 1e-8*np.sin(np.arange(10)), observed, np.ones(10), .7)
    close_gal = sn + 1e-5*np.sin(np.arange(10))
    close_observed = .5*sn[0, 0] + .25*close_gal[0, 0]
    result['near_singular_positive_mixture'] = (sn, close_gal, close_observed, np.ones(10), .7)
    sigma = np.ones(10)
    sigma[:2] = 0
    result['zero_sigma'] = (sn, gal, observed, sigma, .7)
    result['underflow_sigma_squared'] = (sn, gal, observed, np.full(10, 1e-200), .7)
    return result
