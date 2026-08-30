# Этапы: стенд, админка, очередь

Чеклист следующей волны после продуктовых этапов 1–7. Цели продукта — [product.md](product.md).

**Как отмечать:** `[x]` у пункта, когда он проверен (код в git и/или стенд). Этап закрыт, когда отмечены все пункты раздела «Готово, когда».

**Поток выкладки:** код готовим локально → push в git → на Ubuntu `git pull && docker compose --profile queue up -d --build --force-recreate`.

**Стенд:** Ubuntu, i3, 8 ГБ RAM, свободный домен, Cloudflare Tunnel (порты 80/443 на роутере не открываем).

**Не входит в эти этапы:** S3/MinIO, Flower, второй Celery worker, несколько uvicorn workers.

Подробности compose, `.env` и бэкапов — [deploy.md](deploy.md). Alembic head: `14subject_difficulty`.

---

## Сводка

| Этап | Что | Статус |
|------|-----|--------|
| 0 | Хост Ubuntu + туннель | не начат (на сервере) |
| 1 | Docker: nginx + API + Postgres | **код готов** |
| 2 | Auth (закрыть API) | **код готов** |
| 3 | Админка: школы и админы школ | **код готов** |
| 4 | Redis + Celery | **код готов** (`--profile queue`) |
| 5 | Эксплуатация стенда | **код готов** (скрипт бэкапа) |

---

## Этап 0 — Хост (Ubuntu)

Цель: машина готова, приложение ещё можно не деплоить.

### На сервере

- [ ] Docker Engine + Compose plugin (не Docker Desktop, не snap если можно apt)
- [ ] Swap 2 ГБ
- [ ] Каталог `/opt/schedule`, пользователь в группе `docker`
- [ ] Cloudflare: зона домена, туннель создан
- [ ] Cloudflare Access: вход только с ваших email (второй слой до своей auth)

### Готово, когда

- [ ] `docker compose version` работает
- [ ] Туннель в панели Cloudflare в статусе healthy (допускается заглушка)

---

## Этап 1 — Docker: приложение на домене

Цель: текущее приложение открывается по HTTPS. Redis/Celery — через `--profile queue`.

### В git

- [x] `Dockerfile` (multi-stage: Node собирает `frontend/dist` → Python + SPA)
- [x] `.dockerignore`
- [x] `docker-compose.yml`: `nginx`, `api` (1 воркер), `db` (+ profile `queue`: redis, worker)
- [x] Лимиты RAM в compose
- [x] `deploy/nginx.conf`
- [x] `env.example`: `POSTGRES_*`, `SECRET_KEY`, bootstrap, Redis
- [x] API в контейнере: `0.0.0.0:8000`
- [x] CORS для Vite; same-origin за nginx
- [x] Миграции при старте API (`ensure_database` + Alembic)
- [x] `psycopg` в requirements; на стенде Postgres
- [x] README / docs: блок Docker

### Не коммитить

- `.env`, пароль Postgres, токен Cloudflare Tunnel

### На сервере (после push)

- [ ] `git clone` / `git pull` в `/opt/schedule`
- [ ] `cp env.example .env`, свой пароль БД + `BOOTSTRAP_ADMIN_*`
- [ ] Туннель → `http://127.0.0.1:80`
- [ ] `docker compose up -d --build`
- [ ] Volume Postgres не удалять (`down -v` не делать)

### Готово, когда

- [ ] С телефона открывается `https://<домен>`
- [ ] Справочники, сетка, импорт, отчёты работают
- [ ] Порты 80/443 на роутере закрыты

**Дальше на стенде всегда:** `git pull && docker compose --profile queue up -d --build --force-recreate`

---

## Этап 2 — Auth

### В git

- [x] Модель `User`
- [x] JWT в httpOnly cookie
- [x] `/api/auth/login`, `/logout`, `/me`
- [x] Страница `/login` в React
- [x] Bootstrap: `BOOTSTRAP_ADMIN_EMAIL` / `PASSWORD`
- [x] Рабочие роутеры за `get_current_user` / `get_current_school`
- [x] Без сессии → 401 (тест `test_teachers_requires_auth_without_override`)

### На сервере

- [ ] Cloudflare Access оставить включённым
- [ ] Bootstrap-админ только в `.env` на хосте

### Готово, когда

- [ ] Анонимный запрос к API — 401
- [ ] После логина приложение работает

---

## Этап 3 — Админка: школы и админы школ

### В git

- [x] Модель `School`
- [x] `school_id` на доменных таблицах + миграция `8auth_tenancy`
- [x] `get_current_school()` на рабочие API
- [x] `/api/admin/schools`, `/admins`
- [x] UI `/admin`: список школ, создание, админы школ
- [x] `school_admin` только своя школа; `platform_admin` без `school_id` → `/admin` (сетку не открывает)

### Готово, когда

- [ ] Две школы не видят данные друг друга (проверить на стенде)
- [ ] Platform-админ создаёт школу и админа школы без SQL

---

## Этап 4 — Redis + Celery

### В git

- [x] Redis + worker в compose (`--profile queue`)
- [x] concurrency=1, prefetch=1, mem_limit worker 4g, cpus 4, SOLVER_NUM_WORKERS=4
- [x] `POST /api/schedule/auto` → `202` + `job_id`
- [x] `GET /api/jobs/{id}`
- [x] Фронт: поллинг вместо NDJSON
- [x] Лимит solver (`SOLVER_TIME_LIMIT_SEC`, default 90)
- [x] Одна активная задача на школу (409 если уже running)
- [x] Docker: `SOLVER_ALLOW_IN_PROCESS=false` (без очереди job `failed`, не OOM в api)
- [x] Worker `depends_on` healthy api; `QWEN_*` в контейнере api

### Готово, когда

- [ ] С `--profile queue` справочники открываются во время автосоставления
- [ ] `python run_api.py` без Redis: fallback в процесс API всё ещё считает задачу

---

## Этап 5 — Эксплуатация стенда

- [x] Ротация логов Docker в compose
- [x] `deploy/backup-postgres.sh` + комментарий cron в скрипте / docs
- [x] Документация: не делать `docker compose down -v`

---

## Вне скоупа (пока не делаем)

- S3 / MinIO
- Учебный год (`academic_year`)
- Роли «учитель / только просмотр»
- Несколько реплик API, Flower, второй worker

---

## Железо стенда (напоминание)

| В простое | На пике автосоставления |
|-----------|-------------------------|
| ~2.5–3.5 ГБ | ~5–7 ГБ (нужен swap 2 ГБ) |

На 8 ГБ: **один** uvicorn, **один** Celery worker. Solver только в worker.
