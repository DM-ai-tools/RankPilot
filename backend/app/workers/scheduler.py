"""APScheduler — polls rp_jobs every few seconds and runs pending maps_scan tasks."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.content_publish_service import publish_due_approved_content
from app.workers.maps_worker import poll_and_run_jobs

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def register_jobs() -> None:
    scheduler.add_job(
        poll_and_run_jobs,
        "interval",
        seconds=10,
        id="maps_scan_poll",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info("Registered maps_scan_poll job (every 10 s)")
    scheduler.add_job(
        publish_due_approved_content,
        "interval",
        hours=1,
        id="content_publish_due",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info("Registered content_publish_due job (every 1 h)")


async def run_worker() -> None:
    register_jobs()
    scheduler.start()
    import asyncio
    await asyncio.Event().wait()
