from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy import func
from sqlmodel import Field, SQLModel

from app.core.repository import BaseRepository, SoftDeleteRepository


class DummyModel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nombre: str


class DummySoftDeleteModel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nombre: str
    borrado_en: datetime | None = Field(default=None)


@pytest.mark.asyncio
async def test_base_repository_add_calls_flush_and_never_commit():
    session = AsyncMock()
    session.add = MagicMock()
    repo = BaseRepository(DummyModel, session)
    entity = DummyModel(id=1, nombre="Test")

    result = await repo.add(entity)

    assert result is entity
    session.add.assert_called_once_with(entity)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(entity)
    assert not session.commit.called, "BaseRepository jamás debe llamar a commit()"


@pytest.mark.asyncio
async def test_base_repository_update_calls_flush_and_never_commit():
    session = AsyncMock()
    repo = BaseRepository(DummyModel, session)
    entity = DummyModel(id=1, nombre="Test Actualizado")

    result = await repo.update(entity)

    assert result is entity
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(entity)
    assert not session.commit.called


@pytest.mark.asyncio
async def test_base_repository_delete_calls_delete_and_flush():
    session = AsyncMock()
    repo = BaseRepository(DummyModel, session)
    entity = DummyModel(id=1, nombre="Para Borrar")

    await repo.delete(entity)

    session.delete.assert_awaited_once_with(entity)
    session.flush.assert_awaited_once()
    assert not session.commit.called


@pytest.mark.asyncio
async def test_base_repository_get_by_id():
    session = AsyncMock()
    mock_result = MagicMock()
    expected_entity = DummyModel(id=1, nombre="Encontrado")
    mock_result.scalar_one_or_none.return_value = expected_entity
    session.execute.return_value = mock_result

    repo = BaseRepository(DummyModel, session)
    found = await repo.get_by_id(1)

    assert found is expected_entity
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_base_repository_get_all_with_pagination():
    session = AsyncMock()
    mock_result = MagicMock()
    expected_items = [DummyModel(id=1, nombre="A"), DummyModel(id=2, nombre="B")]
    mock_result.scalars.return_value.all.return_value = expected_items
    session.execute.return_value = mock_result

    repo = BaseRepository(DummyModel, session)
    items = await repo.get_all(offset=10, limit=20)

    assert items == expected_items
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_base_repository_count():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 42
    session.execute.return_value = mock_result

    repo = BaseRepository(DummyModel, session)
    total = await repo.count()

    assert total == 42
    session.execute.assert_awaited_once()


def test_soft_delete_repository_rejects_incompatible_model():
    session = AsyncMock()
    with pytest.raises(TypeError) as exc_info:
        SoftDeleteRepository(DummyModel, session)
    assert "no soporta borrado lógico" in str(exc_info.value)


@pytest.mark.asyncio
async def test_soft_delete_repository_soft_delete_sets_timestamp():
    session = AsyncMock()
    repo = SoftDeleteRepository(DummySoftDeleteModel, session)
    entity = DummySoftDeleteModel(id=1, nombre="Activo", borrado_en=None)

    result = await repo.soft_delete(entity)

    assert result.borrado_en is not None
    assert isinstance(result.borrado_en, datetime)
    session.flush.assert_awaited_once()
    assert not session.commit.called


@pytest.mark.asyncio
async def test_soft_delete_repository_soft_delete_by_id():
    session = AsyncMock()
    entity = DummySoftDeleteModel(id=2, nombre="Activo 2", borrado_en=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = entity
    session.execute.return_value = mock_result

    repo = SoftDeleteRepository(DummySoftDeleteModel, session)
    result = await repo.soft_delete(2)

    assert result.borrado_en is not None
    session.flush.assert_awaited_once()
    assert not session.commit.called


@pytest.mark.asyncio
async def test_soft_delete_repository_soft_delete_not_found_raises():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    repo = SoftDeleteRepository(DummySoftDeleteModel, session)
    with pytest.raises(ValueError) as exc_info:
        await repo.soft_delete(999)
    assert "No se encontró" in str(exc_info.value)


@pytest.mark.asyncio
async def test_soft_delete_repository_get_all():
    session = AsyncMock()
    mock_result = MagicMock()
    expected = [DummySoftDeleteModel(id=1, nombre="Activo", borrado_en=None)]
    mock_result.scalars.return_value.all.return_value = expected
    session.execute.return_value = mock_result

    repo = SoftDeleteRepository(DummySoftDeleteModel, session)
    items = await repo.get_all(offset=0, limit=10)

    assert items == expected
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_soft_delete_repository_count():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 5
    session.execute.return_value = mock_result

    repo = SoftDeleteRepository(DummySoftDeleteModel, session)
    count = await repo.count()

    assert count == 5
    session.execute.assert_awaited_once()
