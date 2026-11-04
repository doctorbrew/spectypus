"""Subprocess-local NGSF arithmetic backends with native candidate rechecks.

Only the tested native source is transformed. Interpolation, extinction,
sorting and native table construction retain their existing implementations.
"""
import ast
from collections import Counter
import hashlib
import inspect
import os
from pathlib import Path
import textwrap

SUPPORTED_SOURCE = 'a27fa909c2dc8587dfe603be3cf72e383d10e58bb736943b763492a3c286dd6b'


def configure_cpu():
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'NPROC'):
        os.environ[name] = '1'
    os.environ['JAX_PLATFORMS'] = 'cpu'
    os.environ['JAX_ENABLE_X64'] = 'true'
    os.environ['JAX_CPU_ENABLE_ASYNC_DISPATCH'] = 'false'
    os.environ['XLA_FLAGS'] = ('--xla_cpu_multi_thread_eigen=false '
        '--xla_cpu_enable_fast_math=false --xla_cpu_parallel_codegen_split_count=1 '
        '--xla_force_host_platform_device_count=1 '
        'intra_op_parallelism_threads=1 inter_op_parallelism_threads=1')


def arithmetic(xp, sn, gal, observed, sigma, minimum_overlap, length=None, guarded=False):
    sn2 = xp.nansum(sn**2, axis=2)
    gal2 = xp.nansum(gal**2, axis=2)
    cross = xp.nansum(gal*sn, axis=2)
    sn_obs = xp.nansum(sn*observed, axis=2)
    gal_obs = xp.nansum(gal*observed, axis=2)
    determinant = sn2*gal2 - cross**2
    c = 1 / determinant
    numerator_b = gal2*sn_obs - cross*gal_obs
    numerator_d = sn2*gal_obs - cross*sn_obs
    b, d = c*numerator_b, c*numerator_d
    b, d = xp.where(b < 0, xp.nan, b), xp.where(d < 0, xp.nan, d)
    residual = observed - (b[:, :, None]*sn + d[:, :, None]*gal)
    count = observed.size - xp.sum(xp.isnan((residual/sigma)**2), axis=2)
    chi2 = xp.nansum(residual**2 / sigma**2, axis=2)
    raw_chi2 = chi2
    chi2 = xp.where(count / (observed.size if length is None else length) > minimum_overlap,
                    chi2, xp.inf)
    score, once = chi2 / (count-2)**2, chi2 / (count-2)
    outputs = (b, d, count, chi2, xp.where(score == 0, 1e10, score),
               xp.where(once == 0, 1e10, once))
    if not guarded:
        return outputs
    # Conservative cancellation/conditioning guards. Recheck whole SN columns
    # against every host so native summation and NaN conventions are retained.
    risk = ((xp.abs(determinant) <= 1e-3*(xp.abs(sn2*gal2) + cross**2))
            | ~xp.isfinite(determinant)
            | (xp.abs(numerator_b) <= 1e-6*(xp.abs(gal2*sn_obs) + xp.abs(cross*gal_obs)))
            | (xp.abs(numerator_d) <= 1e-6*(xp.abs(sn2*gal_obs) + xp.abs(cross*sn_obs))))
    # Native has a discontinuous sentinel at an exactly zero score. Avoid
    # deciding a perfect/near-perfect match using compiled residual arithmetic.
    scale = xp.nansum(observed**2 / sigma**2)
    risk |= xp.isfinite(b) & xp.isfinite(d) & (raw_chi2 <= 1e-12*scale)
    return (*outputs, risk)


def make_jax_kernel():
    import jax
    import jaxlib
    import jax.numpy as jnp
    if jax.__version__ != '0.6.2' or jaxlib.__version__ != '0.6.2':
        raise RuntimeError('requires tested jax/jaxlib 0.6.2')
    jax.config.update('jax_enable_x64', True)
    if jax.default_backend() != 'cpu':
        raise RuntimeError('only CPU JAX has been validated')
    compiled = jax.jit(lambda sn, gal, obs, sigma, overlap, length:
        arithmetic(jnp, sn, gal, obs, sigma, overlap, length, guarded=True))
    return compiled


