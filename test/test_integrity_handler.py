from unittest.mock import MagicMock
from fastapi import Request
from sqlalchemy.exc import IntegrityError
import pytest

from main import manejar_integrity_error


@pytest.fixture
def mock_request():
    return MagicMock(spec=Request)


def crear_integrity_error(constraint_name: str | None = None, sqlstate: str | None = None) -> IntegrityError:
    orig = MagicMock()
    orig.constraint_name = constraint_name
    orig.sqlstate = sqlstate
    orig.pgcode = sqlstate
    # Simular mensaje con SQL interno que jamás debe filtrarse
    statement = "INSERT INTO usuario (email) VALUES ('bad@sql.com')"
    params = ("bad@sql.com",)
    return IntegrityError(statement, params, orig)


@pytest.mark.asyncio
async def test_handler_usuario_email_key_409(mock_request):
    exc = crear_integrity_error(constraint_name="usuario_email_key")
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 409
    body = response.body.decode("utf-8")
    assert "El correo ya se encuentra registrado" in body
    assert "INSERT INTO" not in body


@pytest.mark.asyncio
async def test_handler_ix_usuario_email_409(mock_request):
    exc = crear_integrity_error(constraint_name="ix_usuario_email")
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 409
    body = response.body.decode("utf-8")
    assert "El correo ya se encuentra registrado" in body


@pytest.mark.asyncio
async def test_handler_uq_asignacion_rol_activa_409(mock_request):
    exc = crear_integrity_error(constraint_name="uq_asignacion_rol_activa")
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 409
    body = response.body.decode("utf-8")
    assert "vigente" in body.lower() or "asignación" in body.lower()
    assert "uq_asignacion_rol_activa" not in body


@pytest.mark.asyncio
async def test_handler_ck_asignacion_rol_rol_valido_422(mock_request):
    exc = crear_integrity_error(constraint_name="ck_asignacion_rol_rol_valido")
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 422
    body = response.body.decode("utf-8")
    assert "Rol inválido" in body
    assert "ck_asignacion_rol_rol_valido" not in body


@pytest.mark.asyncio
async def test_handler_asignacion_rol_usuario_id_fkey_404(mock_request):
    exc = crear_integrity_error(constraint_name="asignacion_rol_usuario_id_fkey")
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 404
    body = response.body.decode("utf-8")
    assert "Usuario no encontrado" in body


@pytest.mark.asyncio
async def test_handler_uq_repuesto_codigo_activo_409(mock_request):
    exc = crear_integrity_error(constraint_name="uq_repuesto_codigo_activo")
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 409
    body = response.body.decode("utf-8")
    assert "código de repuesto ya se encuentra registrado" in body
    assert "uq_repuesto_codigo_activo" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("constraint", "esperado"),
    [
        ("ck_repuesto_precio_positivo", "El precio debe ser mayor a cero"),
        ("ck_repuesto_stock_no_negativo", "El stock no puede ser negativo"),
        (
            "ck_movimiento_stock_cantidad_no_cero",
            "La cantidad del movimiento no puede ser cero",
        ),
        ("ck_historial_precio_nuevo_positivo", "El precio nuevo debe ser mayor a cero"),
        (
            "ck_historial_precio_cambio_requerido",
            "El precio nuevo debe ser distinto del anterior",
        ),
    ],
)
async def test_handler_check_de_repuestos_422(mock_request, constraint, esperado):
    exc = crear_integrity_error(constraint_name=constraint)
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 422
    body = response.body.decode("utf-8")
    assert esperado in body
    assert constraint not in body
    assert "INSERT INTO" not in body


@pytest.mark.asyncio
async def test_handler_fallback_sqlstate_23505_409(mock_request):
    exc = crear_integrity_error(constraint_name="constraint_desconocido", sqlstate="23505")
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 409
    body = response.body.decode("utf-8")
    assert "El recurso ya existe" in body


@pytest.mark.asyncio
async def test_handler_fallback_sqlstate_23514_422(mock_request):
    exc = crear_integrity_error(constraint_name=None, sqlstate="23514")
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 422
    body = response.body.decode("utf-8")
    assert "Valor inválido" in body


@pytest.mark.asyncio
async def test_handler_desconocido_responde_400(mock_request):
    exc = crear_integrity_error(constraint_name="desconocido", sqlstate="99999")
    response = await manejar_integrity_error(mock_request, exc)

    assert response.status_code == 400
    body = response.body.decode("utf-8")
    assert "No se pudo completar la operación" in body
    assert "desconocido" not in body
