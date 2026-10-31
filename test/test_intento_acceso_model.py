"""Tests para el modelo IntentoAcceso (task 1.2).

El modelo ya vive en app/modules/usuarios/models.py.
Estos tests verifican instanciación, defaults y campos requeridos.
"""
from datetime import datetime, timezone

# Importamos todos los modelos relacionados para que SQLAlchemy resuelva
# los Relationship entre módulos antes de instanciar cualquier modelo.
import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
from app.modules.usuarios.models import IntentoAcceso


def test_intento_acceso_instancia_minima():
    """Puede instanciarse con los campos requeridos (sin id)."""
    intento = IntentoAcceso(email="a@b.com", ip="127.0.0.1", exito=False)
    assert intento.email == "a@b.com"
    assert intento.ip == "127.0.0.1"
    assert intento.exito is False
    assert intento.id is None


def test_intento_acceso_exito_true():
    """El campo exito puede ser True."""
    intento = IntentoAcceso(email="x@y.com", ip="10.0.0.1", exito=True)
    assert intento.exito is True


def test_intento_acceso_cuando_default_utcnow():
    """El campo 'cuando' se inicializa automáticamente con datetime timezone-aware."""
    before = datetime.now(timezone.utc)
    intento = IntentoAcceso(email="z@w.com", ip="192.168.1.1", exito=False)
    after = datetime.now(timezone.utc)

    assert intento.cuando is not None
    assert intento.cuando.tzinfo is not None
    assert before <= intento.cuando <= after


def test_intento_acceso_campos_correctos():
    """Los campos del modelo tienen los tipos esperados."""
    intento = IntentoAcceso(email="test@test.com", ip="1.2.3.4", exito=True)
    assert isinstance(intento.email, str)
    assert isinstance(intento.ip, str)
    assert isinstance(intento.exito, bool)
    assert isinstance(intento.cuando, datetime)