class Kernel:
    def __init__(self, backend, report):
        self.report = report
        self.counts = report['counts']
        self.jax = None
        if backend == 'jax':
            try:
                self.jax = make_jax_kernel()
            except (ImportError, RuntimeError) as exc:
                report['fallback_reason'] = f'{type(exc).__name__}: {exc}'
        report['effective'] = 'jax' if self.jax is not None else 'numpy'

    def numpy(self, sn, gal, observed, sigma, overlap):
        import numpy as np
        parts = [arithmetic(np, sn[:, i:i+8], gal, observed, sigma, overlap)
                 for i in range(0, sn.shape[1], 8)]
        return tuple(np.concatenate([p[k] for p in parts], axis=1) for k in range(6))

    def __call__(self, sn, gal, observed, sigma, overlap, iterations):
        import numpy as np
        self.counts['grid_calls'] += 1
        # These cases can change residual NaN/Inf behavior under compilation.
        unsafe = (any(np.isinf(x).any() for x in (sn, gal, observed, sigma))
                  or np.any(np.isfinite(sigma) & ((np.abs(sigma) < 1e-150) | (np.abs(sigma) > 1e150)))
                  or any(np.nanmax(np.abs(x), initial=0) > 1e100 for x in (sn, gal, observed)))
        if self.jax is None or unsafe:
            self.counts['numpy_grid_calls'] += 1
            if unsafe:
                self.counts['unsafe_input_fallbacks'] += 1
            return self.numpy(sn, gal, observed, sigma, overlap)
        n = sn.shape[1]
        padded = np.pad(sn, ((0, 0), (0, (-n) % 8), (0, 0)), constant_values=np.nan)
        try:
            parts = [tuple(np.asarray(x) for x in self.jax(padded[:, i:i+8], gal,
                     observed, sigma, np.float64(overlap), np.float64(observed.size)))
                     for i in range(0, padded.shape[1], 8)]
        except Exception as exc:
            # A backend failure must remain visible; fall back for this fit.
            self.report['fallback_reason'] = f'JAX execution failed: {type(exc).__name__}: {exc}'
            self.report['effective'] = 'numpy'
            self.jax = None
            self.counts['numpy_grid_calls'] += 1
            return self.numpy(sn, gal, observed, sigma, overlap)
        output = [np.concatenate([p[k] for p in parts], axis=1)[:, :n].copy() for k in range(6)]
        risk = np.concatenate([p[6] for p in parts], axis=1)[:, :n]
        checked = np.zeros(n, dtype=bool)

        def recheck(columns):
            columns = np.asarray(columns, dtype=int)
            if columns.size:
                reference = self.numpy(sn[:, columns], gal, observed, sigma, overlap)
                for actual, exact in zip(output, reference):
                    actual[:, columns] = exact
                checked[columns] = True
                self.counts['native_rechecked_columns'] += len(columns)

        recheck(np.flatnonzero(risk.any(axis=0)))
        # Recompute contenders with native NumPy before native table building.
        # Include a deliberately wider margin than the validated 1e-9 tolerance
        # and iterate when a rechecked candidate moves outside the top set.
        while True:
            flat = output[4].ravel()
            order = np.argsort(flat)
            selected = order[:iterations]
            cutoff = flat[selected[-1]]
            contenders = selected
            if np.isfinite(cutoff):
                contenders = np.union1d(selected, np.flatnonzero(np.isfinite(flat)
                    & (flat <= cutoff + 1e-6*abs(cutoff) + 1e-10)))
            columns = np.unique(contenders % n)
            pending = columns[~checked[columns]]
            if not len(pending):
                break
            recheck(pending)
        self.counts['jax_grid_calls'] += 1
        return tuple(output)


def install(functions, backend):
    if backend not in {'native', 'numpy', 'jax'}:
        raise ValueError(f'unsupported NGSF backend: {backend}')
    report = {'schema': 'spectypus-backend/1', 'requested': backend,
              'effective': 'native', 'precision': 'float64', 'device': 'cpu',
              'counts': Counter(), 'fallback_reason': None,
              'native_candidate_rechecks': False}
    if backend == 'native':
        return report
    source_hash = hashlib.sha256(Path(functions.__file__).read_bytes()).hexdigest()
    report['source_sha256'] = source_hash
    if source_hash != SUPPORTED_SOURCE:
        report['fallback_reason'] = 'unrecognized NGSF source; retained native core'
        return report
    source = textwrap.dedent(inspect.getsource(functions.core))
    tree = ast.parse(source)
    body = tree.body[0].body
    def assignment(node):
        return node.targets[0].id if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) else None
    start = next(i for i, node in enumerate(body) if assignment(node) == 'c')
    end = next(i for i, node in enumerate(body) if assignment(node) == 'reduchi2_1d')
    kernel = Kernel(backend, report)
    report['native_candidate_rechecks'] = kernel.jax is not None
    tree.body[0].body = body[:start] + ast.parse(
        'b, d, times, chi2, reduchi2, reduchi2_once = '
        '_spectypus_kernel(sn, gal, int_obj, sigma, minimum_overlap, iterations)').body + body[end:]
    # Keep function globals tied to the original module so subsequent mask
    # hooks still intercept sn_hg_arrays. External files are never written.
    functions.__dict__['_spectypus_kernel'] = kernel
    exec(compile(ast.fix_missing_locations(tree), '<spectypus-ngsf-backend>', 'exec'), functions.__dict__)
    original_error = functions.error_obj
    error_key = error_value = None

    def error(kind, lam, original):
        nonlocal error_key, error_value
        key = (kind, str(original), lam.dtype.str, lam.shape, lam.tobytes())
        if key != error_key:
            error_value = original_error(kind, lam, original).copy()
            error_key = key
        return error_value.copy()

    functions.error_obj = error
    return report
