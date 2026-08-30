# Стенд и Docker

Чеклист выкладки: [stages.md](stages.md). Архитектура слоёв: [architecture.md](architecture.md).

Поток: код локально → push в git → на Ubuntu `git pull && docker compose --profile queue up -d --build --force-recreate`.

## Compose

```bash
git clone <repo> /opt/schedule && cd /opt/schedule
cp env.example .env
# POSTGRES_PASSWORD, SECRET_KEY, BOOTSTRAP_ADMIN_*, COOKIE_SECURE=true
docker compose --profile queue up -d --build
```

Сервисы без профиля `queue`: `nginx` → `api` → Postgres. Автосоставление **не** работает: api ставит `SOLVER_ALLOW_IN_PROCESS=false`, без Redis job сразу `failed`.

С `--profile queue` добавляются Redis и один Celery worker (solver только там). Worker ждёт healthy `api` (миграции). Образ API — multi-stage: Node собирает `frontend/dist`, Python 3.12 отдаёт SPA и `/api`. Миграции: `alembic upgrade head` при старте контейнера `api`.

| Сервис | RAM | Роль |
|--------|------|------|
| `db` | 512m | Postgres 16, volume `pgdata` |
| `api` | 512m | 1 uvicorn; солвер сюда не должен попадать |
| `nginx` | 64m | :80 → api (и SPA, и `/api`) |
| `redis` | 64m | только `--profile queue` |
| `worker` | 4g / 4 CPU | CP-SAT, concurrency=1 |

## `.env` на сервере

Не коммитить. Скопировать из `env.example` и задать:

| Переменная | Зачем |
|-----------|--------|
| `POSTGRES_PASSWORD` | обязателен (`:?` в compose) |
| `SECRET_KEY` | JWT |
| `BOOTSTRAP_ADMIN_EMAIL` / `PASSWORD` | первый `platform_admin` при пустой таблице `users` |
| `COOKIE_SECURE=true` | HTTPS / Cloudflare Tunnel |
| `SOLVER_TIME_LIMIT_SEC` | лимит CP-SAT (default 90) |
| `SOLVER_CPUS` / `SOLVER_NUM_WORKERS` | равны числу ядер worker |
| `SOLVER_MEM_LIMIT` | default `4g` |
| `QWEN_API_KEY` | опционально: панель «почему» и assist; пробрасывается в контейнер `api` |
| `HTTP_PORT` | стенд `80`; локальный Docker часто `8080` (порт 80 занят) |

`DASHSCOPE_API_KEY` — синоним `QWEN_API_KEY`. Ключи в git не класть.

Cloudflare Tunnel направлять на `http://127.0.0.1:80`. Порты 80/443 на роутере не открывать.

## Локальный Docker (Windows)

Порт 80 на хосте часто занят. В `.env`: `HTTP_PORT=8080`, `COOKIE_SECURE=false`, затем:

```bash
docker compose --profile queue up -d --build
```

UI: http://127.0.0.1:8080 — без `COOKIE_SECURE=false` логин по HTTP не сохранится. Без профиля `queue` «Заполнить всё» сразу `failed`.

## Правила

- Не делать `docker compose down -v` — сотрётся volume Postgres
- Обновление: `git pull && docker compose --profile queue up -d --build --force-recreate`
- Проверка: `curl -sS http://127.0.0.1/api/health` — анонимный `GET /api/teachers` должен дать 401
- 502: не дергайте nginx, пока он `Restarting`. Сначала `docker compose --profile queue ps` и `logs api --tail 80`. Если `api` Up — `docker compose --profile queue up -d --force-recreate --no-deps nginx`
- Worker: `cpus: 4`, `mem_limit: 4g`, `SOLVER_NUM_WORKERS=4` (потоки = ядра). На 2 vCPU в `.env`: `SOLVER_CPUS=2` и `SOLVER_NUM_WORKERS=2`. «Заполнить всё» — CP-SAT на одну смену, не лесенка по всем учителям.
- Журнал задачи должен начинаться с «Запуск на Celery worker…». Если job `failed` с текстом про `--profile queue` — Redis/worker не подняты (солвер в api больше не запускается).

## Бэкап

Скрипт: [`deploy/backup-postgres.sh`](../deploy/backup-postgres.sh). Пример cron — в комментарии в начале файла (хранит 14 дампов в `backups/`).

```
15 3 * * * /opt/schedule/deploy/backup-postgres.sh >> /var/log/schedule-backup.log 2>&1
```

## Ресурсы (8 ГБ RAM)

Один uvicorn, один worker, swap 2 ГБ. В простое ~2.5–3.5 ГБ. Worker по умолчанию 4 ГБ (не 2 ГБ): CP-SAT на полной смене иначе уходит в swap. На 16 ГБ хоста можно `SOLVER_MEM_LIMIT=6g`.

Вне скоупа стенда: S3/MinIO, Flower, второй Celery worker, несколько uvicorn workers.