"""A small, interpreted CAD language, executed in a resource-limited child.

This is deliberately not a Python sandbox: no supplied code reaches exec/eval.
Only reviewed CadQuery operations can be invoked by the worker interpreter.
"""
from __future__ import annotations

import ast
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


METHODS = frozenset('box cylinder sphere rect circle ellipse polygon polyline spline threePointArc radiusArc sagittaArc lineTo moveTo move line hLine vLine hLineTo vLineTo center close extrude revolve loft sweep twistExtrude cut union intersect cutThruAll cutBlind hole cboreHole cskHole shell fillet chamfer faces edges vertices workplane transformed translate rotate mirror mirrorX mirrorY pushPoints rarray polarArray toPending offset2D add combine clean'.split())
SCRIPT_GRAMMAR = '''Restricted CadQuery language (millimeters): start with `import cadquery as cq`.
Use only straight-line simple variable assignments; end with `result = <solid Workplane>`.
Expressions: finite numeric/string/bool/None literals, tuples/lists (up to 512 items), assigned
variables, numeric + - * / and unary +/-; cq.Workplane("XY"/"XZ"/"YZ") and modeling method
chains. No loops, functions, comprehensions, builtin calls, other imports, math module,
attribute reads, IO, exports, reflection, or indexing. Use numeric constants for pi/sin/cos.
Allowed Workplane methods: ''' + ', '.join(sorted(METHODS)) + '''.
Use Workplane boolean cut/union to make novel forms; chained selectors are supported.
No callbacks, tags, arbitrary objects or custom planes. Names may not start with underscore.
Maximum 128 assignments, 256 modeling calls, 64KB script. All values bounded to 1,000,000.
Return closed positive-volume solids; avoid disconnected parts unless requested.
The server measures and exports STEP and STL; do not export in the script.'''


class CadScriptError(ValueError):
    """Invalid CAD language, failed solid construction, or exhausted resource budget."""


def validate_script(script: str) -> ast.Module:
    if not isinstance(script, str) or len(script.encode('utf-8')) > 65536:
        raise CadScriptError('CAD script exceeds 64KB limit')
    try:
        tree = ast.parse(script)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise CadScriptError('Invalid CAD syntax') from exc
    if len(tree.body) > 129 or sum(1 for _ in ast.walk(tree)) > 6000:
        raise CadScriptError('CAD script complexity limit exceeded')
    names = set()
    calls = 0

    def expression(node, depth=0):
        nonlocal calls
        if depth > 80:
            raise CadScriptError('CAD expression depth limit exceeded')
        if isinstance(node, ast.Constant):
            value = node.value
            if value is None or type(value) is bool:
                return
            if type(value) in (int, float) and abs(value) <= 1e6 and math.isfinite(value):
                return
            if type(value) is str and len(value) <= 256:
                return
        elif isinstance(node, ast.Name) and node.id in names:
            return
        elif isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) <= 512:
            for item in node.elts:
                expression(item, depth + 1)
            return
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            expression(node.operand, depth + 1)
            return
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            expression(node.left, depth + 1)
            expression(node.right, depth + 1)
            return
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func = node.func
            if isinstance(func.value, ast.Name) and func.value.id == 'cq':
                if func.attr != 'Workplane':
                    raise CadScriptError('Only cq.Workplane is allowed')
            elif func.attr in METHODS:
                expression(func.value, depth + 1)
            else:
                raise CadScriptError('CAD method is not allowed')
            calls += 1
            if calls > 256:
                raise CadScriptError('CAD modeling call limit exceeded')
            for arg in node.args:
                expression(arg, depth + 1)
            for kw in node.keywords:
                if kw.arg is None or kw.arg.startswith('_'):
                    raise CadScriptError('Invalid CAD keyword argument')
                expression(kw.value, depth + 1)
            return
        raise CadScriptError('Expression is outside restricted CAD language')

    imported = False
    for statement in tree.body:
        if isinstance(statement, ast.Import) and not imported and not names:
            if len(statement.names) == 1 and statement.names[0].name == 'cadquery' and statement.names[0].asname == 'cq':
                imported = True
                continue
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
            raise CadScriptError('Only import cadquery as cq and simple assignments are allowed')
        name = statement.targets[0].id
        if name.startswith('_') or name == 'cq' or len(name) > 64:
            raise CadScriptError('Invalid CAD variable name')
        expression(statement.value)
        names.add(name)
    if not imported or 'result' not in names:
        raise CadScriptError('CAD script must import cadquery as cq and assign result')
    return tree


