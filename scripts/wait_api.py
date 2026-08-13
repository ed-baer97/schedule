"""Wait until FastAPI answers on :8000 (Vite starts faster than uvicorn reload)."""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8000/api/health"
ATTEMPTS = 60
DELAY = 0.5


def main() -> int:
    for _ in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(URL, timeout=1.5) as resp:
                if 200 <= resp.status < 500:
                    return 0
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(DELAY)
    print("API не ответил на http://127.0.0.1:8000 — проверьте python run_api.py", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
