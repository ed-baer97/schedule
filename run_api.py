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

    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
