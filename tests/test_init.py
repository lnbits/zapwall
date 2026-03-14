import pytest
from fastapi import APIRouter

from .. import zapwall_ext


@pytest.mark.asyncio
async def test_router():
    router = APIRouter()
    router.include_router(zapwall_ext)
