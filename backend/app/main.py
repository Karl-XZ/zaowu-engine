from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  注册表结构
from .config import ROOT, settings
from .db import Base, engine
from .routers import auth, cad, cad_ai, design, misc, pay
from .routers import models as models_router
from .services import jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    jobs.resume_pending()
    yield


app = FastAPI(title=f"{settings.app_name} API", version="1.4.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, design.router, cad.router, cad_ai.router, models_router.router, pay.router, misc.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# 生产环境：直接托管前端构建产物
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        f = (DIST / full_path).resolve()
        if full_path == "api" or full_path.startswith("api/") or not f.is_relative_to(DIST.resolve()):
            raise HTTPException(404, "Not found")
        return FileResponse(f if full_path and f.is_file() else DIST / "index.html")
