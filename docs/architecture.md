# Архитектура и структура

Веб-сервис школьного расписания: **React (Vite)** + **FastAPI**. Доменные модели и солвер живут в `app/`, HTTP — в `backend/`, UI — в `frontend/`. Данные школ изолированы по `school_id`.

## Дерево репозитория

```
schedule/
├── app/                      # домен: модели, сервисы, Excel-шаблоны
│   ├── config.py             # DATABASE_URL и прочие настройки
│   ├── db.py                 # SQLAlchemy Base
│   ├── domain/               # чистые хелперы (дни, время, grade_from_name)
│   ├── models/               # сущности БД
│   ├── services/             # use-case: CRUD, сетка, отчёты, импорт, солвер
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
│       ├── api/              # client.ts + модули по сущностям (типы + fetch)
│       ├── auth/             # AuthContext
│       ├── layouts/
│       └── pages/            # только UI
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
| `frontend/src/pages/` | UI, маршруты, поллинг jobs |
| `frontend/src/api/` | типы + fetch к `/api` (единственное место вызовов) |
| `frontend/src/domain/` | общие UI-константы (дни недели, `SchoolLevel`) |
| `backend/routers/` | HTTP: auth, Depends, маппинг DTO → Pydantic |
| `backend/schemas/` | вход/выход API (контракт), включая auth/admin |
| `app/services/` | бизнес-логика и SQL; обязательный `school_id`; **отдаёт DTO, не ORM** |
| `app/domain/` | чистые функции без Session/FastAPI |
| `app/models/` | колонки и relationship (без запросов в `@property`) |
| `migrations/` | эволюция схемы |

### Правила границ

1. **Роутер** — auth (`Depends`), вызов сервиса, `model_validate` по DTO. Без `select`/`joinedload` и без бизнес-правил (auth cookie/login допускается в `auth` router). Ошибки сервиса — глобальный `ServiceError` handler в `main.py`.
2. **Сервис** — обязательный `school_id: int` (кроме platform `AdminService`). Не импортирует FastAPI. Возвращает dataclass/DTO из `app/services/dto.py` (или пакетных types). Tenancy: только `require_owned`.
3. **Модель** — таблицы и связи; `@property` без доп. SQL. Часы сетки: `app/domain/assignment.py` + `assignment_hours.remaining_for` / `placed_counts`.
4. **Один write-path на агрегат**
   - `TeachingAssignment` — только `AssignmentService` (`create` / `upsert_hours` / `set_group_numbers`); Excel вызывает его и каталожные `ensure`.
   - `ScheduleCell` — только `ScheduleService` (`insert_cell` / `apply_placements` / `create_cell` / `move_cell` / `reposition_cell` / `delete_cell` / `delete_cells` / `clear_schedule`); авто и солвер делегируют сюда.
5. **Канон имён (как в git)** — `backend.deps`, `backend.schemas`, `TeachingAssignment`, `ScheduleCell`, `ScheduleSettings`, `AutoScheduler`, `ScheduleValidator`. Пакеты `app.services.assignment` / `app.services.schedule` доступны также через реэкспорт `assignment_service` / `schedule_service`.
6. **Правила слота** — предикаты в `app/domain/schedule_rules.py` (`slots_conflict` / `slot_facts_conflict`, `groups_can_share_slot`, `units_cannot_share_class_slot`, `occupancy_blocks_unit`, `teacher_busy_at_slot`, `classroom_at_capacity`, лимиты дня); плоские факты в `app/domain/schedule_facts.py`; ORM→факты только в `app/services/schedule_fact_loader.py`. Валидатор, residual и CP-SAT используют одни предикаты (учитель/кабинет по пересечению интервалов, не по «тому же номеру урока»). Residual строит рёбра со снимка фактов; `validate_cell` — предохранитель на записи. CP-SAT capacity — sweep/`slot_facts_conflict`.

Роутеры не содержат солвер: они вызывают сервисы; постановка Job — `JobService.enqueue_auto` (диспатч через порт `app/services/job_dispatch.py`, реализация в `backend/tasks.py`).
Кабинет для ячейки и warnings — `classroom_resolver.py`; настройки уровня — `load_settings`; диагностика непроставленных часов — `schedule_diagnostics.py`.
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
| `/api/schedule` | сетка, ячейки, настройки; `POST …/auto` и `POST …/repair` → `202` + `job_id`; `POST …/explain` — факты валидатора + текст Qwen |
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
| `assignment/` (`assignment_service` re-export) | CRUD назначений, матрица предмет×класс, нагрузка, `upsert_hours` / `set_group_numbers` |
| `assignment_hours.py` | batch `placed_counts` / `remaining_for` (без SQL в модели) |
| `schedule/` (`schedule_service` re-export) | сетка (queries), ячейки (commands, единственный write-path), настройки |
| `dto.py` | общие DTO на границе сервисов |
| `classroom_resolver.py` | `load_settings`, `resolve_classroom`, warnings без кабинета |
| `schedule_diagnostics.py` | диагностика непроставленных часов |
| `job_dispatch.py` | порт диспатча auto-job (Celery в `backend/tasks`) |
| `dashboard_service.py` | сводка школы |
| `admin_service.py` | школы, админы школ, platform dashboard |
| `job_service.py` | статус Job + `enqueue_auto` (tenancy shift/teacher внутри) |
| `import_service.py` | валидация файлов + оркестрация ExcelImporter |
| `report_service.py` | отчёты JSON и Excel |
| `teacher_service.py` … `subject_service.py` | CRUD справочников + `ensure` для импорта (DTO наружу) |
| `schedule_mapping.py` | joinedload и DTO-проекции `ScheduleCell` |
| `tenancy.py` | `require_owned` по `school_id` |
| `schedule_fact_loader.py` | плоские `UnitFact` / `SlotFact` / teacher/classroom busy для валидатора и солверов |
| `validators.py` | конфликты ячеек (грузят факты; предикаты из domain) |
| `excel_import.py` | парсинг Excel; запись только через сервисы |
| `schedule_explain.py` | панель «почему»: факты валидатора + остаток часов; Qwen только формулирует текст |
| `qwen_client.py` | DashScope OpenAI-compatible; phrasing only, без записи ячеек |
| `auto_scheduler.py` | «лесенка»; ячейки только через `ScheduleService`; `repair_iter` — residual solver, тот же write-path |
| `schedule_solver.py` | residual + OR-Tools CP-SAT на фактах из loader; веса из `ScheduleSettings` / `app.domain.preferences` |
| `bell_schedule.py` | интервалы звонков; `slots_conflict` из domain |

Чистые хелперы: `app/domain/` — дни/`fmt_time`, `grade_from_name` / `level_from_grade` / `level_label`, `normalize_person_name`, `remaining_hours`, `schedule_facts` (`UnitFact`/`SlotFact`/`BusySlotFact`), `slots_conflict` / `slot_facts_conflict` / `groups_can_share_slot` / `units_cannot_share_class_slot` / `occupancy_blocks_unit` / `teacher_busy_at_slot` / `classroom_at_capacity` / лимиты дня, `preferences` (веса 0–10 → коэффициенты CP-SAT).

Автосоставление: есть Redis — Celery worker; нет — синхронный fallback. Одна активная задача на школу (иначе `409`). Виды job: `auto_all`, `auto_by_teacher`, `repair`. Repair не пишет ячейки сам — только residual solver через `ScheduleService`. Панель «почему» на сетке не ставит уроки: валидатор даёт факты, Qwen (если задан `QWEN_API_KEY`) пересказывает их.

Все школьные сервисы принимают обязательный `school_id: int` (`AdminService` — platform-wide).

Фронт: `frontend/src/api/*` — единственные HTTP-вызовы; `frontend/src/domain/` — `SchoolLevel`, подписи дней.

## Тесты и CI

- `tests/conftest.py` — изолированная SQLite, override auth
- `.github/workflows/ci.yml` — pytest + `npm run build` во `frontend/`
