"""精确 CAD：本地参数化模板（PRD §3.2、GEN-C08）。外部 API 调用 = 0。

几何内核使用 manifold3d（布尔运算保证流形）。STEP 导出需要 OpenCASCADE（cadquery/build123d），
未安装时只输出 STL/3MF/GLB，并在结果中注明。
"""
from __future__ import annotations

import re
import math

import trimesh
from manifold3d import CrossSection, Manifold, set_circular_segments

set_circular_segments(64)

TEMPLATES = {
    "nameplate": {"name": "铭牌", "version": "nameplate_v3",
                  "params": {"length": 80, "width": 30, "thickness": 4, "hole_d": 5, "hole_spacing": 58, "corner_r": 3}},
    "keychain": {"name": "钥匙扣", "version": "keychain_v2",
                 "params": {"length": 70, "width": 35, "thickness": 4, "hole_d": 5, "corner_r": 6}},
    "base": {"name": "圆形底座", "version": "base_v1",
             "params": {"diameter": 60, "height": 10, "chamfer": 1}},
    "box": {"name": "收纳盒", "version": "box_v1",
            "params": {"length": 90, "width": 60, "height": 35, "wall": 3, "lid_clearance": 0.3}},
}


def _rounded_rect(l: float, w: float, r: float) -> CrossSection:
    r = max(0.01, min(r, l / 2 - 0.01, w / 2 - 0.01))
    c = CrossSection.circle(r)
    pts = [c.translate([x, y]) for x in (-l / 2 + r, l / 2 - r) for y in (-w / 2 + r, w / 2 - r)]
    return CrossSection.batch_hull(pts)


def _to_trimesh(m: Manifold) -> trimesh.Trimesh:
    import numpy as np
    mesh = m.to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts))


def validate(kind: str, p: dict, material: dict) -> list[str]:
    if kind not in TEMPLATES:
        return ["未知模板"]
    p = {**TEMPLATES[kind]["params"], **p}
    invalid = [k for k, v in p.items() if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)]
    if invalid:
        return [f"参数 {k} 必须是有限数值" for k in invalid]
    errs = []
    t = p.get("thickness") or p.get("wall") or p.get("height")
    if t is not None and t < material["min_wall_mm"]:
        errs.append(f"厚度 {t} mm 小于{material['name']}最小壁厚 {material['min_wall_mm']} mm")
    if "hole_d" in p:
        if p["hole_d"] < material["min_hole_mm"]:
            errs.append(f"孔径 {p['hole_d']} mm 小于最小孔径 {material['min_hole_mm']} mm")
        if kind == "nameplate":
            edge = (p["length"] - p["hole_spacing"]) / 2 - p["hole_d"] / 2
            if edge < material["min_hole_edge_mm"]:
                errs.append(f"孔边距 {edge:.1f} mm 小于 {material['min_hole_edge_mm']} mm")
            if p["hole_d"] >= p["width"] - 2 * material["min_hole_edge_mm"]:
                errs.append("孔径相对宽度过大")
    for k, v in p.items():
        if v < 0 or (v == 0 and k not in ("corner_r", "chamfer")):
            errs.append(f"参数 {k} 必须大于 0")
    if "corner_r" in p and p["corner_r"] > min(p["length"], p["width"]) / 2:
        errs.append("圆角半径不能超过短边的一半")
    if kind in ("nameplate", "keychain"):
        if p["hole_d"] + 2 * material["min_hole_edge_mm"] > p["width"]:
            errs.append("孔径过大，宽度方向孔边距不足")
        if kind == "nameplate" and p["hole_spacing"] - p["hole_d"] < material["min_wall_mm"]:
            errs.append("两孔之间的壁厚不足")
        if kind == "keychain" and p["hole_d"] + 4 + material["min_hole_edge_mm"] > p["length"]:
            errs.append("孔径过大，长度方向孔边距不足")
    if kind == "base" and p["chamfer"] >= min(p["height"], p["diameter"] / 2):
        errs.append("倒角必须小于高度和半径")
    if kind == "box":
        if p["wall"] >= p["height"] or 2 * (p["wall"] + p["lid_clearance"]) >= min(p["length"], p["width"]):
            errs.append("壁厚或盖间隙过大，盒腔和盖塞必须保持正尺寸")
    dims = [v for k, v in p.items() if k in ("length", "width", "diameter", "height", "thickness")]
    if kind == "box":
        dims.append(2 * p["width"] + 12)  # box and lid share one exported layout
    if dims and max(dims) > material["max_size_mm"]:
        errs.append(f"尺寸超过{material['name']}上限 {material['max_size_mm']} mm")
    return errs


