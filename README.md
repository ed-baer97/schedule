# Система составления школьного расписания

Веб-приложение для составления и управления школьным расписанием: справочники, нагрузка, ручная сетка, автосоставление (OR-Tools), отчёты. Стек — **FastAPI + React**, мультиарендность (школы), JWT-auth, Docker.

## Документация

| Документ | О чём |
|----------|--------|
| [docs/](docs/README.md) | Оглавление |
| [Архитектура и структура](docs/architecture.md) | Дерево репозитория, слои, модели, API, правила слота и кабинета |
| [Продукт](docs/product.md) | Цель, сущности, роли, правила, стек |
| [Этапы выкладки](docs/stages.md) | Чеклист стенда (хост, Docker, auth, очередь) |
| [Локальная разработка (Windows)](docs/local-windows.md) | Первый раз и ежедневный запуск |
| [Стенд / Docker](docs/deploy.md) | Compose, бэкапы, ограничения RAM |

## Запуск на Windows (фронт и бэк отдельно)

Нужны Python 3.11+ и Node.js 20+.

### Первый раз

```powershell
cd schedule
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
npm install --prefix frontend
Copy-Item env.example .env
alembic upgrade head
```

В `.env` для локального HTTP: `COOKIE_SECURE=false`.

Логин из `env.example` (создаётся при пустой таблице `users`): `admin@example.com` / `admin12345`.

После входа `platform_admin` без школы попадает в **/admin** — создайте школу и пригласите админа школы. Дальше работайте под админом школы.

### Каждый день — два окна PowerShell

**Backend** (окно 1):

```powershell
cd schedule
.\venv\Scripts\activate
python run_api.py
```

API / OpenAPI: http://127.0.0.1:8000/docs

**Frontend** (окно 2):

```powershell
cd schedule\frontend
npm run dev
```

UI: http://127.0.0.1:5173 — Vite проксирует `/api` на порт 8000. Сначала поднимите API, затем Vite.

Подробности: [docs/local-windows.md](docs/local-windows.md).

## Docker (стенд)

```bash
git clone <repo> /opt/schedule && cd /opt/schedule
cp env.example .env
docker compose up -d --build
docker compose --profile queue up -d   # автосоставление в фоне
```

Не делать `docker compose down -v` (сотрёт БД). Полная инструкция: [docs/deploy.md](docs/deploy.md).

## Тесты

```powershell
.\venv\Scripts\activate
python -m pytest -q
```

## Лицензия

MIT
