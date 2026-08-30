# Документация

Оглавление. Корень репозитория — краткий [README](../README.md) с запуском на Windows.

| Документ | Содержание |
|----------|------------|
| [Архитектура и структура](architecture.md) | Слои, дерево, модели, API, UI, правила слота/кабинета, зеркала Python↔TS |
| [Продукт](product.md) | Цель, сущности, правила (кабинеты, сложность предмета), стек |
| [Этапы выкладки](stages.md) | Чеклист стенда: хост, Docker, auth, админка, очередь |
| [Локальная разработка (Windows)](local-windows.md) | Два процесса: FastAPI и Vite |
| [Стенд / Docker](deploy.md) | Compose, `.env`, Postgres, nginx, бэкапы, RAM |

Alembic head: `14subject_difficulty`. Flask в runtime нет.

## Слои приложения

```
браузер  →  Vite :5173 (dev) / nginx (прод)
                ↓  /api
            FastAPI :8000  (SPA из frontend/dist на стенде)
                ↓
            app/services → app/domain + app/models
                ↓
            SQLite (dev) / PostgreSQL (стенд)
                ↓
            OR-Tools  (локально поток API; на стенде Celery + Redis)
```

Границы слоёв и write-path — в [architecture.md](architecture.md). Деплой — [deploy.md](deploy.md).