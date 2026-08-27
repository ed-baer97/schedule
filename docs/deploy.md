# Стенд и Docker

Чеклист выкладки: [stages.md](stages.md).

## Compose

```bash
git clone <repo> /opt/schedule && cd /opt/schedule
cp env.example .env
# POSTGRES_PASSWORD, SECRET_KEY, BOOTSTRAP_ADMIN_*, COOKIE_SECURE=true
docker compose up -d --build
# автосоставление в фоне:
docker compose --profile queue up -d
```

Сервисы без профиля `queue`: `nginx` :80 → `api` → Postgres.

С `--profile queue` добавляются Redis и один Celery worker (solver только там).

## Правила

- Cloudflare Tunnel направлять на `http://127.0.0.1:80`
- Не делать `docker compose down -v` — сотрётся volume Postgres
- `.env` и токен туннеля в git не класть
- Обновление: `git pull && docker compose --profile queue up -d --build --force-recreate`
- 502: не дергайте nginx, пока он `Restarting`. Сначала `docker compose --profile queue ps` и `logs api --tail 80`. Если `api` Up — `docker compose --profile queue up -d --force-recreate --no-deps nginx`, затем `curl -sS http://127.0.0.1/api/health`
- Worker: `cpus: 4`, `mem_limit: 4g`, `SOLVER_NUM_WORKERS=4` (потоки = ядра). На 2 vCPU в `.env`: `SOLVER_CPUS=2` и `SOLVER_NUM_WORKERS=2`. «Заполнить всё» — CP-SAT на одну смену, не лесенка по всем учителям.
- Журнал задачи должен начинаться с «Запуск на Celery worker…». Если «в процессе API» — Redis/worker недоступны, солвер сидит в контейнере api (512 МБ).

## Бэкап

Скрипт: [`deploy/backup-postgres.sh`](../deploy/backup-postgres.sh). Пример cron — в комментарии в начале файла.

## Ресурсы (8 ГБ RAM)

Один uvicorn, один worker, swap 2 ГБ. В простое ~2.5–3.5 ГБ. Worker по умолчанию 4 ГБ (не 2 ГБ): CP-SAT на полной смене иначе уходит в swap. На 16 ГБ хоста можно `SOLVER_MEM_LIMIT=6g`.
