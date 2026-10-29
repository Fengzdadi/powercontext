"""ExamRadar FastAPI application."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import get_settings
from .seekdb import ensure_tables
from .learning_store import ensure_learning_tables
from .routes import health, documents, search, coverage, usage, sessions, quiz, memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_tables()
    ensure_learning_tables()
    yield


app = FastAPI(title="ExamRadar", version="0.1.0", lifespan=lifespan)

s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=s.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(coverage.router)
app.include_router(usage.router)
app.include_router(sessions.router)
app.include_router(quiz.router)
app.include_router(memory.router)

_static_dir = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
def index():
    return FileResponse(_static_dir / "index.html")


@app.get("/import.html")
def import_page():
    return FileResponse(_static_dir / "import.html")


@app.get("/ask.html")
def ask_page():
    return FileResponse(_static_dir / "ask.html")


@app.get("/radar.html")
def radar_page():
    return FileResponse(_static_dir / "radar.html")


@app.get("/usage.html")
def usage_page():
    return FileResponse(_static_dir / "usage.html")


@app.get("/coach.html")
def coach_page():
    return FileResponse(_static_dir / "coach.html")


@app.get("/memory.html")
def memory_page():
    return FileResponse(_static_dir / "memory.html")


if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
