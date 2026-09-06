@echo off
REM Inscora - GLM-OCR edition (Windows)
if exist .env (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
)
if exist .venv\Scripts\python.exe (
  set "PY_BIN=.venv\Scripts\python.exe"
) else (
  set "PY_BIN=python"
)
%PY_BIN% -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
