# Архитектура и структура

Веб-сервис школьного расписания: **React (Vite)** + **FastAPI**. Доменные модели и солвер живут в `app/`, HTTP — в `backend/`, UI — в `frontend/`. Данные школ изолированы по `school_id`.

## Дерево репозитория

```
schedule/
├── app/                      # домен: модели, сервисы, Excel-шаблоны
│   ├── config.py             # DATABASE_URL и прочие настройки
│   ├── db.py                 # SQLAlchemy Base
│   ├── domain/               # чистые предикаты (слот, кабинеты, дни, уровень)
│   ├── models/               # сущности БД
│   ├── services/             # use-case: CRUD, сетка, отчёты, импорт, солвер
│   └── excel_templates/      # шаблоны для импорта
├── backend/                  # FastAPI: роутеры, auth, Celery
│   ├── main.py               # приложение, CORS, раздача SPA из frontend/dist
│   ├── deps.py               # сессия БД, текущий пользователь/школа
│   ├── security.py           # JWT cookie, пароли (argon2)
│   ├── bootstrap.py          # первый platform_admin из .env
│   ├── database.py           # alembic upgrade при старте
│   ├── http_errors.py        # ServiceError → HTTPException
│   ├── celery_app.py         # брокер Redis; PING перед delay
│   ├── tasks.py              # фоновое автосоставление
│   ├── routers/              # HTTP API (/api/…)
│   └── schemas/              # Pydantic-схемы
├── frontend/                 # React + TypeScript + Bootstrap 5
│   └── src/
│       ├── api/              # client.ts + модули по сущностям (типы + fetch)
│       ├── domain/           # зеркало жёстких правил для UI (дни, слот, кабинет)
│       ├── auth/             # AuthContext
│       ├── components/
│       ├── layouts/
│       └── pages/            # только UI
├── migrations/               # Alembic
├── tests/                    # pytest + TestClient
├── deploy/                   # nginx.conf, backup-postgres.sh
├── scripts/wait_api.py       # ожидание API для корневого npm run dev
├── docs/                     # эта документация
├── docker-compose.yml
├── Dockerfile                # multi-stage: сборка SPA + Python API
├── package.json              # npm run dev: API + Vite вместе
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
| `frontend/src/domain/` | UI-константы и зеркало жёстких предикатов (`days`, `SchoolLevel`, `scheduleRules`, `classroomRules`) |
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
   - `Classroom.subjects` (M2M `classroom_subjects`) — только `ClassroomService._sync_subjects`; страница предметов показывает обратный список, не пишет связь.
5. **Канон имён (как в git)** — `backend.deps`, `backend.schemas`, `TeachingAssignment`, `ScheduleCell`, `ScheduleSettings`, `AutoScheduler`, `ScheduleValidator`. Пакеты `app.services.assignment` / `app.services.schedule` доступны также через реэкспорт `assignment_service` / `schedule_service`.
6. **Правила слота** — предикаты в `app/domain/schedule_rules.py` (`slots_conflict` / `slot_facts_conflict`, `groups_can_share_slot`, `units_cannot_share_class_slot`, `occupancy_blocks_unit`, `teacher_busy_at_slot`, `classroom_at_capacity`, лимиты дня); плоские факты в `app/domain/schedule_facts.py`; ORM→факты только в `app/services/schedule_fact_loader.py`. Валидатор, residual и CP-SAT используют одни предикаты (учитель/кабинет по пересечению интервалов, не по «тому же номеру урока»). Residual строит рёбра со снимка фактов; `validate_cell` — предохранитель на записи. CP-SAT capacity — sweep/`slot_facts_conflict`.
7. **Правила кабинета** — жёсткое «можно/нельзя» и стоимость в `app/domain/classroom_rules.py` (`room_has_subject`, `room_allows_subject`, `room_allows_level` / `room_allows`, `placement_cost`, `candidate_rooms_for`, `PlacementContext.force_teacher_home` / `force_class_home`). `ClassroomFact.subject_ids` — `frozenset`; пустой набор = общий кабинет; `is_exclusive` без тегов запрещён на CRUD. `Classroom.school_level` (`NULL` = общий, `elementary` / `secondary`) — отдельный тег от exclusive: уроки ОШ не ставятся в кабинеты НШ. НШ без `requires_fixed_classroom` остаётся в кабинете класса (`force_class_home`); подгруппы с флагом «уходят» — `force_teacher_home` побеждает. ORM→`ClassroomFact` / `PlacementContext` и выбор свободного кабинета — только `classroom_resolver.py` (`classroom_fact`, `candidate_classrooms` — адаптер, `pick_classroom` / `pick_classroom_for` — единственный pick-path). Лесенка, residual, CP-SAT и explain берут кандидатов оттуда; валидатор режет пару предмет↔кабинет через `room_denial_message` (факт — из `classroom_fact`). UI сетки зеркалит `roomAllows` в `frontend/src/domain/classroomRules.ts` — запись всегда проверяет бэкенд.

Роутеры не содержат солвер: они вызывают сервисы; постановка Job — `JobService.enqueue_auto` (диспатч через порт `app/services/job_dispatch.py`, реализация в `backend/tasks.py`).
Настройки уровня — `load_settings`; диагностика непроставленных часов — `schedule_diagnostics.py`.

## Модели (`app/models/`)

| Модель | Роль |
|--------|------|
| `School` | тенант |
| `User` | вход (`platform_admin` / `school_admin`) |
| `InviteToken` | таблица из `8auth_tenancy`; поток приглашений не реализован — админов создаёт `/api/admin` |
| `Job` | статус автосоставления |
| `Teacher` | ФИО, `home_classroom_id` (хозяин комнаты) |
| `Classroom` | номер, вместимость; предметы через M2M `classroom_subjects` (пул), `is_exclusive` (только помеченные предметы; пустые теги = общий), `school_level` (`NULL` = общий / НШ / ОШ) |
| `Subject` | название, цвет; `requires_fixed_classroom`; обратная связь `classrooms` через ту же таблицу |
| `Shift`, `ShiftLessonTime` | смена и звонки |
| `SchoolClass` | класс (уровень, смена, `home_classroom_id`, `homeroom_teacher_id`) |
| `TeachingAssignment` | предмет ↔ учитель ↔ класс, часы, подгруппа |
| `ScheduleCell` | ячейка сетки |
| `ScheduleSettings` | дни, лимиты, `classroom_mode`, `elementary_group_subjects_leave`, веса CP-SAT (на школу и уровень) |

Почти все доменные таблицы несут `school_id`. `platform_admin` без школы работает только в `/admin`.

## API (`backend/routers/`)

Префикс `/api`. Рабочие роутеры требуют JWT (httpOnly cookie). Публичные: `GET /api/health`, auth.

| Префикс | Назначение |
|---------|------------|
| `/api/auth` | login, logout, me |
| `/api/admin` | школы и админы школ |
| `/api/jobs/{id}` | статус фоновой задачи; `GET /api/jobs/active` — текущая pending/running/cancelling для школы; `POST …/cancel` — остановить (`?force=true` — сразу cancelled) |
| `/api/dashboard` | сводка |
| `/api/teachers`, `/classrooms`, `/school-classes`, `/shifts`, `/subjects` | CRUD; `GET /api/teachers/load` — часы учителя по предметам и сменам |
| `/api/workload`, `/assignments` | нагрузка и назначения |
| `/api/schedule` | сетка, ячейки, настройки; `POST …/auto` и `POST …/repair` → `202` + `job_id`; `POST …/explain` — факты валидатора + текст Qwen |
| `/api/reports` | просмотр и Excel |
| `/api/import` | Excel: `POST /subject-hours` (несколько файлов), старые шаблоны пока на месте |

OpenAPI: http://127.0.0.1:8000/docs

Автосоставление: есть Redis (PING) — Celery worker; нет — фоновый поток в процессе API (Windows без Docker), без ретраев kombu. Одна активная задача на школу (иначе `409`), включая статус `cancelling`. Уход со страницы UI не останавливает worker: `GET /api/jobs/active` позволяет снова показать прогресс. Прерванный процесс (reload/Ctrl+C) оставляет строку Job — при старте API такие in-process задачи сбрасываются в `failed`; при постановке новой мёртвый воркер тоже сбрасывается. Остановка: `POST /api/jobs/{id}/cancel` (pending сразу `cancelled`; running с живым Celery — `cancelling`, CP-SAT `StopSearch`; `?force=true` или повторный cancel / мёртвый поток — сразу `cancelled`, без записи сетки).

## Страницы UI (`frontend/src/pages/`)

| Маршрут | Кто | Страница |
|---------|-----|----------|
| `/login` | все | вход |
| `/admin` | `platform_admin` | школы и админы школ |
| `/` | `school_admin` | дашборд |
| `/teachers`, `/classrooms`, `/school-classes`, `/shifts`, `/subjects` | школа | справочники |
| `/workload` | школа | часы предмет×класс |
| `/teacher-load` | школа | нагрузка учителей |
| `/subjects/:id/assignments` | школа | назначения учителей внутри предмета |
| `/schedule`, `/schedule/auto` | школа | сетка и авто |
| `/reports`, `/reports/class/:id`, `/reports/teacher/:id` | школа | отчёты |
| `/import` | школа | импорт Excel |

Vite в dev проксирует `/api` на `http://127.0.0.1:8000`. В Docker SPA отдаёт FastAPI из `frontend/dist`, снаружи — nginx.

