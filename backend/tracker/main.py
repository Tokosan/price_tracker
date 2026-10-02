"""App FastAPI. Correr con UN solo worker: el scheduler vive en este proceso."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from sqlalchemy import text

from tracker import db as dbmod
from tracker.api import admin, auth, channels, watches
from tracker.api.deps import CSRFMiddleware
from tracker.config import settings
from tracker.notifications import telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx loguea la URL completa de cada petición, y la de Telegram lleva el token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("tracker")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.check_production()
    sched = None
    poll_task = None
    if settings.scheduler_enabled:
        from tracker import scheduler

        sched = scheduler.start()
    if telegram.bot is not None and settings.scheduler_enabled:
        poll_task = asyncio.create_task(telegram.bot.poll_forever())
    elif telegram.bot is None:
        log.info("Telegram no configurado (falta TELEGRAM_BOT_TOKEN): solo historial in-app")
    try:
        yield
    finally:
        if poll_task:
            poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await poll_task
        if sched:
            sched.shutdown(wait=False)


app = FastAPI(title="price_tracker", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(CSRFMiddleware)
app.include_router(auth.router)
app.include_router(watches.router)
app.include_router(channels.router)
app.include_router(admin.router)


@app.get("/api/health")
def health() -> dict:
    with dbmod.engine.connect() as conn:
        journal = conn.execute(text("PRAGMA journal_mode")).scalar()
    bot = telegram.bot
    return {
        "ok": True,
        "db_journal_mode": journal,
        "scheduler": settings.scheduler_enabled,
        "telegram": (
            {
                "configured": True,
                "bot": bot.username,
                "polling": bot.polling,
                "error": bot.last_error,
            }
            if bot
            else {"configured": False}
        ),
    }
