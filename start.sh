#!/usr/bin/env bash
# 一键启动（开发模式）：后端 http://localhost:8010 · 前端 http://localhost:5173
set -e
cd "$(dirname "$0")"
API_PORT="${API_PORT:-8010}"
[ -f .env ] || cp .env.example .env
PY="$(command -v python3.12 || command -v python3.11 || command -v python3)"
if [ ! -x backend/.venv/bin/python ]; then
  echo "▶ 创建 Python 虚拟环境（需要 Python ≥ 3.10）"
  "$PY" -m venv backend/.venv
  if command -v uv >/dev/null; then uv pip install --python backend/.venv/bin/python -r backend/requirements.txt
  else backend/.venv/bin/pip install -r backend/requirements.txt; fi
fi
[ -d frontend/node_modules ] || (cd frontend && npm install)
echo "▶ 后端 :$API_PORT   前端 :5173"
(cd backend && .venv/bin/uvicorn app.main:app --reload --port "$API_PORT") &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd frontend && API_PORT="$API_PORT" npx vite --port 5173