## Сервисы (`app/services/`)

| Модуль | Задача |
|--------|--------|
| `assignment/` (`assignment_service` re-export) | CRUD назначений, матрица предмет×класс, нагрузка, `upsert_hours` / `set_group_numbers` |
| `assignment_hours.py` | batch `placed_counts` / `remaining_for` (без SQL в модели) |
| `schedule/` (`schedule_service` re-export) | сетка (queries), ячейки (commands, единственный write-path), настройки |
| `dto.py` | общие DTO на границе сервисов |
| `classroom_resolver.py` | ORM→факты (`classroom_fact`); `candidate_classrooms` / `pick_classroom` / `pick_classroom_for`; warnings без кабинета |
| `schedule_diagnostics.py` | диагностика непроставленных часов |
| `job_dispatch.py` | порт диспатча auto-job (Celery в `backend/tasks`) |
| `dashboard_service.py` | сводка школы |
| `admin_service.py` | школы, админы школ, platform dashboard |
| `job_service.py` | статус Job + `enqueue_auto` + `cancel` (tenancy shift/teacher внутри) |
| `import_service.py` | валидация файлов + оркестрация ExcelImporter |
| `report_service.py` | отчёты JSON и Excel |
| `teacher_service.py` … `subject_service.py` | CRUD справочников + `ensure` для импорта (DTO наружу); `teacher_service.list_load`; `classroom_service` — `_sync_subjects` / `_sync_teachers`; `subject_service` — `selectinload(Subject.classrooms)` |
| `schedule_mapping.py` | joinedload и DTO-проекции `ScheduleCell` |
| `tenancy.py` | `require_owned` по `school_id` |
| `schedule_fact_loader.py` | плоские `UnitFact` / `SlotFact` / teacher/classroom busy для валидатора и солверов |
| `validators.py` | конфликты ячеек (грузят факты; предикаты из domain) |
| `excel_import.py` | парсинг Excel; запись только через сервисы |
| `schedule_explain.py` | панель «почему»: факты валидатора + остаток часов; Qwen только формулирует текст |
| `qwen_client.py` | DashScope OpenAI-compatible; phrasing only, без записи ячеек |
| `auto_scheduler.py` | CP-SAT «Заполнить всё» по смене (два этапа: допустимость, затем оптимум); «лесенка» по учителю — first-fit + relocating, без DFS-перекладки смены; `repair_iter` — residual solver; ячейки только через `ScheduleService` |
| `schedule_solver.py` | residual + OR-Tools CP-SAT на фактах из loader; phase 1 `stop_after_first_solution`, phase 2 `AddHint` на остаток времени; веса из `ScheduleSettings` / `app.domain.preferences` |
| `bell_schedule.py` | интервалы звонков; `slots_conflict` из domain |

