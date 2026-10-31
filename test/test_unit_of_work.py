from unittest.mock import AsyncMock
import pytest

from app.core.unit_of_work import UnitOfWork


@pytest.mark.asyncio
async def test_uow_commit_on_clean_exit():
    session = AsyncMock()
    uow = UnitOfWork(session)

    async with uow as ctx:
        assert ctx is uow

    session.commit.assert_awaited_once()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


@pytest.mark.asyncio
async def test_uow_rollback_on_exception():
    session = AsyncMock()
    uow = UnitOfWork(session)

    with pytest.raises(RuntimeError) as exc_info:
        async with uow:
            raise RuntimeError("Fallo transaccional crítico")

    assert "Fallo transaccional" in str(exc_info.value)
    session.rollback.assert_awaited_once()
    session.commit.assert_not_called()
    session.close.assert_not_called()


@pytest.mark.asyncio
async def test_uow_manual_commit_and_rollback():
    session = AsyncMock()
    uow = UnitOfWork(session)

    await uow.commit()
    session.commit.assert_awaited_once()

    await uow.rollback()
    session.rollback.assert_awaited_once()
    session.close.assert_not_called()
