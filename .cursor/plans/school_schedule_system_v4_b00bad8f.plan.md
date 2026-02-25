---
name: School Schedule System v4
overview: Веб-сервис для составления школьного расписания. PostgreSQL, импорт из Excel, полноценный CRUD, ручной и автоматический режимы. Python/Flask/SQLAlchemy/HTML/JS.
todos:
  - id: setup-project
    content: Структура проекта, Flask app, requirements.txt, .env, PostgreSQL
    status: completed
  - id: create-models
    content: Все SQLAlchemy модели + миграции PostgreSQL
    status: completed
    dependencies:
      - setup-project
  - id: base-ui
    content: Базовый UI шаблон Bootstrap 5, навигация
    status: completed
    dependencies:
      - setup-project
  - id: excel-import
    content: Импорт учителей и учебного плана из Excel + шаблоны
    status: completed
    dependencies:
      - create-models
      - base-ui
  - id: crud-teachers
    content: CRUD для учителей
    status: completed
    dependencies:
      - base-ui
      - create-models
  - id: crud-classrooms
    content: CRUD для кабинетов
    status: completed
    dependencies:
      - base-ui
      - create-models
  - id: crud-classes
    content: CRUD для классов + привязка к сменам
    status: completed
    dependencies:
      - base-ui
      - create-models
  - id: crud-shifts
    content: Управление сменами
    status: completed
    dependencies:
      - base-ui
      - create-models
  - id: crud-subjects
    content: CRUD для предметов + выбор цвета
    status: completed
    dependencies:
      - base-ui
      - create-models
  - id: crud-workload
    content: Редактирование нагрузки (часы)
    status: completed
    dependencies:
      - crud-classes
      - crud-subjects
  - id: assign-teachers
    content: Назначение учителей к предметам-классам
    status: completed
    dependencies:
      - crud-workload
      - crud-teachers
  - id: schedule-grid
    content: Сетка расписания с фильтрами
    status: completed
    dependencies:
      - assign-teachers
      - crud-shifts
  - id: drag-drop
    content: Drag and Drop для уроков
    status: completed
    dependencies:
      - schedule-grid
  - id: validation
    content: Валидация конфликтов
    status: completed
    dependencies:
      - drag-drop
  - id: auto-scheduler
    content: Автоматическое составление расписания
    status: completed
    dependencies:
      - validation
  - id: reports
    content: Отчёты и экспорт Excel/PDF
    status: completed
    dependencies:
      - auto-scheduler
---

# План разработки: Система составления школьного расписания (v4)

## Технологический стек

| Компонент | Технология |

|-----------|------------|

| Backend | Python 3.11+, Flask |

| ORM | SQLAlchemy |

| База данных | **PostgreSQL** |

| Миграции | Flask-Migrate (Alembic) |

| Excel | pandas, openpyxl |

| Frontend | HTML5, CSS3, JavaScript, Bootstrap 5 |

| Drag and Drop | SortableJS |

---

## Архитектура системы

```mermaid
flowchart TB
    subgraph input [Ввод данных]
        Excel1[teachers.xlsx]
        Excel2[curriculum_elementary.xlsx]
        Excel3[curriculum_secondary.xlsx]
        WebUI[Веб-интерфейс CRUD]
    end
    
    subgraph backend [Backend Flask]
        Importer[Excel Importer]
        Routes[API Routes]
        Services[Business Logic]
        Validators[Conflict Validators]
        AutoScheduler[Auto Scheduler]
    end
    
    subgraph frontend [Frontend]
        CRUD[CRUD страницы]
        DnD[Drag and Drop]
        Grid[Schedule Grid]
    end
    
    subgraph database [PostgreSQL]
        Teachers[(teachers)]
        Classrooms[(classrooms)]
        Classes[(school_classes)]
        Subjects[(subjects)]
        Assignments[(teaching_assignments)]
        Schedule[(schedule_cells)]
    end
    
    Excel1 --> Importer
    Excel2 --> Importer
    Excel3 --> Importer
    WebUI --> Routes
    Importer --> database
    Routes --> Services
    Services --> database
    CRUD --> Routes
    DnD --> Routes
    Grid --> Routes
```

---

## Структура проекта

```
schedule/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models/
│   ├── routes/
│   ├── services/
│   │   ├── excel_import.py
│   │   ├── schedule_builder.py
│   │   ├── auto_scheduler.py
│   │   └── validators.py
│   ├── static/
│   └── templates/
├── excel_templates/
├── migrations/
├── requirements.txt
├── run.py
├── .env                    # DATABASE_URL для PostgreSQL
└── PROJECT_GOALS.md
```

---

## Настройка PostgreSQL

Конфигурация через переменные окружения:

```
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/school_schedule
SECRET_KEY=your-secret-key
```

requirements.txt:

```
flask
flask-sqlalchemy
flask-migrate
psycopg2-binary    # PostgreSQL драйвер
python-dotenv
pandas
openpyxl
```

---

## Этап 1: Инфраструктура

- Flask app factory, конфигурация из .env
- SQLAlchemy + Flask-Migrate + PostgreSQL
- Все модели данных
- Базовый UI шаблон (Bootstrap 5)

---

## Этап 2: Импорт из Excel (первоначальная загрузка)

**teachers.xlsx:**

| ФИО | Краткое имя | Email | Телефон |

**curriculum_elementary.xlsx / curriculum_secondary.xlsx:**

- Строки = классы
- Столбцы = предметы
- Ячейки = часы в неделю

Функционал: страница импорта, шаблоны для скачивания, валидация

---

## Этап 3: Полноценный CRUD

| Сущность | Импорт Excel | CRUD в системе |

|----------|--------------|----------------|

| Учителя | Да | Полный CRUD |

| Кабинеты | Нет | Полный CRUD |

| Классы | Да (из таблицы) | Полный CRUD + привязка к смене |

| Смены | Нет | Полный CRUD |

| Предметы | Да (из таблицы) | Полный CRUD + цвет |

| Нагрузка | Да | Редактирование часов |

| Назначения | Нет | Назначение учителя + подгруппа |

---

## Этап 4: Назначение учителей

- Таблица: предмет + класс + часы + учитель + подгруппа
- Два учителя на предмет-класс = подгруппы

---

## Этап 5: Ручное составление расписания

- Сетка (дни x уроки x классы)
- Фильтры по школе и смене
- Drag and Drop
- Валидация конфликтов

---

## Этап 6: Автоматическое составление

- Алгоритм "лесенка"
- Граф конфликтов

---

## Этап 7: Отчёты и экспорт

- Печать расписания
- Экспорт Excel/PDF

---

## Workflow

```mermaid
flowchart LR
    Import[Импорт Excel] --> Edit[Редактирование в системе]
    Edit --> Assign[Назначение учителей]
    Assign --> Schedule[Составление расписания]
    Schedule --> Export[Экспорт]
```