# Система составления школьного расписания

Веб-приложение для составления и управления школьным расписанием с поддержкой ручного и автоматического режимов.

## Возможности

- **Импорт данных** из Excel (учителя, учебный план)
- **Справочники**: учителя, кабинеты, классы, смены, предметы
- **Нагрузка**: редактирование часов по предметам и классам
- **Назначения**: связь учитель-предмет-класс, деление на группы
- **Ручное расписание**: drag & drop, валидация конфликтов
- **Автоматическое составление**: стратегия «лесенка» по учителю и CP-SAT solver
- **Отчёты**: просмотр и экспорт в Excel

## Требования

- Python 3.11+
- Node.js 20+
- PostgreSQL 14+ (или SQLite для разработки)

## Установка

### 1. Клонируйте репозиторий

```bash
cd schedule
```

### 2. Создайте виртуальное окружение

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
npm install
npm install --prefix frontend
```

### 4. Настройте базу данных

Скопируйте файл конфигурации:

```bash
copy env.example .env   # Windows
cp env.example .env     # Linux/Mac
```

По умолчанию используется SQLite (`instance/school_schedule.db`). Для PostgreSQL создайте базу и укажите URL в `.env`:

```sql
CREATE DATABASE school_schedule;
```

```
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/school_schedule
```

### 5. Примените миграции

```bash
alembic upgrade head
```

При первом запуске API миграции применяются автоматически, если схема ещё не готова.

### 6. Создайте Excel-шаблоны (опционально)

```bash
python create_templates.py
```

### 7. Запустите приложение

Из корня репозитория:

```bash
npm run dev
```

`npm run dev` поднимает FastAPI (`python run_api.py`, порт 8000) и Vite одновременно. Откройте http://127.0.0.1:5173 — запросы `/api/*` проксируются на API. Если API ещё не поднялся, в шапке появится баннер «API недоступен».

**Раздельный запуск:**

```bash
# Backend
python run_api.py
# или
python -m uvicorn backend.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev
```

Документация OpenAPI: http://127.0.0.1:8000/docs

Production-сборка фронта (`npm run build`) кладёт файлы в `frontend/dist`; FastAPI отдаёт SPA с того же порта 8000.

**Ошибка `no such table`:** у выбранной базы ещё нет таблиц из миграций. Выполните из корня проекта (с активированным venv): `alembic upgrade head`.

## Структура проекта

```
schedule/
├── app/
│   ├── config.py            # Конфигурация и DATABASE_URL
│   ├── db.py                # SQLAlchemy Base
│   ├── models/              # Модели данных
│   ├── services/            # Бизнес-логика (автосоставление, валидация, импорт)
│   └── excel_templates/     # Шаблоны для импорта
├── backend/                 # FastAPI (JSON API)
├── frontend/                # React (Vite + TypeScript)
├── migrations/              # Alembic
├── tests/                   # Pytest
├── uploads/                 # Загруженные файлы
├── alembic.ini
├── requirements.txt
├── run_api.py
└── PROJECT_GOALS.md
```

## Использование

### 1. Импорт данных

1. Перейдите в раздел «Импорт»
2. Скачайте шаблоны Excel
3. Заполните данные
4. Загрузите файлы

### 2. Настройка

1. Добавьте смены (начальная / основная школа)
2. Привяжите классы к сменам
3. Назначьте учителей к предметам

### 3. Составление расписания

1. Перейдите в «Расписание»
2. Выберите уровень школы и смену
3. Перетаскивайте предметы в ячейки
4. Или используйте автоматическое заполнение

### 4. Экспорт

1. Перейдите в «Отчёты»
2. Выберите класс или учителя
3. Скачайте Excel или распечатайте

## Деление на группы

Если нужно разделить предмет на группы (например, информатика или иностранный язык):

1. Перейдите в «Предметы» и нажмите «Назначения» у нужного предмета
2. Выберите уровень школы (НШ / ОШ) и добавьте до двух учителей
3. Отметьте у обоих чекбокс одного и того же класса — он автоматически разделится на подгруппы

Общий просмотр и точечная замена учителя по конкретной нагрузке доступны на странице «Назначения».

## Технологии

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, Alembic
- **Database**: PostgreSQL (или SQLite для разработки и тестов)
- **Frontend**: React + Vite + TypeScript + `@tanstack/react-query`, Bootstrap 5
- **Excel**: pandas, openpyxl
- **Автосоставление**: OR-Tools CP-SAT

## Тесты

```bash
python -m pytest -q
```

`tests/conftest.py` использует временный SQLite; миграции для тестов не нужны.

## Лицензия

MIT