def build(kind: str, p: dict) -> trimesh.Trimesh:
    if kind == "nameplate":
        plate = Manifold.extrude(_rounded_rect(p["length"], p["width"], p["corner_r"]), p["thickness"])
        for sx in (-1, 1):
            hole = Manifold.cylinder(p["thickness"] + 2, p["hole_d"] / 2, p["hole_d"] / 2).translate([sx * p["hole_spacing"] / 2, 0, -1])
            plate = plate - hole
        return _to_trimesh(plate)
    if kind == "keychain":
        plate = Manifold.extrude(_rounded_rect(p["length"], p["width"], p["corner_r"]), p["thickness"])
        x = -p["length"] / 2 + p["hole_d"] / 2 + 4
        plate = plate - Manifold.cylinder(p["thickness"] + 2, p["hole_d"] / 2, p["hole_d"] / 2).translate([x, 0, -1])
        return _to_trimesh(plate)
    if kind == "base":
        r, h, c = p["diameter"] / 2, p["height"], p.get("chamfer", 0)
        body = Manifold.cylinder(h - c, r, r) + Manifold.cylinder(c, r, r - c).translate([0, 0, h - c]) if c > 0 else Manifold.cylinder(h, r, r)
        return _to_trimesh(body)
    if kind == "box":
        l, w, h, t, cl = p["length"], p["width"], p["height"], p["wall"], p["lid_clearance"]
        outer = Manifold.extrude(_rounded_rect(l, w, 4), h)
        inner = Manifold.extrude(_rounded_rect(l - 2 * t, w - 2 * t, 2), h).translate([0, 0, t])
        box = outer - inner
        lid = Manifold.extrude(_rounded_rect(l, w, 4), t) + Manifold.extrude(
            _rounded_rect(l - 2 * t - 2 * cl, w - 2 * t - 2 * cl, 2), 4).translate([0, 0, -4])
        lid = lid.translate([0, w + 12, 4])
        return _to_trimesh(box + lid)
    raise ValueError("未知模板")


_NUM = r"(\d+(?:\.\d+)?)\s*(?:mm|毫米)?"


def parse_text(text: str) -> tuple[str, dict, list[str]]:
    """自然语言 → 模板 + 参数。缺失关键尺寸返回提示（GEN-C01）。"""
    kind = "nameplate"
    if re.search(r"钥匙扣|挂件", text):
        kind = "keychain"
    elif re.search(r"底座", text):
        kind = "base"
    elif re.search(r"盒", text):
        kind = "box"
    p = dict(TEMPLATES[kind]["params"])
    found = []

    def grab(pattern, key, conv=float):
        m = re.search(pattern, text)
        if m:
            p[key] = conv(m.group(1))
            found.append(key)

    grab(_NUM + r"\s*长", "length"); grab(r"长\s*" + _NUM, "length")
    grab(_NUM + r"\s*宽", "width"); grab(r"宽\s*" + _NUM, "width")
    grab(_NUM + r"\s*厚", "thickness"); grab(r"厚\s*" + _NUM, "thickness")
    grab(r"(?:直径|孔径|⌀)\s*" + _NUM, "hole_d"); grab(_NUM + r"\s*(?:的)?(?:对称)?(?:圆)?孔", "hole_d")
    grab(r"(?:中心距|孔距)\s*" + _NUM, "hole_spacing")
    grab(r"壁厚\s*" + _NUM, "wall"); grab(r"高\s*" + _NUM, "height"); grab(_NUM + r"\s*高", "height")
    m = re.search(r"(\d+(?:\.\d+)?)\s*[×xX*]\s*(\d+(?:\.\d+)?)(?:\s*[×xX*]\s*(\d+(?:\.\d+)?))?", text)
    if m:
        p["length"], p["width"] = float(m.group(1)), float(m.group(2))
        if m.group(3):
            p["thickness" if kind in ("nameplate", "keychain") else "height"] = float(m.group(3))
        found += ["length", "width"]
    if kind == "nameplate" and "hole_spacing" not in found and "length" in found:
        p["hole_spacing"] = round(p["length"] - 2 * max(11.0, p.get("hole_d", 5) * 2.2), 1)
    if kind == "base":
        grab(r"(?:直径)\s*" + _NUM, "diameter")
    p = {k: p[k] for k in TEMPLATES[kind]["params"]}
    missing = [k for k in (("diameter", "height") if kind == "base" else ("length", "width")) if k in p and k not in found]
    return kind, p, missing
