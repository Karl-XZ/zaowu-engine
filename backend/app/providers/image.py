"""设计效果图生成：Aholo 多模态单图异步接口；配置 IMAGE_PROVIDER=aholo 和地区 API 凭证。

MOCK 模式用 Pillow 绘制示意效果图，颜色/风格/造型随对话调整变化，保证流程可演示。
"""
from __future__ import annotations

import io
import math

import httpx
from PIL import Image, ImageDraw, ImageFilter

from ..config import settings
from . import aholo_client

COLOR_RGB = {
    "warm pink": (238, 150, 139), "pink": (240, 160, 180), "red": (213, 43, 30), "blue": (90, 140, 220),
    "sky blue": (130, 190, 235), "green": (110, 180, 120), "yellow": (240, 200, 80), "purple": (160, 120, 200),
    "black": (60, 55, 52), "white": (240, 236, 228), "gold": (220, 180, 70), "silver": (190, 195, 200),
    "orange": (240, 140, 60), "grey": (150, 150, 150), "brown": (160, 110, 75),
}


class ImageResult:
    def __init__(self, png: bytes, provider: str, cost_fen: int, task_id: str | None = None):
        self.png, self.provider, self.cost_fen = png, provider, cost_fen
        self.task_id = task_id
        self.actual_cost_known = False
        self.cost_is_estimate = True


def generate(prompt: str, spec: dict, reference_png: bytes | None = None, *, on_task_created=None) -> ImageResult:
    if settings.image_mock:
        return ImageResult(_mock_render(spec), "mock", settings.cost_concept_image_fen)
    return _real_generate(prompt, reference_png, on_task_created=on_task_created)


def _real_generate(prompt: str, reference_png: bytes | None, *, on_task_created=None) -> ImageResult:
    if settings.image_provider.lower() != "aholo":
        raise aholo_client.AholoError("Unsupported image provider; configure IMAGE_PROVIDER=aholo")
    with httpx.Client(timeout=60) as client:
        payload = {"prompt": prompt}
        if reference_png:
            payload["img"] = aholo_client.upload_image(client, settings.image_api_base, settings.image_api_key, reference_png)
        task_id = aholo_client.create(client, settings.image_api_base, settings.image_api_key, "multimodal-to-image", payload)
        if on_task_created is not None:
            try:
                on_task_created(task_id)
            except Exception as exc:
                error = aholo_client.AholoCreateUncertain(f"Aholo task {task_id} was created but local persistence failed; do not retry creation")
                error.task_id = task_id
                raise error from exc
        data = aholo_client.wait_for(client, settings.image_api_base, settings.image_api_key, task_id, 600)
        if str(data["status"]) != "3":
            raise aholo_client.AholoError(f"Aholo image task {task_id} failed or was cancelled")
        urls = aholo_client.output_urls(data)
        if not urls:
            raise aholo_client.AholoError(f"Aholo image task {task_id} has no image URL")
        content = aholo_client.download_bytes(client, urls[0], aholo_client.MAX_IMAGE_BYTES)
    try:
        with Image.open(io.BytesIO(content)) as generated:
            if generated.width * generated.height > 25_000_000:
                raise ValueError("Image exceeds pixel limit")
            out = io.BytesIO()
            generated.convert("RGB").save(out, "PNG")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise aholo_client.AholoError(f"Aholo task {task_id} returned an invalid image") from exc
    return ImageResult(out.getvalue(), "aholo", settings.cost_concept_image_fen, task_id=task_id)


# ---------------- MOCK 渲染 ----------------
def _shade(base: tuple[int, int, int], k: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * k))) for c in base)


def _ball(img: Image.Image, cx: float, cy: float, r: float, color: tuple[int, int, int], soft: bool) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    steps = 28
    for i in range(steps):
        t = i / (steps - 1)
        rr = r * (1 - 0.55 * t)
        ox, oy = cx - r * 0.28 * t, cy - r * 0.32 * t
        col = _shade(color, 0.72 + 0.5 * t) if soft else _shade(color, 0.8 + 0.35 * t)
        d.ellipse([ox - rr, oy - rr, ox + rr, oy + rr], fill=col + (255,))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1.2 if soft else 0.4)))


