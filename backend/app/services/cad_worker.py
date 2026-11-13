"""Private process entry point; reads only the limited CAD language from stdin."""
import ast
import json
import math
import os
from pathlib import Path
import sys

# -I ignores the working directory and environment Python paths. Load this exact
# sibling module, never application startup/configuration (which can contain secrets).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cad_sandbox import CadScriptError, validate_script


def run(script):
    import cadquery as cq
    tree = validate_script(script)
    variables = {}

    def bounded(value):
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e6:
            raise CadScriptError('Arithmetic must produce a finite number within 1,000,000')
        return value

    def evaluate(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return variables[node.id]
        if isinstance(node, (ast.Tuple, ast.List)):
            values = [evaluate(item) for item in node.elts]
            return tuple(values) if isinstance(node, ast.Tuple) else values
        if isinstance(node, ast.UnaryOp):
            value = bounded(evaluate(node.operand))
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = bounded(evaluate(node.left)), bounded(evaluate(node.right))
            if isinstance(node.op, ast.Add):
                return bounded(left + right)
            if isinstance(node.op, ast.Sub):
                return bounded(left - right)
            if isinstance(node.op, ast.Mult):
                return bounded(left * right)
            return bounded(left / right)
        if isinstance(node, ast.Call):
            args = [evaluate(arg) for arg in node.args]
            kwargs = {kw.arg: evaluate(kw.value) for kw in node.keywords}
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'cq':
                # Never pass a model object as a constructor plane/origin.
                if any(isinstance(arg, cq.Workplane) for arg in args + list(kwargs.values())):
                    raise CadScriptError('Invalid Workplane constructor argument')
                return cq.Workplane(*args, **kwargs)
            receiver = evaluate(node.func.value)
            if type(receiver) is not cq.Workplane:
                raise CadScriptError('Modeling calls require a Workplane')
            # Resource multipliers otherwise allow billions of holes in one call.
            if node.func.attr in ('rarray', 'polarArray'):
                for value in args:
                    if type(value) in (int, float) and abs(value) > 512:
                        raise CadScriptError('CAD array exceeds resource limit')
                for key, value in kwargs.items():
                    if key in ('xCount', 'yCount', 'count') and (type(value) not in (int, float) or value > 512):
                        raise CadScriptError('CAD array exceeds resource limit')
            try:
                return getattr(receiver, node.func.attr)(*args, **kwargs)
            except Exception as exc:
                raise CadScriptError(f'{node.func.attr} at line {node.lineno}: {str(exc)[:350]}') from None
        raise CadScriptError('Invalid CAD expression')

    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            variables[statement.targets[0].id] = evaluate(statement.value)
    result = variables['result']
    if type(result) is not cq.Workplane:
        raise CadScriptError('result must be a solid Workplane')
    # Combine all selected solids into one exported compound, preserving bodies.
    solids = result.solids().vals()
    if not solids or len(solids) > 32:
        raise CadScriptError('CAD result must contain between 1 and 32 solids')
    shape = cq.Compound.makeCompound(solids)
    box = shape.BoundingBox()
    dimensions = [box.xlen, box.ylen, box.zlen]
    volume = shape.Volume()
    valid = shape.isValid() and all(solid.isValid() and solid.Volume() > 1e-6 for solid in solids)
    if not valid or not math.isfinite(volume) or volume <= 1e-6 or any(not math.isfinite(d) or d <= 1e-6 or d > 10000 for d in dimensions):
        raise CadScriptError('CAD result is invalid, empty, or outside dimension limits')
    cq.exporters.export(shape, 'model.step', exportType='STEP')
    cq.exporters.export(shape, 'model.stl', exportType='STL', tolerance=0.05, angularTolerance=0.1)
    return {'metrics': {'valid': True, 'volumeMm3': volume, 'solidCount': len(solids), 'dimensionMm': dimensions}}


if __name__ == '__main__':
    try:
        # JSON escaping can expand an otherwise valid 64KB Unicode script.
        payload = json.loads(sys.stdin.read(524288))
        if os.name != 'nt':
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
            seconds = max(1, math.ceil(payload['timeout']))
            resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
            resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
        output = run(payload['script'])
    except Exception as exc:
        output = {'error': f'CAD construction failed: {str(exc)[:500]}'}
    print(json.dumps(output, allow_nan=False))
