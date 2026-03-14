import asyncio

from fastapi import APIRouter
from loguru import logger

from .crud import db
from .tasks import run_zapwall_listener
from .views import zapwall_generic_router
from .views_api import zapwall_api_router

zapwall_ext = APIRouter(prefix="/zapwall", tags=["zapwall"])
zapwall_ext.include_router(zapwall_generic_router)
zapwall_ext.include_router(zapwall_api_router)

zapwall_static_files = [{"path": "/zapwall/static", "name": "zapwall_static"}]

scheduled_tasks: list[asyncio.Task] = []


def zapwall_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def zapwall_start():
    from lnbits.tasks import create_permanent_unique_task

    task = create_permanent_unique_task("ext_zapwall_listener", run_zapwall_listener)
    scheduled_tasks.append(task)


__all__ = ["db", "zapwall_ext", "zapwall_start", "zapwall_static_files", "zapwall_stop"]
