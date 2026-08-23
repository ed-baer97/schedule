# Документация

Оглавление. Корень репозитория — краткий [README](../README.md) с запуском на Windows.

| Документ | Содержание |
|----------|------------|
| [Архитектура и структура](architecture.md) | Дерево репозитория, слои, модели, API, страницы UI |
| [Продукт](product.md) | Цель, сущности, правила, стек |
| [Этапы выкладки](stages.md) | Чеклист стенда: хост, Docker, auth, админка, очередь |
| [Локальная разработка (Windows)](local-windows.md) | Два процесса: FastAPI и Vite |
| [Стенд / Docker](deploy.md) | Compose, Postgres, nginx, бэкапы |

## Слои приложения

```
браузер  →  Vite :5173 (dev) / nginx (прод)
                ↓  /api
            FastAPI :8000
                ↓
            SQLAlchemy  →  SQLite (dev) / PostgreSQL (стенд)
                ↓
            OR-Tools  (локально sync; на стенде Celery + Redis)
```
