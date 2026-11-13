"""对象存储抽象。默认本地目录；生产环境可替换为 S3 兼容存储（接口保持不变）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import settings

ROOT = Path(settings.storage_dir)


def path_for(rel: str) -> Path:
    p = (ROOT / rel).resolve()
    if ROOT.resolve() not in p.parents and p != ROOT.resolve():
        raise ValueError("非法路径")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save_bytes(rel: str, data: bytes) -> str:
    path_for(rel).write_bytes(data)
    return rel


def sha256_file(rel: str) -> str:
    h = hashlib.sha256()
    with open(path_for(rel), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
