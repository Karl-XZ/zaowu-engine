"""切片检查（PRD §4.9）。配置 SLICER_CLI_PATH 时调用 OrcaSlicer/PrusaSlicer 命令行；否则使用几何估算（结果标注 estimated）。"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import trimesh

from ..config import settings


def slice_check(mesh: trimesh.Trimesh, material: dict) -> dict:
    if settings.slicer_cli_path and Path(settings.slicer_cli_path).exists():
        try:
            return _cli(mesh, material)
        except Exception as e:  # 切片器异常不应伪装成通过
            return {"slicer": "cli", "result": "failed", "error": str(e)[:300], "estimated": False}
    return _estimate(mesh, material)


def _estimate(mesh: trimesh.Trimesh, material: dict) -> dict:
    zmin = mesh.bounds[0][2]
    # 首层接触面积：底部 0.3 mm 内、法线朝下的面
    centers, normals, areas = mesh.triangles_center, mesh.face_normals, mesh.area_faces
    base = (centers[:, 2] < zmin + 0.3) & (normals[:, 2] < -0.9)
    first_layer = float(areas[base].sum())
    # 悬垂：法线与 -Z 夹角 < 45° 且不在底面
    over = (normals[:, 2] < -0.707) & ~base
    overhang_area = float(areas[over].sum())
    support_cm3 = round(overhang_area * 0.6 / 1000, 2)
    vol_cm3 = abs(mesh.volume) / 1000
    height = float(mesh.extents[2])
    layers = int(np.ceil(height / 0.1))
    minutes = int(layers * 0.12 + vol_cm3 * 2.5 + support_cm3 * 3)
    ok = first_layer >= material["first_layer_min_area_mm2"]
    return {
        "slicer": "estimate", "estimated": True, "result": "passed" if ok else "failed",
        "firstLayerAreaMm2": round(first_layer, 1), "firstLayerMinMm2": material["first_layer_min_area_mm2"],
        "supportVolumeCm3": support_cm3, "overhangAreaMm2": round(overhang_area, 1),
        "layers": layers, "layerHeightMm": 0.1, "printTimeMin": minutes,
        "materialG": round(vol_cm3 * material["density_g_cm3"], 1),
        "error": "" if ok else "首层接触面积不足，模型可能立不稳或打印失败",
    }


def _cli(mesh: trimesh.Trimesh, material: dict) -> dict:
    with tempfile.TemporaryDirectory() as d:
        stl = Path(d) / "m.stl"
        mesh.export(stl)
        out = Path(d) / "m.gcode"
        proc = subprocess.run([settings.slicer_cli_path, "--export-gcode", "--output", str(out), str(stl)],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode != 0 or not out.exists():
            return {"slicer": "cli", "result": "failed", "error": proc.stderr[-300:], "estimated": False}
        g = out.read_text(errors="ignore")
        t = re.search(r"estimated printing time.*?=\s*(.+)", g)
        fil = re.search(r"filament used \[g\]\s*=\s*([\d.]+)", g)
        est = _estimate(mesh, material)
        est.update({"slicer": "cli", "estimated": False, "printTimeText": t.group(1).strip() if t else "",
                    "materialG": float(fil.group(1)) if fil else est["materialG"]})
        return est
