from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, DateTime, Index, text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.ordenes.models import OrdenTrabajo
    from app.modules.usuarios.models import Usuario


class Cliente(SQLModel, table=True):
    __tablename__ = "cliente"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: Optional[int] = Field(
        default=None,
        foreign_key="usuario.id",
        unique=True,
        nullable=True,
    )
    nombre: str = Field(max_length=255, nullable=False)
    documento: str = Field(max_length=50, unique=True, index=True, nullable=False)
    telefono: str = Field(max_length=50, nullable=False)

    usuario: Optional["Usuario"] = Relationship(back_populates="cliente")
    vehiculos: list["Vehiculo"] = Relationship(back_populates="cliente")


class Vehiculo(SQLModel, table=True):
    __tablename__ = "vehiculo"
    __table_args__ = (
        CheckConstraint("anio BETWEEN 1950 AND 2100", name="ck_vehiculo_anio_valido"),
        Index(
            "uq_vehiculo_patente_activa",
            "patente",
            unique=True,
            postgresql_where=text("borrado_en IS NULL"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    cliente_id: int = Field(foreign_key="cliente.id", index=True, nullable=False)
    patente: str = Field(max_length=20, nullable=False)
    marca: str = Field(max_length=100, nullable=False)
    modelo: str = Field(max_length=100, nullable=False)
    anio: int = Field(nullable=False)
    borrado_en: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )

    cliente: Cliente = Relationship(back_populates="vehiculos")
    ordenes: list["OrdenTrabajo"] = Relationship(back_populates="vehiculo")
