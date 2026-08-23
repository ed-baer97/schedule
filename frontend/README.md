# Frontend (React + Vite)

UI школьного расписания. Документация проекта — в [docs/](../docs/README.md).

Локально фронт и бэк запускаются **отдельно** (два окна PowerShell). Полная инструкция: [docs/local-windows.md](../docs/local-windows.md).

```powershell
# из папки frontend, при уже запущенном python run_api.py
npm run dev      # Vite :5173, прокси /api → FastAPI :8000
npm run build    # → frontend/dist (отдаёт FastAPI / Docker-образ)
```

Маршруты: `/login`, `/invite`, `/admin` (platform), остальное — приложение школы после auth.
