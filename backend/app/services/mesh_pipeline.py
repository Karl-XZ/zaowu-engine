"""网格修复 + 制造预检 + 切片 + 导出（PRD §4.3、§4.5、§4.9）。

不可测即阻断：修复后仍非水密、采样不足等情况，结果为 failed，绝不默认通过。
"""
from __future__ import annotations

import io
import json

import numpy as np
import trimesh

from . import slicer, storage


def load_glb(data: bytes) -> trimesh.Trimesh:
    scene = trimesh.load(io.BytesIO(data), file_type="glb", force="scene")
    # dump applies scene graph transforms, including multiple instances on older trimesh.
    mesh = trimesh.util.concatenate(tuple(scene.dump())) if isinstance(scene, trimesh.Scene) else scene
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
        raise ValueError("GLB 不含有效三角网格")
    mesh.merge_vertices(merge_tex=True, merge_norm=True)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))  # glTF Y-up → Z-up
    mesh._source_scene = scene
    return mesh


def repair(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, list[str]]:
    actions: list[str] = []
    before_faces = len(mesh.faces)
    before_vertices = len(mesh.vertices)
    # Manufacturing topology ignores UV/normal seams; the source scene keeps its materials.
    mesh.merge_vertices(merge_tex=True, merge_norm=True)
    if len(mesh.vertices) < before_vertices:
        actions.append(f"合并几何接缝顶点 {before_vertices - len(mesh.vertices)} 个")
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces) != before_faces:
        actions.append(f"清理退化/重复面 {before_faces - len(mesh.faces)} 个")
    if not mesh.is_winding_consistent:
        trimesh.repair.fix_winding(mesh)
        actions.append("修正法线朝向")
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
        actions.append("闭合孔洞")
    if not mesh.is_watertight:
        try:  # 用 manifold3d 重建流形
            from manifold3d import Manifold, Mesh
            m = Manifold(Mesh(vert_properties=np.asarray(mesh.vertices, np.float32), tri_verts=np.asarray(mesh.faces, np.uint32)))
            if not m.is_empty():
                out = m.to_mesh()
                mesh = trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts))
                actions.append("流形重建")
        except Exception:
            pass
    if mesh.volume < 0:
        mesh.invert()
        actions.append("翻转内外")
    # 去除微小孤立壳体
    parts = mesh.split(only_watertight=False)
    if len(parts) > 1:
        big = max(parts, key=lambda p: abs(p.volume) if p.is_watertight else p.area)
        tiny = [p for p in parts if p is not big and (abs(p.volume) if p.is_watertight else 0) < abs(big.volume) * 0.002]
        if tiny:
            keep = [p for p in parts if not any(p is t for t in tiny)]
            mesh = trimesh.util.concatenate(keep)
            actions.append(f"移除孤立碎片 {len(tiny)} 个")
    return mesh, actions


def scale_to_height(mesh: trimesh.Trimesh, height_mm: float) -> trimesh.Trimesh:
    if not np.isfinite(height_mm) or height_mm <= 0:
        raise ValueError("目标高度必须是大于零的有限数值")
    h = mesh.extents[2]
    if not np.isfinite(h) or h <= 0:
        raise ValueError("模型高度无效，无法缩放")
    mesh.apply_scale(height_mm / h)
    return center(mesh)


