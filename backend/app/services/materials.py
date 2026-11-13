"""材料/工艺档案（PRD §4.2、§4.4）。数值依据嘉立创公开设计规范的保守取值，须随官方规范更新并升版本号。"""
from __future__ import annotations

MATERIALS: dict[str, dict] = {
    "mono_resin": {
        "id": "mono_resin",
        "name": "单色树脂",
        "profile_version": "mono_resin_v1",
        "validated": True,
        "color": False,
        "min_wall_mm": 2.0,
        "min_feature_mm": 1.2,
        "min_text_stroke_mm": 0.8,
        "min_hole_mm": 2.0,
        "min_hole_edge_mm": 3.0,
        "min_size_mm": 15,
        "max_size_mm": 200,
        "first_layer_min_area_mm2": 60,
        "density_g_cm3": 1.2,
        "note": "打印件为材料本色，效果图中的颜色不会印到成品上。",
    },
    "color_resin": {
        "id": "color_resin",
        "name": "全彩树脂",
        "profile_version": "color_resin_v1",
        "validated": True,
        "color": True,
        "min_wall_mm": 2.0,
        "min_feature_mm": 2.0,
        "min_text_stroke_mm": 1.0,
        "min_hole_mm": 2.5,
        "min_hole_edge_mm": 3.0,
        "min_size_mm": 20,
        "max_size_mm": 160,
        "first_layer_min_area_mm2": 80,
        "density_g_cm3": 1.25,
        "note": "全彩文创件易损，悬空与细小结构建议 ≥ 2 mm。",
    },
    "nylon": {
        "id": "nylon",
        "name": "尼龙",
        "profile_version": "nylon_draft",
        "validated": False,
        "color": False,
        "min_wall_mm": 1.5,
        "min_feature_mm": 1.0,
        "min_text_stroke_mm": 0.8,
        "min_hole_mm": 2.0,
        "min_hole_edge_mm": 2.5,
        "min_size_mm": 15,
        "max_size_mm": 250,
        "first_layer_min_area_mm2": 50,
        "density_g_cm3": 1.0,
        "note": "验证中，暂不开放。",
    },
}


def get_material(mid: str) -> dict:
    m = MATERIALS.get(mid)
    if not m:
        raise ValueError("未知材料")
    if not m["validated"]:
        raise ValueError(f"{m['name']}仍在验证中，暂不开放")
    return m


def public_materials() -> list[dict]:
    return [{k: v for k, v in m.items()} for m in MATERIALS.values()]
