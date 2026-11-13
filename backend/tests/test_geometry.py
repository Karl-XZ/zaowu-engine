import io

import numpy as np
import pytest
import trimesh

from app.services import cad_templates as cad, mesh_pipeline as pipeline, storage
from app.services.materials import MATERIALS


@pytest.mark.parametrize("height", [0, -1, float("inf")])
def test_scaling_rejects_invalid_target_height(height):
    with pytest.raises(ValueError):
        pipeline.scale_to_height(trimesh.creation.box(), height)


def test_glb_scene_keeps_instance_transforms_and_source_preview():
    scene = trimesh.Scene()
    scene.add_geometry(trimesh.creation.box([2, 3, 4]), transform=trimesh.transformations.translation_matrix([10, 0, 0]))
    mesh = pipeline.load_glb(scene.export(file_type="glb"))
    assert mesh.extents == pytest.approx([2, 4, 3])
    assert mesh.centroid[0] == pytest.approx(10)
    assert getattr(mesh, "_source_scene", None) is not None


@pytest.mark.parametrize("kind,changes", [
    ("nameplate", {"corner_r": 40}),
    ("nameplate", {"hole_spacing": 2}),
    ("nameplate", {"length": float("nan")}),
    ("nameplate", {"thickness": 300}),
    ("keychain", {"hole_d": 30}),
    ("base", {"chamfer": 11}),
    ("box", {"wall": 31}),
    ("box", {"lid_clearance": 40}),
    ("box", {"width": 110}),
])
def test_invalid_cad_geometry_is_rejected(kind, changes):
    p = {**cad.TEMPLATES[kind]["params"], **changes}
    assert cad.validate(kind, p, MATERIALS["mono_resin"])


def test_base_parser_reports_missing_diameter_and_keeps_decimal_height():
    kind, params, missing = cad.parse_text("圆形底座，高 12.35 mm")
    assert kind == "base"
    assert params["height"] == 12.35
    assert "diameter" in missing


def test_processed_glb_keeps_original_material_and_scales_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    source = trimesh.creation.box([20, 30, 20])
    source.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(baseColorFactor=[10, 200, 30, 255]))
    mesh = pipeline.load_glb(source.export(file_type="glb"))
    result = pipeline.process(mesh, MATERIALS["mono_resin"], 60, "textured")
    assert result["passed"], result["report"]
    preview = trimesh.load(storage.path_for(result["files"]["glb"]), force="scene")
    assert preview.extents == pytest.approx([40, 60, 40])
    material = next(iter(preview.geometry.values())).visual.material
    assert list(material.baseColorFactor) == [10, 200, 30, 255]


def test_repair_welds_uv_islands_without_losing_the_solid():
    source = trimesh.creation.box([20, 30, 40])
    vertices = source.vertices[source.faces].reshape((-1, 3))
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.arange(len(vertices)).reshape((-1, 3)), process=False)
    mesh.visual = trimesh.visual.TextureVisuals(uv=np.arange(len(vertices) * 2).reshape((-1, 2)) / 100)
    assert not mesh.is_watertight
    repaired, actions = pipeline.repair(mesh)
    assert repaired.is_watertight, actions
    assert len(repaired.split()) == 1
    assert repaired.extents == pytest.approx([20, 30, 40])
    assert repaired.volume == pytest.approx(20 * 30 * 40)


def test_glb_welds_uv_islands_before_topology_checks():
    source = trimesh.creation.box([20, 30, 40])
    vertices = source.vertices[source.faces].reshape((-1, 3))
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.arange(len(vertices)).reshape((-1, 3)), process=False)
    mesh.visual = trimesh.visual.TextureVisuals(uv=np.arange(len(vertices) * 2).reshape((-1, 2)) / 100)
    loaded = pipeline.load_glb(mesh.export(file_type="glb"))
    assert loaded.is_watertight
    assert len(loaded.split()) == 1


@pytest.mark.parametrize("kind", list(cad.TEMPLATES))
def test_default_cad_delivers_watertight_unscaled_files(kind, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    params = dict(cad.TEMPLATES[kind]["params"])
    mesh = cad.build(kind, params)
    extents = mesh.extents.copy()
    result = pipeline.process(mesh, MATERIALS["mono_resin"], None, kind, expected_bodies=2 if kind == "box" else 1)
    assert result["passed"], result["report"]
    assert result["mesh"].extents == pytest.approx(extents)
    assert result["report"]["slice"]["estimated"] is True
    exported = trimesh.load(io.BytesIO(storage.path_for(result["files"]["stl"]).read_bytes()), file_type="stl")
    assert exported.is_watertight
    assert np.isfinite(exported.vertices).all()