def _star(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill) -> None:
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def _mock_render(spec: dict) -> bytes:
    W = 1024
    img = Image.new("RGBA", (W, W), (236, 228, 212, 255))
    bg = ImageDraw.Draw(img)
    for i in range(60, 0, -1):  # 影棚径向渐变
        k = i / 60
        c = tuple(int(v) for v in (220 + 32 * (1 - k), 210 + 36 * (1 - k), 192 + 44 * (1 - k)))
        bg.ellipse([W / 2 - 700 * k, W * 0.42 - 640 * k, W / 2 + 700 * k, W * 0.42 + 640 * k], fill=c + (255,))
    notes = " ".join(spec.get("shapeNotes", []))
    soft = spec.get("style") in ("soft clay", "plush", "watercolor-painted")
    color = COLOR_RGB.get(spec.get("color") or "", (213, 43, 30))
    subject = spec.get("subject", "")
    animal = "cat" if ("猫" in subject) else ("dog" if "狗" in subject else "bear")
    chubby = 1.15 if ("胖" in notes or "圆" in notes) else 1.0

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([250, 860, 774, 930], fill=(20, 18, 16, 70))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))

    d = ImageDraw.Draw(img)
    if spec.get("connectedBase", True):  # 一体底座（月亮/圆台）
        moon = "月" in subject
        base_col = (238, 214, 150) if moon else (200, 190, 175)
        d.chord([270, 700, 754, 920], 0, 180, fill=_shade(base_col, 0.85))
        d.chord([320, 700, 704, 860], 0, 180, fill=_shade(base_col, 1.05))
    _ball(img, 512, 640, 150 * chubby, color, soft)                 # 身体
    _ball(img, 512, 420, 175 * chubby, color, soft)                 # 头
    ear = 62 * (1.15 if "圆" in notes else 1.0)
    if animal == "cat":
        d = ImageDraw.Draw(img)
        for sx in (-1, 1):
            d.polygon([(512 + sx * 150, 300), (512 + sx * 60, 270), (512 + sx * 140, 170)], fill=_shade(color, 0.9))
    else:
        _ball(img, 512 - 140 * chubby, 285, ear, color, soft)
        _ball(img, 512 + 140 * chubby, 285, ear, color, soft)
    d = ImageDraw.Draw(img)
    d.ellipse([450, 400, 478, 432], fill=(35, 28, 26))
    d.ellipse([546, 400, 574, 432], fill=(35, 28, 26))
    d.ellipse([470, 450, 554, 510], fill=(250, 236, 228))
    d.ellipse([498, 458, 526, 476], fill=(35, 28, 26))
    d.ellipse([400, 470, 444, 492], fill=_shade(color, 1.25))
    d.ellipse([580, 470, 624, 492], fill=_shade(color, 1.25))
    if "星" in notes or "星" in subject:
        _star(d, 512, 640, 78, (242, 201, 76))
        _ball(img, 430, 660, 40, color, soft)
        _ball(img, 594, 660, 40, color, soft)
    if "围巾" in notes or "围巾" in subject:
        ImageDraw.Draw(img).rounded_rectangle([392, 548, 632, 590], 20, fill=(213, 43, 30))
    if "帽" in notes or "帽" in subject:
        ImageDraw.Draw(img).pieslice([400, 180, 624, 330], 180, 360, fill=(20, 18, 16))
    if spec.get("style") == "watercolor-painted":
        img = img.filter(ImageFilter.GaussianBlur(2.2))
    if spec.get("style") == "voxel pixel":
        img = img.resize((64, 64), Image.NEAREST).resize((W, W), Image.NEAREST)
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()
