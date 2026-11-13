"""Aholo Lux3D 适配器（PRD §3.1、§8.4）。

- 中国区 Key（labs.aholo3d.cn）与国际区 Key 不互通；字段以实际绑定地区的 OpenAPI 为准。
- 纯图生 3D 未公开 prompt 字段：需要文字约束时用文生 3D 的 img + prompt（GEN-A10）。
- 异步任务：submit → 轮询 task id；超时先查询既有任务，禁止重复创建（GEN-A12）。
- 结果 URL 短期有效：拿到后立刻转存平台存储（GEN-A04）。

MOCK 模式：用 manifold3d 构造与效果图一致的水密网格（小熊/猫 + 一体底座，可选抱星星）。
"""
from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import time
import uuid

import httpx
import numpy as np
import trimesh

from ..config import settings
from . import aholo_client


Lux3DError = aholo_client.AholoError


def submit(image_png: bytes, prompt: str | None, idempotency_key: str, spec: dict) -> str:
    if settings.aholo_mock:
        return f"mock-{uuid.uuid4().hex[:12]}"
    with httpx.Client(timeout=60) as client:
        payload = {"img": aholo_client.upload_image(client, settings.aholo_api_base, settings.aholo_api_key, image_png),
                   "version": settings.aholo_model_version, "outputFormat": ["glb"],
                   "enablePbr": spec.get("colorMode") == "color", "aiPredictSize": False}
        operation = "text-to-3d" if prompt else "img-to-3d"
        if prompt:
            payload["prompt"] = prompt
        return aholo_client.create(client, settings.aholo_api_base, settings.aholo_api_key, operation, payload, idempotency_key)


def poll(task_id: str, timeout_s: int = 900) -> dict:
    if task_id.startswith("mock-"):
        if not settings.aholo_mock:
            raise Lux3DError("Mock task cannot be resumed with the real provider")
        time.sleep(2.5)
        return {"status": "succeeded", "resultUrl": None, "costFen": settings.cost_lux3d_fen, "mock": True}
    with httpx.Client(timeout=30) as client:
        data = aholo_client.wait_for(client, settings.aholo_api_base, settings.aholo_api_key, task_id, timeout_s)
    if str(data["status"]) != "3":
        return {"status": "failed", "resultUrl": None, "costFen": settings.cost_lux3d_fen, "taskId": task_id}
    urls = aholo_client.output_urls(data)
    glbs = [url for url in urls if urlsplit(url).path.lower().endswith(".glb")]
    zips = [url for url in urls if urlsplit(url).path.lower().endswith(".zip")]
    candidates = glbs or zips or urls
    if not candidates:
        raise Lux3DError(f"Aholo task {task_id} succeeded without a model URL")
    # The API exposes no CNY cost; keep the configured estimate, never call credits fen.
    return {"status": "succeeded", "resultUrl": candidates[0], "costFen": settings.cost_lux3d_fen, "taskId": task_id}


def download(result: dict, spec: dict) -> bytes:
    if result.get("mock") and settings.aholo_mock:
        return mock_glb(spec)
    if result.get("status") != "succeeded" or not result.get("resultUrl"):
        raise Lux3DError("Aholo real generation has no successful downloadable model")
    with httpx.Client(timeout=120) as client:
        data = aholo_client.download_bytes(client, result["resultUrl"], aholo_client.MAX_MODEL_BYTES)
    if data.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos = archive.infolist()
                if len(infos) > 1000 or sum(item.file_size for item in infos) > aholo_client.MAX_MODEL_BYTES:
                    raise Lux3DError("Aholo ZIP exceeds extraction limits")
                for item in infos:
                    path = PurePosixPath(item.filename.replace("\\", "/"))
                    if path.is_absolute() or ".." in path.parts or ":" in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000:
                        raise Lux3DError("Aholo ZIP contains an unsafe path")
                models = [item for item in infos if not item.is_dir() and item.filename.lower().endswith(".glb")]
                if len(models) != 1:
                    raise Lux3DError("Aholo ZIP must contain exactly one GLB model")
                with archive.open(models[0]) as model:
                    data = model.read(aholo_client.MAX_MODEL_BYTES + 1)
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            raise Lux3DError("Aholo returned an invalid model ZIP") from exc
    if len(data) < 12 or data[:4] != b"glTF" or int.from_bytes(data[4:8], "little") != 2 or int.from_bytes(data[8:12], "little") != len(data):
        raise Lux3DError("Aholo returned an invalid GLB model")
    return data


# ---------------- MOCK 网格 ----------------
def _m2t(m) -> trimesh.Trimesh:
    mesh = m.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts), process=True)


def mock_glb(spec: dict) -> bytes:
    from manifold3d import Manifold, set_circular_segments
    set_circular_segments(48)
    notes = " ".join(spec.get("shapeNotes", []))
    subject = spec.get("subject", "")
    chubby = 1.15 if ("胖" in notes or "圆" in notes) else 1.0
    S = Manifold.sphere
    parts = [
        Manifold.cylinder(10, 26, 24).translate([0, 0, 0]),                              # 底座
        S(14 * chubby).scale([1, 0.9, 1.1]).translate([0, 0, 22]),                       # 身体
        S(16 * chubby).translate([0, 0, 44]),                                            # 头
        S(6.5).translate([-12 * chubby, 0, 57]), S(6.5).translate([12 * chubby, 0, 57]),  # 耳朵
        S(4).translate([0, -14.5 * chubby, 41]),                                         # 鼻
    ]
    if "星" in notes or "星" in subject:
        pts = []
        import math
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            r = 11 if i % 2 == 0 else 5
            pts.append([r * math.cos(a), r * math.sin(a)])
        from manifold3d import CrossSection
        star = Manifold.extrude(CrossSection([pts]), 5).rotate([90, 0, 0]).translate([0, -10, 22])
        parts += [star, S(5).translate([-9, -11, 22]), S(5).translate([9, -11, 22])]
    body = parts[0]
    for p in parts[1:]:
        body = body + p
    tm = _m2t(body)
    tm.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))  # Z-up → glTF Y-up
    return tm.export(file_type="glb")
