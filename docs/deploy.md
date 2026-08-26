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
- После `--build` без `--force-recreate` возможен 502: nginx держит IP старого `api`
- Worker: `SOLVER_NUM_WORKERS=2` (контейнер 1.5 CPU). «Заполнить всё» — CP-SAT на одну смену, не лесенка по всем учителям.

## Бэкап

Скрипт: [`deploy/backup-postgres.sh`](../deploy/backup-postgres.sh). Пример cron — в комментарии в начале файла.

## Ресурсы (8 ГБ RAM)

Один uvicorn, один worker, swap 2 ГБ. В простое ~2.5–3.5 ГБ, на пике автосоставления ~5–7 ГБ.