Чистые хелперы `app/domain/`: дни/`fmt_time`; `grade_from_name` / `level_from_grade` / `level_label`; `normalize_person_name`; `remaining_hours`; `schedule_facts` (`UnitFact`/`SlotFact`/`BusySlotFact`); слот — `slots_conflict` / `slot_facts_conflict` / `groups_can_share_slot` / `units_cannot_share_class_slot` / `occupancy_blocks_unit` / `teacher_busy_at_slot` / `classroom_at_capacity` / лимиты дня; кабинеты — `room_has_subject` / `room_allows_subject` / `room_allows` / `placement_cost` / `candidate_rooms_for`; `preferences` (веса 0–10 → коэффициенты CP-SAT).

Автосоставление: есть Redis (PING перед `.delay()`) — Celery worker; нет — фоновый поток. Одна активная задача на школу (иначе `409`). Виды job: `auto_all`, `auto_by_teacher`, `repair`. Остановка через `POST /api/jobs/{id}/cancel` (`?force=true` сбрасывает зависшую). Прерванный API-процесс: in-process jobs → `failed` при старте. Repair не пишет ячейки сам — только residual solver через `ScheduleService`. Панель «почему» на сетке не ставит уроки: валидатор даёт факты, Qwen (если задан `QWEN_API_KEY`) пересказывает их.

Все школьные сервисы принимают обязательный `school_id: int` (`AdminService` — platform-wide).

Фронт: `frontend/src/api/*` — единственные HTTP-вызовы (`health.ts`, jobs в `schedule.ts`); `frontend/src/domain/` — `SchoolLevel`, дни, `groupsCanShareSlot`, `roomHasSubject`, `roomAllows` / `roomAllowsSubject`.

## Тесты и CI

- `tests/conftest.py` — изолированная SQLite, override auth
- SQLite: перед удалением `Classroom`/`Subject` чистить `classroom_subjects` (иначе reuse id подтягивает старые теги)
- `.github/workflows/ci.yml` — pytest + `npm run build` во `frontend/`
