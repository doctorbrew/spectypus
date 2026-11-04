"""Experimental common-expression reuse in NGSF's native core.

Transform only six explicitly matched, pure array expressions. Keep the rest
of the native function, including NaN handling, score normalization, ordering
and table construction, unchanged. Fail closed on an unexpected source shape.
This is an opt-in benchmark hook, not a production engine patch.
"""
import ast
import inspect
import textwrap


REDUCTIONS = {
    'np.nansum(sn ** 2, 2)': ('_bench_sn2', 2),
    'np.nansum(gal ** 2, 2)': ('_bench_gal2', 2),
    'np.nansum(gal * sn, 2)': ('_bench_cross', 3),
    'np.nansum(sn * int_obj, 2)': ('_bench_sn_obj', 2),
    'np.nansum(gal * int_obj, 2)': ('_bench_gal_obj', 2),
}
RESIDUAL = 'int_obj - (sn_b * sn + gal_d * gal)'


def transform(source):
    tree = ast.parse(textwrap.dedent(source))
    fn = tree.body[0]
    if not isinstance(fn, ast.FunctionDef) or fn.name != 'core':
        raise ValueError('expected native core function')
    replacements = {ast.dump(ast.parse(expr, mode='eval').body): (name, count)
                    for expr, (name, count) in REDUCTIONS.items()}
    replacements[ast.dump(ast.parse(RESIDUAL, mode='eval').body)] = ('_bench_residual', 2)
    counts = {key: 0 for key in replacements}
    if any(isinstance(n, ast.Name) and n.id.startswith('_bench_') for n in ast.walk(fn)):
        raise ValueError('benchmark variable collision')

    class Reuse(ast.NodeTransformer):
        def visit(self, node):
            key = ast.dump(node)
            if key in replacements:
                counts[key] += 1
                return ast.copy_location(ast.Name(id=replacements[key][0], ctx=ast.Load()), node)
            return super().visit(node)

    fn = Reuse().visit(fn)
    if any(counts[key] != expected for key, (_, expected) in replacements.items()):
        raise ValueError('unexpected native reduction/residual expressions')
    body, inserted = [], []
    for statement in fn.body:
        name = (statement.targets[0].id if isinstance(statement, ast.Assign)
                and isinstance(statement.targets[0], ast.Name) else None)
        if name == 'c':
            body.extend(ast.parse(f'{var} = {expr}').body[0]
                        for expr, (var, _) in REDUCTIONS.items())
            inserted.append('reductions')
        if name == 'a' and 'residual' not in inserted:
            body.extend(ast.parse(f'_bench_residual = {RESIDUAL}').body)
            inserted.append('residual')
        body.append(statement)
    if inserted != ['reductions', 'residual']:
        raise ValueError('unexpected native core assignment order')
    fn.body = body
    tree.body = [fn]
    return ast.fix_missing_locations(tree)


def install(functions):
    tree = transform(inspect.getsource(functions.core))
    namespace = functions.__dict__
    exec(compile(tree, '<spectypus-benchmark-common-expressions>', 'exec'), namespace)
