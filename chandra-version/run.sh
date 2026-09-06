#!/usr/bin/env bash
# Inscora - Chandra OCR edition (Linux/macOS — college server)
set -a; [ -f .env ] && . ./.env; set +a
PY_BIN="python3"
[ -f .venv/bin/python3 ] && PY_BIN=".venv/bin/python3"
"$PY_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