def center(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    c = mesh.bounds.mean(axis=0)
    mesh.apply_translation([-c[0], -c[1], -mesh.bounds[0][2]])
    return mesh


def wall_thickness(mesh: trimesh.Trimesh, samples: int = 900) -> dict:
    """射线法：表面采样点沿反法线求对侧距离。返回 min / P1 / P5（mm）。"""
    try:
        pts, fidx = trimesh.sample.sample_surface_even(mesh, samples)
    except Exception:
        pts, fidx = trimesh.sample.sample_surface(mesh, samples)
    if len(pts) < samples * 0.5:
        return {"measurable": False, "reason": "采样覆盖不足"}
    normals = mesh.face_normals[fidx]
    origins = pts - normals * 1e-3
    locs, ray_idx, _ = mesh.ray.intersects_location(origins, -normals, multiple_hits=False)
    if len(ray_idx) < len(pts) * 0.8:
        return {"measurable": False, "reason": "射线命中率不足，网格可能非封闭"}
    d = np.linalg.norm(locs - origins[ray_idx], axis=1)
    d = d[d > 1e-3]
    if len(d) == 0:
        return {"measurable": False, "reason": "无有效厚度样本"}
    thin_pts = origins[ray_idx][np.linalg.norm(locs - origins[ray_idx], axis=1) < np.percentile(d, 1)]
    return {
        "measurable": True, "samples": int(len(d)),
        "minMm": round(float(d.min()), 2), "p1Mm": round(float(np.percentile(d, 1)), 2),
        "p5Mm": round(float(np.percentile(d, 5)), 2), "medianMm": round(float(np.median(d)), 2),
        "thinSpots": thin_pts[:20].round(2).tolist(),
    }


def check(mesh: trimesh.Trimesh, material: dict, target_h: float, tol: float = 2.0, expected_bodies: int = 1) -> dict:
    items = []

    def add(key, label, ok, value, level="block"):
        items.append({"key": key, "label": label, "ok": bool(ok), "value": value, "level": level})

    add("watertight", "水密 · 流形", mesh.is_watertight and mesh.is_winding_consistent,
        "通过" if mesh.is_watertight else "存在开口")
    add("volume", "非零体积", mesh.is_watertight and mesh.volume > 1, f"{abs(mesh.volume) / 1000:.2f} cm³")
    ext = mesh.extents
    add("size", "外形尺寸", abs(ext[2] - target_h) <= tol and ext.max() <= material["max_size_mm"],
        f"{ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f} mm")
    comps = len(mesh.split(only_watertight=False))
    add("bodies", "连通 · 实体数", comps == expected_bodies, f"{comps} 个实体")
    wt = wall_thickness(mesh) if mesh.is_watertight else {"measurable": False, "reason": "非水密，无法测量"}
    if wt.get("measurable"):
        add("wall", f"最小壁厚（P5，≥{material['min_wall_mm']}）", wt["p5Mm"] >= material["min_wall_mm"], f"{wt['p5Mm']} mm")
        add("feature", f"细小特征（P1，≥{material['min_feature_mm']}）", wt["p1Mm"] >= material["min_feature_mm"], f"{wt['p1Mm']} mm")
    else:
        add("wall", "壁厚", False, f"不可测：{wt.get('reason')}")
    passed = all(i["ok"] for i in items if i["level"] == "block")
    return {"passed": passed, "items": items, "wall": wt, "dimensionMm": [round(float(x), 2) for x in ext]}


def process(mesh: trimesh.Trimesh, material: dict, target_h: float | None, out_prefix: str, expected_bodies: int = 1) -> dict:
    """完整流水线；返回报告与文件。最多两轮修复。target_h=None 表示 CAD 精确尺寸，不缩放。"""
    scale = target_h is not None
    source_scene = getattr(mesh, "_source_scene", None)
    if source_scene is not None:
        source_scene = source_scene.copy()
        source_scene.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        if scale and mesh.extents[2] > 0 and np.isfinite(target_h) and target_h > 0:
            source_scene.apply_scale(target_h / mesh.extents[2])
        bounds = source_scene.bounds
        source_scene.apply_translation([-bounds.mean(axis=0)[0], -bounds.mean(axis=0)[1], -bounds[0][2]])
    mesh = scale_to_height(mesh, target_h) if scale else center(mesh)
    target_h = target_h if scale else float(mesh.extents[2])
    report = check(mesh, material, target_h, expected_bodies=expected_bodies)
    actions: list[str] = []
    for _ in range(2):
        if report["passed"]:
            break
        mesh, acts = repair(mesh)
        mesh = scale_to_height(mesh, target_h) if scale else center(mesh)
        actions += acts
        report = check(mesh, material, target_h, expected_bodies=expected_bodies)
    slice_rep = slicer.slice_check(mesh, material) if report["passed"] else {"result": "skipped"}
    if report["passed"] and slice_rep.get("result") != "passed":
        report["passed"] = False
    files = {}
    if report["passed"]:
        files["stl"] = storage.save_bytes(f"{out_prefix}/model.stl", mesh.export(file_type="stl"))
        try:
            files["3mf"] = storage.save_bytes(f"{out_prefix}/model.3mf", mesh.export(file_type="3mf"))
        except Exception:
            pass
    preview = source_scene if source_scene is not None else mesh.copy()
    preview.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
    files["glb"] = storage.save_bytes(f"{out_prefix}/preview.glb", preview.export(file_type="glb"))
    full = {"check": report, "repairs": actions, "slice": slice_rep, "materialProfile": material["profile_version"],
            "preview": "source_materials" if source_scene is not None else "processed_mesh",
            "limitations": ["几何预检不保证可制造性，请由生产商复核", "预览保留原始外观；生产文件使用修复后的网格"] if source_scene is not None else ["几何预检不保证可制造性，请由生产商复核"]}
    files["report"] = storage.save_bytes(f"{out_prefix}/report.json", json.dumps(full, ensure_ascii=False, indent=2).encode())
    return {"passed": report["passed"], "report": full, "files": files, "mesh": mesh,
            "hash": storage.sha256_file(files["stl"]) if "stl" in files else ""}
