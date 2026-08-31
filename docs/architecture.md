# Архитектура и структура

Веб-сервис школьного расписания: **React (Vite)** + **FastAPI**. Доменные модели и солвер живут в `app/`, HTTP — в `backend/`, UI — в `frontend/`. Данные школ изолированы по `school_id`. Flask в runtime нет.

Запрос идёт сверху вниз; назад — только DTO / JSON, не ORM:

```
браузер
  └─ pages / layouts / components     UI, поллинг jobs
       └─ frontend/src/api            единственные fetch к /api
            └─ frontend/src/domain     зеркало жёстких правил (без записи)
                 │
                 ▼  HTTP  (Vite :5173 dev / nginx → FastAPI :8000 прод)
            backend/routers            auth Depends, вызов сервиса, Pydantic
            backend/schemas            контракт API
                 │
                 ▼
            app/services               use-case + SQL, school_id, DTO наружу
                 ├─ app/domain         чистые предикаты (без Session / FastAPI)
                 └─ app/models          таблицы; @property без SQL
                      └─ migrations     Alembic (head: 14subject_difficulty)
                           └─ SQLite (dev) / PostgreSQL (стенд)

Инфра: Redis + Celery worker (`--profile queue`) — только автосоставление
```

## Дерево репозитория

```
schedule/
├── app/                      # домен: модели, сервисы, Excel-шаблоны
│   ├── config.py             # DATABASE_URL и прочие настройки
│   ├── db.py                 # SQLAlchemy Base
│   ├── passwords.py          # argon2 (без FastAPI)
│   ├── domain/               # чистые предикаты (слот, кабинеты, дни, уровень, assist)
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
6. **Правила слота** — предикаты в `app/domain/schedule_rules.py` (`slots_conflict` / `slot_facts_conflict`, `groups_can_share_slot`, `units_cannot_share_class_slot`, `occupancy_blocks_unit`, `teacher_busy_at_slot`, `classroom_at_capacity`, лимиты дня); плоские факты в `app/domain/schedule_facts.py`; ORM→факты только в `app/services/schedule_fact_loader.py`. Валидатор, residual и CP-SAT используют одни предикаты (учитель/кабинет: тот же день + пересечение звонков; звонки — время суток без даты, Пн 08:00 не блокирует Вт 08:00; без звонков — тот же день и номер урока). Residual строит рёбра со снимка фактов; `validate_cell` — предохранитель на записи. CP-SAT capacity — sweep по дню, затем интервалы.
7. **Правила кабинета** — жёсткое «можно/нельзя» и стоимость в `app/domain/classroom_rules.py` (`room_has_subject`, `room_allows_subject`, `room_allows_level` / `room_allows`, `placement_cost`, `candidate_rooms_for`, `PlacementContext.force_teacher_home` / `force_class_home`). `ClassroomFact.subject_ids` — `frozenset`; пустой набор = общий кабинет; `is_exclusive` без тегов запрещён на CRUD. `Classroom.school_level` (`NULL` = общий, `elementary` / `secondary`) — отдельный тег от exclusive: уроки ОШ не ставятся в кабинеты НШ. НШ без `requires_fixed_classroom` остаётся в кабинете класса (`force_class_home`); подгруппы с флагом «уходят» — `force_teacher_home` побеждает. ORM→`ClassroomFact` / `PlacementContext` и выбор свободного кабинета — только `classroom_resolver.py` (`classroom_fact`, `candidate_classrooms` — адаптер, `pick_classroom` / `pick_classroom_for` — единственный pick-path; `filter_free_classrooms` / `classroom_free_at_slot` — вместимость в слоте). `GET /api/schedule/assignments-for-class/{id}?day_of_week=&lesson_number=` не отдаёт кабинеты на ёмкости в этом слоте. UI сетки зеркалит `roomAllows` и `roomFreeAtSlot` в `frontend/src/domain/classroomRules.ts` — запись всегда проверяет бэкенд. Лесенка, residual и CP-SAT **обязаны** записать конкретный `classroom_id` (`validate_cell(..., require_classroom=True)`; пустой пул кандидатов → CP-SAT `INFEASIBLE`). `y[unit,slot,room]` только для малых пулов (≤4, лаборатории); общие кабинеты назначаются после Solve (`_assign_rooms_to_chosen`), иначе модель не успевает за лимит. В SAT — грубая ёмкость: уроков в слоте ≤ сумма `classes_capacity`, фиксированный предмет ≤ свой пул. Сдвоенные часы одного назначения получают **один кабинет**, если он свободен на оба часа; иначе каждый час из пула отдельно. `pick_classroom` / `pick_classroom_for` ставят кабинет соседнего часа пары первым. Ручная сетка по-прежнему допускает «Без кабинета». Explain берёт кандидатов оттуда; валидатор режет пару предмет↔кабинет через `room_denial_message` (факт — из `classroom_fact`).

Роутеры не содержат солвер: они вызывают сервисы; постановка Job — `JobService.enqueue_auto` (диспатч через порт `app/services/job_dispatch.py`, реализация в `backend/tasks.py`). Отмена in-process (SQLite) — Event в `job_cancel.py`, без ожидания WAL. Celery worker читает статус в БД.
Настройки уровня — `load_settings`; диагностика непроставленных часов — `schedule_diagnostics.py`.

### Зеркала и не-дубли

Это не вторые реализации правил — границы слоёв:

| Пара | Почему так |
|-------|------------|
| `app/domain/*.py` ↔ `frontend/src/domain/*.ts` | UI фильтрует сетку до запроса; запись всегда проверяет бэкенд |
| dataclass DTO ↔ Pydantic ↔ TS в `frontend/src/api/` | три представления одного контракта |
| `assignment_service.py` / `schedule_service.py` | фасады-реэкспорт пакетов, не вторая логика |
| `bell_schedule.schedules_conflict` | ORM-адаптер интервалов над `slots_conflict` |
| `pick_classroom_for` | Session-обёртка: грузит факты и вызывает `pick_classroom` |

Мёртвое: таблица `InviteToken` из миграции `8auth_tenancy` — потока приглашений нет, админов создаёт `/api/admin`.

## Модели (`app/models/`)

| Модель | Роль |
|--------|------|
| `School` | тенант |
| `User` | вход (`platform_admin` / `school_admin`) |
| `InviteToken` | таблица из `8auth_tenancy`; поток приглашений не реализован — админов создаёт `/api/admin` |
| `Job` | статус автосоставления |
| `Teacher` | ФИО, `home_classroom_id` (хозяин комнаты) |
| `Classroom` | номер, вместимость; предметы через M2M `classroom_subjects` (пул), `is_exclusive` (только помеченные предметы; пустые теги = общий), `school_level` (`NULL` = общий / НШ / ОШ) |
| `Subject` | название, цвет; `difficulty` (`easy` / `medium` / `hard`, default `medium`); `requires_fixed_classroom`; обратная связь `classrooms` через ту же таблицу |
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
| `/api/schedule` | сетка, ячейки, настройки; `POST …/auto` и `POST …/repair` → `202` + `job_id`; `POST …/explain` — факты валидатора + текст Qwen; `POST …/assist` — фраза → веса и проверенные сдвиги |
| `/api/reports` | просмотр и Excel |
| `/api/import` | Excel: `POST /subject-hours` (несколько файлов), старые шаблоны пока на месте |

OpenAPI: http://127.0.0.1:8000/docs

Автосоставление: есть Redis (PING) — только Celery worker (ошибка `.delay()` → `failed`, без отката в API). Нет Redis: локально (`SOLVER_ALLOW_IN_PROCESS` по умолчанию true) — фоновый поток в процессе API; в Docker compose переменная `false` — задача сразу `failed` («поднимите `--profile queue`»), солвер не идёт в контейнер api на 512 МБ. Одна активная задача на школу (иначе `409`), включая статус `cancelling`. Уход со страницы UI не останавливает worker: `GET /api/jobs/active` позволяет снова показать прогресс. Прерванный процесс (reload/Ctrl+C) оставляет строку Job — при старте API такие in-process задачи сбрасываются в `failed`; при постановке новой мёртвый воркер тоже сбрасывается. Остановка: `POST /api/jobs/{id}/cancel` сразу ставит in-process Event (StopSearch без ожидания SQLite), затем пишет БД (pending сразу `cancelled`; running с живым воркером — `cancelling`; `?force=true` или повторный cancel / мёртвый поток — сразу `cancelled`, без записи сетки). SQLite: WAL + busy_timeout; солвер коммитит сессию перед `Solve()`.

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
| `job_cancel.py` | in-process Event отмены (SQLite StopSearch без ожидания WAL); Celery смотрит БД |
| `dashboard_service.py` | сводка школы |
| `admin_service.py` | школы, админы школ, platform dashboard |
| `job_service.py` | статус Job + `enqueue_auto` + `cancel`; `time_limit_sec` с формы, потолок `SOLVER_TIME_LIMIT_SEC` |
| `import_service.py` | валидация файлов + оркестрация ExcelImporter |
| `report_service.py` | отчёты JSON и Excel |
| `teacher_service.py` … `subject_service.py` | CRUD справочников + `ensure` для импорта (DTO наружу); `teacher_service.list_load`; `classroom_service` — `_sync_subjects` / `_sync_teachers`; `subject_service` — `selectinload(Subject.classrooms)` |
| `schedule_mapping.py` | joinedload и DTO-проекции `ScheduleCell` |
| `tenancy.py` | `require_owned` по `school_id` |
| `schedule_fact_loader.py` | плоские `UnitFact` / `SlotFact` / teacher/classroom busy для валидатора и солверов |
| `validators.py` | конфликты ячеек (грузят факты; предикаты из domain) |
| `excel_import.py` | парсинг Excel; запись только через сервисы |
| `schedule_explain.py` | панель «почему»: факты валидатора + остаток часов; Qwen только формулирует текст |
| `schedule_assist.py` | фраза завуча → ползунки и локальные сдвиги; Qwen уточняет JSON-намерение; запись только через валидатор + `ScheduleService.move_cell` |
| `qwen_client.py` | DashScope OpenAI-compatible; phrasing / JSON intent, без записи ячеек |
| `auto_scheduler.py` | CP-SAT «Заполнить всё» по смене (сначала hard, pack_gaps, якорение двоек ≥4 ч, остальные soft-пакеты, хвост до лимита времени); «лесенка» по учителю — first-fit + relocating, без DFS-перекладки смены; `repair_iter` — residual solver; ячейки только через `ScheduleService` |
| `schedule_solver.py` | residual + OR-Tools CP-SAT на фактах из loader; phase 1 без `Minimize` (допустимость), пакет `pack_gaps` (вес 4), затем якорение/hint соседних двоек ≥4 ч/нед (`freeze_policy`, ползунки 5–9; на 10 — доверяем hard packing), затем `early_rooms` (вес 2) → `cosmetics` (вес 1); хвост `Minimize` последнего пакета до `time_limit_sec` (10% leftover); ветвление hardest-first; веса из `ScheduleSettings` / `app.domain.preferences` (ползунок сдвоенных: 10 — жёсткая упаковка 2+2+…, нечётный час — один одиночный; два урока предмета в день всегда соседние); `y` только для пула ≤4; остальные кабинеты после Solve (`_assign_rooms_to_chosen`, пары — один кабинет если свободен); SAT: уроков в слоте ≤ сумма вместимостей |
| `bell_schedule.py` | интервалы звонков; `slots_conflict` из domain |

Чистые хелперы `app/domain/`:

| Модуль | Роль |
|--------|------|
| `days.py` | дни, `fmt_time` |
| `school_class.py` / `school_level.py` | `grade_from_name`, `level_from_grade`, `level_label`, параллели для split |
| `names.py` | `normalize_person_name` |
| `assignment.py` | `remaining_hours` |
| `schedule_facts.py` | `UnitFact` / `SlotFact` / `BusySlotFact` |
| `schedule_rules.py` | слот, подгруппы, занятость, лимиты дня |
| `classroom_rules.py` | `room_has_subject` / `room_allows*` / `placement_cost` / `candidate_rooms_for` |
| `preferences.py` | ползунки 0–10 → веса CP-SAT, `freeze_policy` |
| `pair_epochs.py` | якорение соседних двоек между эпохами CP-SAT |
| `assist_intent.py` | фраза завуча → ползунки и порог урока |

Автосоставление: есть Redis (PING перед `.delay()`) — только Celery worker (при ошибке `.delay()` задача `failed`, без отката в API на 512 МБ). Нет Redis: локально — фоновый поток; Docker (`SOLVER_ALLOW_IN_PROCESS=false`) — `failed`. Worker: 4 CPU / 4 ГБ / `SOLVER_NUM_WORKERS=4`. Одна активная задача на школу (иначе `409`). Виды job: `auto_all`, `auto_by_teacher`, `repair`. Остановка через `POST /api/jobs/{id}/cancel` (`?force=true` сбрасывает зависшую). Прерванный API-процесс: in-process jobs → `failed` при старте. Repair не пишет ячейки сам — только residual solver через `ScheduleService`. Панель «почему» на сетке не ставит уроки: валидатор даёт факты, Qwen (если задан `QWEN_API_KEY`) пересказывает их. `POST /api/schedule/assist` пишет ячейки только после `validate_cell` / `move_cell`; Qwen не выбирает `cell_id`.

Все школьные сервисы принимают обязательный `school_id: int` (`AdminService` — platform-wide).

Фронт: `frontend/src/api/*` — единственные HTTP-вызовы (`health.ts`, jobs в `schedule.ts`; `import.ts` — raw `fetch` для FormData); `frontend/src/domain/` — `SchoolLevel`, дни, `groupsCanShareSlot`, `secondHourIsSplit`, `roomHasSubject`, `roomAllows` / `roomAllowsSubject` / `roomFreeAtSlot`.

CP-SAT и сложность предмета: `Subject.difficulty=hard` нельзя ставить на урок ≥ 7 (жёсткое ограничение) и раньше в soft-пакете `early_rooms`. Миграция: `14subject_difficulty`. Чеклист колонок при старте API — `backend/database.py` (`subjects.difficulty`).

## Тесты и CI

- `tests/conftest.py` — изолированная SQLite, override auth
- SQLite: перед удалением `Classroom`/`Subject` чистить `classroom_subjects` (иначе reuse id подтягивает старые теги)
- Домен: `test_schedule_rules`, `test_classroom_rules`, `test_preferences`, `test_pair_epochs`, `test_assist_intent`, `test_schedule_solver_stages`
- API: `test_api_health`, `test_api_crud`, `test_api_schedule`, `test_api_jobs`, `test_excel_import`
- `.github/workflows/ci.yml` — pytest (Python 3.12) + `npm ci` / `npm run build` во `frontend/`
