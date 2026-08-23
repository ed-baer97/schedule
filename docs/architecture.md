# Архитектура и структура

Веб-сервис школьного расписания: **React (Vite)** + **FastAPI**. Доменные модели и солвер живут в `app/`, HTTP — в `backend/`, UI — в `frontend/`. Данные школ изолированы по `school_id`.

## Дерево репозитория

```
schedule/
├── app/                      # домен: модели, сервисы, Excel-шаблоны
│   ├── config.py             # DATABASE_URL и прочие настройки
│   ├── db.py                 # SQLAlchemy Base
│   ├── models/               # сущности БД
│   ├── services/             # валидация, импорт, автосоставление, солвер
│   └── excel_templates/      # шаблоны для импорта
├── backend/                  # FastAPI: роутеры, auth, Celery
│   ├── main.py               # приложение, CORS, раздача SPA из frontend/dist
│   ├── deps.py               # сессия БД, текущий пользователь/школа
│   ├── security.py           # JWT cookie, пароли (argon2)
│   ├── bootstrap.py          # первый platform_admin из .env
│   ├── database.py           # alembic upgrade при старте
│   ├── celery_app.py         # брокер Redis
│   ├── tasks.py              # фоновое автосоставление
│   ├── routers/              # HTTP API (/api/…)
│   └── schemas/              # Pydantic-схемы
├── frontend/                 # React + TypeScript + Bootstrap 5
│   └── src/
│       ├── api/client.ts     # fetch к /api (cookie credentials)
│       ├── auth/             # AuthContext
│       ├── layouts/
│       └── pages/
├── migrations/               # Alembic
├── tests/                    # pytest + TestClient
├── deploy/                   # nginx.conf, backup-postgres.sh
├── scripts/wait_api.py       # ожидание API для корневого npm run dev
├── docs/                     # эта документация
├── docker-compose.yml
├── Dockerfile                # multi-stage: сборка SPA + Python API
├── run_api.py                # uvicorn backend.main:app
├── alembic.ini
├── env.example
└── requirements.txt
```

Локально SQLite лежит в `instance/` (не коммитится). Стенд хранит Postgres в volume `pgdata`.

## Слои

| Слой | Ответственность |
|------|-----------------|
| `frontend/` | UI, маршруты, поллинг jobs |
| `backend/routers/` | HTTP, проверка сессии и школы |
| `backend/schemas/` | вход/выход API |
| `app/models/` | таблицы и связи |
| `app/services/` | правила, Excel, CP-SAT |
| `migrations/` | эволюция схемы |

Роутеры не содержат солвер: они вызывают сервисы и пишут `Job`.

## Модели (`app/models/`)

| Модель | Роль |
|--------|------|
| `School` | тенант |
| `User`, `InviteToken` | вход и приглашения |
| `Job` | статус автосоставления |
| `Teacher`, `Classroom`, `Subject` | справочники |
| `Shift`, `ShiftLessonTime` | смена и звонки |
| `SchoolClass` | класс (уровень, смена) |
| `TeachingAssignment` | предмет ↔ учитель ↔ класс, часы, подгруппа |
| `ScheduleCell` | ячейка сетки |
| `ScheduleSettings` | дни, лимиты, режим кабинетов (на школу и уровень) |

Почти все доменные таблицы несут `school_id`. `platform_admin` без школы работает только в `/admin`.

## API (`backend/routers/`)

Префикс `/api`. Рабочие роутеры требуют JWT (httpOnly cookie). Публичные: `GET /api/health`, auth.

| Префикс | Назначение |
|---------|------------|
| `/api/auth` | login, logout, me, accept-invite |
| `/api/admin` | школы, админы школ, инвайты |
| `/api/jobs/{id}` | статус фоновой задачи |
| `/api/dashboard` | сводка |
| `/api/teachers`, `/classrooms`, `/school-classes`, `/shifts`, `/subjects` | CRUD |
| `/api/workload`, `/assignments` | нагрузка и назначения |
| `/api/schedule` | сетка, ячейки, настройки; `POST …/auto` → `202` + `job_id` |
| `/api/reports` | просмотр и Excel |
| `/api/import` | Excel: `POST /subject-hours` (несколько файлов), старые шаблоны пока на месте |

OpenAPI: http://127.0.0.1:8000/docs

Автосоставление: есть Redis — Celery worker; нет — синхронный fallback (удобно для Windows без Docker). Одна активная задача на школу (иначе `409`).

## Страницы UI (`frontend/src/pages/`)

| Маршрут | Кто | Страница |
|---------|-----|----------|
| `/login`, `/invite` | все | вход и приглашение |
| `/admin` | `platform_admin` | школы и инвайты |
| `/` | `school_admin` | дашборд |
| `/teachers`, `/classrooms`, `/school-classes`, `/shifts`, `/subjects` | школа | справочники |
| `/workload` | школа | нагрузка |
| `/subjects/:id/assignments` | школа | назначения учителей внутри предмета |
| `/schedule`, `/schedule/auto` | школа | сетка и авто |
| `/reports`, `/import` | школа | отчёты и импорт |

Vite в dev проксирует `/api` на `http://127.0.0.1:8000`. В Docker SPA отдаёт FastAPI из `frontend/dist`, снаружи — nginx.

## Сервисы (`app/services/`)

| Модуль | Задача |
|--------|--------|
| `validators.py` | конфликты ячеек (учитель, кабинет, класс, подгруппы) |
| `excel_import.py` | нагрузка по предметам (учителя × классы); кабинеты — после шаблона |
| `auto_scheduler.py` | «лесенка» и постановка в солвер |
| `schedule_solver.py` | OR-Tools CP-SAT |
| `bell_schedule.py` | звонки |

## Тесты и CI

- `tests/conftest.py` — изолированная SQLite, override auth
- `.github/workflows/ci.yml` — pytest + `npm run build` во `frontend/`