def _child_environment(temp_dir: str) -> dict[str, str]:
    # Explicit allowlist: no provider tokens, database configuration or Python hooks.
    env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR') if k in os.environ}
    env.update(TEMP=temp_dir, TMP=temp_dir, HOME=temp_dir, USERPROFILE=temp_dir,
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    return env


def _validated_exports(directory: Path, complete: bool = True) -> dict[str, Path]:
    paths = {suffix: directory / ('model.' + suffix) for suffix in ('stl', 'step')}
    for path in paths.values():
        if path.is_file():
            size = path.stat().st_size
            if size > 64 * 1024**2:
                raise CadScriptError('CAD export exceeds 64MB size limit')
            if complete and size == 0:
                raise CadScriptError('CAD export is empty')
        elif complete:
            raise CadScriptError('CAD export is missing')
    return paths


def _windows_job(process, timeout_s):
    """Assign before giving the worker input, so no CAD executes before limits apply."""
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

    class Extended(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.BasicLimitInformation.LimitFlags = 0x100 | 0x2000 | 0x2 | 0x8
    limits.BasicLimitInformation.PerProcessUserTimeLimit = max(1, int(timeout_s * 10000000))
    # Windows venv python.exe is a redirector that launches the base interpreter.
    limits.BasicLimitInformation.ActiveProcessLimit = 2
    limits.ProcessMemoryLimit = 2 * 1024**3
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, int(process._handle)):
        if job:
            kernel.CloseHandle(job)
        raise CadScriptError('Could not apply Windows CAD resource limits')
    return lambda: kernel.CloseHandle(job)


def build_script(script: str, out_dir: Path, timeout_s: int = 60) -> dict:
    if type(timeout_s) not in (int, float) or not 0 < timeout_s <= 120 or not math.isfinite(timeout_s):
        raise CadScriptError('CAD timeout must be positive and at most 120 seconds')
    validate_script(script)
    with tempfile.TemporaryDirectory(prefix='zaowu-cad-') as temp_dir:
        worker = Path(__file__).with_name('cad_worker.py').resolve()
        process = subprocess.Popen([sys.executable, '-I', str(worker)], cwd=temp_dir,
                                   env=_child_environment(temp_dir), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        close_job = None
        try:
            if os.name == 'nt':
                close_job = _windows_job(process, timeout_s)
            deadline = time.monotonic() + timeout_s
            input_data = json.dumps({'script': script, 'timeout': timeout_s})
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CadScriptError('CAD build exceeded time limit')
                try:
                    stdout, stderr = process.communicate(input_data, timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    input_data = None
                    # Also cap files while exporting on Windows, which has no
                    # RLIMIT_FSIZE. Never hand an enormous mesh to the API process.
                    _validated_exports(Path(temp_dir), complete=False)
            if process.returncode:
                raise CadScriptError('CAD worker failed or exceeded resource limits: ' + stderr[-500:])
            try:
                payload = json.loads(stdout)
            except ValueError as exc:
                raise CadScriptError('CAD worker returned invalid output') from exc
            if 'error' in payload:
                raise CadScriptError(payload['error'])
            exports = _validated_exports(Path(temp_dir))
            target = Path(out_dir)
            target.mkdir(parents=True, exist_ok=True)
            for suffix in ('stl', 'step'):
                source = exports[suffix]
                destination = target / source.name
                os.replace(source, destination)
                payload[suffix] = destination
            return payload
        finally:
            if process.poll() is None:
                process.kill()
            if close_job:
                close_job()
            process.communicate()
