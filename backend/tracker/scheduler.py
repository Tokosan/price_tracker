"""Scheduler en el mismo proceso (por eso uvicorn corre con UN solo worker)."""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from tracker.checker import check_product, is_in_flight
from tracker.db import SessionLocal, utcnow
from tracker.models import Product, User, Watch, WatchItem

log = logging.getLogger("tracker.scheduler")

TICK_SECONDS = 60
_tasks: set[asyncio.Task] = set()


def due_product_ids(limit: int = 50) -> list[int]:
    """Productos con al menos un Watch activo (de un usuario activo) y revisión vencida."""
    with SessionLocal() as db:
        active = (
            select(WatchItem.product_id)
            .join(Watch, Watch.id == WatchItem.watch_id)
            .join(User, User.id == Watch.user_id)
            .where(Watch.active.is_(True), User.active.is_(True))
        )
        return list(
            db.scalars(
                select(Product.id)
                .where(Product.id.in_(active), Product.next_check_at <= utcnow())
                .order_by(Product.next_check_at)
                .limit(limit)
            )
        )


async def tick() -> None:
    ids = [pid for pid in due_product_ids() if not is_in_flight(pid)]
    if ids:
        log.info("revisando %d producto(s): %s", len(ids), ids)
    # Cada revisión es una tarea; el rate limit por dominio las serializa por tienda.
    for pid in ids:
        task = asyncio.create_task(check_product(pid))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


def start() -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(
        tick,
        "interval",
        seconds=TICK_SECONDS,
        id="tick",
        max_instances=1,
        coalesce=True,
        next_run_time=utcnow(),
    )
    sched.start()
    log.info("scheduler iniciado (tick cada %ss)", TICK_SECONDS)
    return sched
