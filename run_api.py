"""
Запуск FastAPI из корня репозитория (чтобы импортировался пакет `backend`).

Использование из любой директории:
  python path/to/schedule/run_api.py

Или из корня schedule:
  python run_api.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
os.chdir(_ROOT)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "1") not in ("0", "false", "False")

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=reload,
    )
