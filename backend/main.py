"""FastAPI entrypoint."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from backend.database import ensure_database
from backend.deps import flask_app
from backend.routers import (
    assignments,
    classrooms,
    dashboard,
    health,
    import_data,
    reports,
    schedule,
    school_classes,
    shifts,
    subjects,
    teachers,
    workload,
)

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_database(flask_app)
    yield


app = FastAPI(title="School Schedule API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(OperationalError)
async def sqlalchemy_operational_handler(
    _request: Request, exc: OperationalError
) -> JSONResponse:
    """Понятный ответ, если SQLite без миграций или пустая БД."""
    msg = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
    lowered = msg.lower()
    if "no such table" in lowered or "no such column" in lowered:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Схема базы данных устарела или неполная. "
                    "Выполните из корня проекта: set FLASK_APP=run.py && flask db upgrade"
                ),
            },
        )
    raise exc


@app.get("/", include_in_schema=False)
def root() -> Response:
    """Сервим SPA, если есть собранный фронт; иначе — Swagger."""
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(
            index,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )
    return RedirectResponse(url="/docs")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Без иконки: убираем лишний 404 в логах при заходе в браузер."""
    fav = FRONTEND_DIST / "favicon.svg"
    if fav.is_file():
        return FileResponse(fav)
    return Response(status_code=204)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(teachers.router, prefix="/api/teachers", tags=["teachers"])
app.include_router(classrooms.router, prefix="/api/classrooms", tags=["classrooms"])
app.include_router(
    school_classes.router, prefix="/api/school-classes", tags=["school-classes"]
)
app.include_router(shifts.router, prefix="/api/shifts", tags=["shifts"])
app.include_router(subjects.router, prefix="/api/subjects", tags=["subjects"])
app.include_router(workload.router, prefix="/api/workload", tags=["workload"])
app.include_router(schedule.router, prefix="/api/schedule", tags=["schedule"])
app.include_router(assignments.router, prefix="/api/assignments", tags=["assignments"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(import_data.router, prefix="/api/import", tags=["import"])


if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> Response:
        """Production fallback: serve SPA index.html for client-side routes."""
        if full_path.startswith(("api/", "docs", "openapi.json", "redoc", "assets/")):
            return Response(status_code=404)
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(
                index,
                headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
            )
        return Response(status_code=404)
