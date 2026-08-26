# Локальная разработка на Windows

Фронт и бэк **запускаются отдельно**, в двух окнах PowerShell. Vite проксирует `/api` на FastAPI.

| Процесс | Команда | Адрес |
|---------|---------|--------|
| Backend | `python run_api.py` | http://127.0.0.1:8000 (OpenAPI: `/docs`) |
| Frontend | `npm run dev` в `frontend/` | http://127.0.0.1:5173 |

Работать нужно с **UI на порту 5173**. Запросы к API идут через прокси Vite.

## Что нужно

- Python 3.11+ (`python --version`)
- Node.js 20+ (`node --version`)
- Git

## Первый раз

В корне репозитория:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
npm install --prefix frontend
Copy-Item env.example .env
alembic upgrade head
```

В `.env` для локального HTTP обязательно `COOKIE_SECURE=false`.

Логин из `env.example` (создаётся при пустой таблице `users`):

- email: `admin@example.com`
- пароль: `admin12345`

После входа `platform_admin` без школы попадает в **/admin** — создайте школу и пригласите админа школы. Дальше работайте под админом школы.

## Каждый день: два окна

**Окно 1 — backend**

```powershell
cd путь\к\schedule
.\venv\Scripts\activate
python run_api.py
```

По умолчанию `127.0.0.1:8000`, reload включён. Отключить reload: `$env:RELOAD=0`.

**Окно 2 — frontend**

```powershell
cd путь\к\schedule\frontend
npm run dev
```

Откройте http://127.0.0.1:5173

Порядок: сначала API, потом Vite. Если фронт стартовал раньше — обновите страницу, когда uvicorn поднимется.

## Тесты

```powershell
cd путь\к\schedule
.\venv\Scripts\activate
python -m pytest -q
```

## Сборка SPA

```powershell
npm --prefix frontend run build
```

`frontend/dist` отдаёт FastAPI (и Docker-образ). Для повседневной разработки сборка не нужна — достаточно Vite.

## Замечания

- SQLite: `instance/school_schedule.db`. Не коммитить.
- Redis/Celery локально не обязательны: перед постановкой задачи API делает короткий PING; если Redis нет — автосоставление идёт в фоновом потоке процесса API (без 20 ретраев Celery).
- Корневой `npm run dev` (concurrently api+web) оставлен как опция; основной способ — два отдельных процесса выше.
