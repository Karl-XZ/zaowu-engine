"""Prompt Compiler（PRD §3.5、附录 C）：用户原文不直接作为供应商提示词。

分离：用户需求 / 工艺硬约束 / 构图要求 / 风格。模板带版本号，便于回归测试与 A/B。
"""
from __future__ import annotations

import re

from .preflight import classify_dimension, detect_category

CONCEPT_TEMPLATE_VERSION = "concept_v1"
LUX3D_TEMPLATE_VERSION = "lux3d_v1"

COLOR_WORDS = {
    "暖粉": "warm pink", "粉": "pink", "红": "red", "蓝": "blue", "天蓝": "sky blue", "绿": "green", "黄": "yellow",
    "紫": "purple", "黑": "black", "白": "white", "金": "gold", "银": "silver", "橙": "orange", "灰": "grey", "棕": "brown",
}
STYLE_WORDS = {
    "黏土": "soft clay", "粘土": "soft clay", "水彩": "watercolor-painted", "像素": "voxel pixel", "写实": "realistic",
    "卡通": "cartoon", "赛博": "cyberpunk", "手绘": "hand-painted", "陶瓷": "glazed ceramic", "毛绒": "plush",
    "金属": "brushed metal", "复古": "retro", "极简": "minimalist",
}


def build_spec(text: str, material: dict, size_mm: float, purpose: str = "桌面摆件") -> dict:
    category = detect_category(text)
    return {
        "category": category,
        "subject": text.strip(),
        "sizeHeightMm": size_mm,
        "materialProfile": material["profile_version"],
        "colorMode": "color" if material["color"] else "monochrome",
        "purpose": purpose,
        "style": "cartoon",
        "color": None,
        "shapeNotes": [],
        "connectedBase": category in ("figurine",),
        "hangHole": category in ("keychain",),
        "hardConstraints": [
            "single connected object", "no floating parts", "no ultra-thin features",
            f"min wall {material['min_wall_mm']} mm", "stable integrated base" if category == "figurine" else "flat stable back",
        ],
    }


def hard_checklist(spec: dict, material: dict) -> list[dict]:
    subj = re.split(r"[，,。；;]", spec["subject"])[0][:24]
    items = [
        {"key": "subject", "label": "主体", "value": subj},
        {"key": "structure", "label": "结构", "value": "一体底座" if spec["connectedBase"] else ("挂孔" if spec["hangHole"] else "一体成型")},
        {"key": "size", "label": "尺寸", "value": f"H {spec['sizeHeightMm']:g} ± 2 mm"},
        {"key": "color", "label": "色彩", "value": "全彩" if material["color"] else "单色（材料本色）"},
    ]
    return items


def apply_instruction(spec: dict, instruction: str) -> tuple[dict, str]:
    """把一次对话调整合并进规格；只修改涉及的维度，保持主体一致（GEN-A14）。"""
    spec = {**spec, "shapeNotes": list(spec.get("shapeNotes", []))}
    dim = classify_dimension(instruction)
    if "颜色" in dim:
        for zh, en in sorted(COLOR_WORDS.items(), key=lambda kv: -len(kv[0])):
            if zh in instruction:
                spec["color"] = en
                break
    if "风格" in dim:
        for zh, en in STYLE_WORDS.items():
            if zh in instruction:
                spec["style"] = en
                break
    if "造型" in dim:
        spec["shapeNotes"].append(instruction.strip())
    return spec, dim


def concept_prompt(spec: dict) -> str:
    notes = "; ".join(spec.get("shapeNotes", [])) or "none"
    color = spec.get("color") or "natural harmonious colors"
    base = "standing on a stable integrated base" if spec.get("connectedBase") else ("with a sturdy hang hole" if spec.get("hangHole") else "with a flat stable back")
    return (
        f"Product render of a single collectible {spec['style']} 3D figurine: {spec['subject']}. "
        f"{base}. Approved adjustments: {notes}. Main color: {color}. "
        "One isolated object, fully visible, three-quarter view, centered, soft studio lighting, clean light neutral background, "
        "no scenery, no extra characters, no text overlay. All parts physically attached with wide sturdy connections; "
        "no floating pieces, no thin wires, no fragile antennae, compact silhouette suitable for 3D printing."
    )


def lux3d_prompt(spec: dict) -> str:
    """需要文字约束时使用文生 3D 的 img + prompt 接口（纯图生 3D 无公开 prompt 字段，GEN-A10）。"""
    return (
        f"{spec['subject']} as a single collectible {spec['style']} 3D figurine, approximately {spec['sizeHeightMm']:g} mm tall, "
        f"intended for {spec['materialProfile']} 3D printing. Use a stable integrated base. Attach all important features with wide, "
        "sturdy connections. Avoid isolated floating pieces, fragile wires, extremely thin accessories, deep inaccessible gaps and tiny "
        "overhanging details. Single isolated object; no scenery. This prompt expresses design preferences only; wall thickness, "
        "watertightness, sizing and manufacturability are verified independently after generation."
    )


def summary(spec: dict) -> str:
    parts = []
    if spec.get("shapeNotes"):
        parts.append(spec["shapeNotes"][-1][:10])
    rev = {v: k for k, v in STYLE_WORDS.items()}
    if spec.get("style") and spec["style"] != "cartoon":
        parts.append(rev.get(spec["style"], spec["style"]))
    crev = {v: k for k, v in COLOR_WORDS.items()}
    if spec.get("color"):
        parts.append(crev.get(spec["color"], spec["color"]))
    return " · ".join(parts) or "初始方案"
