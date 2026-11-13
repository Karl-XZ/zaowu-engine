import math
from pathlib import Path

import pytest

from app.services.cad_sandbox import CadScriptError, build_script, validate_script, _child_environment


@pytest.mark.parametrize('script', [
    'import os\nresult = os.getcwd()',
    'import cadquery as cq\nresult = cq.__dict__',
    'import cadquery as cq\nresult = cq.Workplane("XY").__class__',
    'result = open("secret")',
    'while True: pass',
    'x = [x for x in range(100)]',
    'import cadquery as cq\nresult = cq.Workplane("XY").export("stolen.step")',
    'x = "a" * 100000000',
    'x = 10 ** 1000000',
    'x = 1e300',
    'x = ' + '9' * 1000,
    'import cadquery as cq\nresult = cq.Workplane("XY").box(1,1,1)\nprint(result)',
])
def test_rejects_unsafe_or_unbounded_language(script, tmp_path):
    with pytest.raises(CadScriptError):
        build_script(script, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_rejects_script_and_timeout_resource_overflow(tmp_path):
    with pytest.raises(CadScriptError):
        validate_script('x = 1\n' * 10000)
    for timeout in (0, -1, 121, float('inf')):
        with pytest.raises(CadScriptError):
            build_script('result = 1', tmp_path, timeout_s=timeout)


def test_real_kernel_exports_same_box_with_hole(tmp_path):
    artifact = build_script('''import cadquery as cq
width = 20
result = cq.Workplane("XY").box(width, 30, 10).faces(">Z").workplane().hole(6)
''', tmp_path)
    assert artifact['metrics']['valid'] is True
    assert artifact['metrics']['solidCount'] == 1
    assert artifact['metrics']['dimensionMm'] == pytest.approx([20, 30, 10])
    assert artifact['metrics']['volumeMm3'] == pytest.approx(6000 - math.pi * 9 * 10)
    assert artifact['stl'].stat().st_size > 100
    assert 'ISO-10303-21' in artifact['step'].read_text()
    import cadquery as cq
    reimported = cq.importers.importStep(str(artifact['step'])).val()
    assert reimported.Volume() == pytest.approx(artifact['metrics']['volumeMm3'])


@pytest.mark.parametrize('body', [
    'base = cq.Workplane("XY").box(60,70,4,centered=(True,True,False))\nback = cq.Workplane("XY").box(60,4,80).rotate((0,0,0),(1,0,0),20).translate((0,20,38))\nlip = cq.Workplane("XY").box(60,5,12).translate((0,-27,7))\nresult = base.union(back).union(lip)',
    'result = cq.Workplane("XY").polyline([(0,0),(60,0),(60,4),(4,4),(4,45),(0,45)]).close().extrude(25).edges("|Z").fillet(1)',
    'result = cq.Workplane("XY").circle(25).circle(22).extrude(55).union(cq.Workplane("XY").circle(25).extrude(3)).cut(cq.Workplane("XY").box(4,60,35).translate((0,0,35)))',
    'result = cq.Workplane("XZ").polyline([(0,0),(30,0),(30,4),(5,4),(5,40),(0,40)]).close().revolve(360,(0,0),(0,1))',
])
def test_novel_phone_stand_polygons_slotted_cup_and_revolve(body, tmp_path):
    output = build_script('import cadquery as cq\n' + body, tmp_path)
    assert output['metrics']['valid']
    assert output['metrics']['volumeMm3'] > 0


def test_rejects_non_solid_result(tmp_path):
    with pytest.raises(CadScriptError):
        build_script('import cadquery as cq\nresult = cq.Workplane("XY").rect(10,10)', tmp_path)


def test_worker_deadline_terminates_process(tmp_path):
    with pytest.raises(CadScriptError, match='time'):
        build_script('import cadquery as cq\nresult = cq.Workplane("XY").box(2,2,2)', tmp_path, timeout_s=0.001)
    assert list(tmp_path.iterdir()) == []


def test_worker_environment_excludes_credentials_and_python_hooks(monkeypatch, tmp_path):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'must-never-reach-worker')
    monkeypatch.setenv('UNRECOGNIZED_NEW_PROVIDER_TOKEN', 'also-secret')
    monkeypatch.setenv('PYTHONPATH', 'malicious-startup-hook')
    environment = _child_environment(str(tmp_path))
    assert not any('secret' in value or 'must-never' in value or 'malicious' in value for value in environment.values())
    assert environment['TEMP'] == str(tmp_path)


def test_rejects_giant_integer_timeout(tmp_path):
    with pytest.raises(CadScriptError):
        build_script('import cadquery as cq\nresult = 1', tmp_path, timeout_s=10**1000)


def test_unicode_identifiers_survive_isolated_worker_transport(tmp_path):
    # Under the 64KB source limit, even when JSON escapes expand the transport.
    descriptions = ('说明 = "' + '测' * 250 + '"\n') * 80
    artifact = build_script('import cadquery as cq\n' + descriptions + '宽度 = 12\nresult = cq.Workplane("XY").box(宽度,3,4)', tmp_path)
    assert artifact['metrics']['volumeMm3'] == pytest.approx(144)


def test_large_native_exports_cannot_escape_worker_memory_boundary(tmp_path):
    from app.services import cad_sandbox
    (tmp_path / 'model.step').write_bytes(b'ISO-10303-21')
    with (tmp_path / 'model.stl').open('wb') as oversized:
        oversized.truncate(64 * 1024**2 + 1)
    with pytest.raises(CadScriptError, match='size limit'):
        cad_sandbox._validated_exports(tmp_path)


def test_empty_or_missing_export_is_not_publishable(tmp_path):
    from app.services import cad_sandbox
    (tmp_path / 'model.step').write_bytes(b'')
    with pytest.raises(CadScriptError):
        cad_sandbox._validated_exports(tmp_path)


def test_kernel_failure_identifies_operation_for_one_shot_repair(tmp_path):
    with pytest.raises(CadScriptError, match='polyline|close|extrude'):
        build_script('import cadquery as cq\nresult = cq.Workplane("XY").polyline([(0,0),(0,0),(0,0)]).close().extrude(3)', tmp_path)
