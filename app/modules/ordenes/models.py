from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, DateTime, Numeric, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.clientes.models import Vehiculo
    from app.modules.repuestos.models import MovimientoStock, Repuesto
    from app.modules.usuarios.models import Usuario


class EstadoOrden(SQLModel, table=True):
    __tablename__ = "estado_orden"

    codigo: str = Field(primary_key=True, max_length=50)
    descripcion: str = Field(max_length=255, nullable=False)
    posicion: int = Field(unique=True, nullable=False)
    es_final: bool = Field(default=False, nullable=False)

    ordenes: list["OrdenTrabajo"] = Relationship(back_populates="estado_rel")


class OrdenTrabajo(SQLModel, table=True):
    __tablename__ = "orden_trabajo"
    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_orden_trabajo_total_no_negativo"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    vehiculo_id: int = Field(foreign_key="vehiculo.id", index=True, nullable=False)
    mecanico_id: Optional[int] = Field(
        default=None,
        foreign_key="usuario.id",
        index=True,
        nullable=True,
    )
    estado: str = Field(
        foreign_key="estado_orden.codigo",
        index=True,
        max_length=50,
        nullable=False,
    )
    falla: str = Field(max_length=500, nullable=False)
    creada_en: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    total: Decimal = Field(
        default=Decimal("0.00"),
        sa_type=Numeric(12, 2),
        nullable=False,
    )

    vehiculo: "Vehiculo" = Relationship(back_populates="ordenes")
    mecanico: Optional["Usuario"] = Relationship(back_populates="ordenes_como_mecanico")
    estado_rel: EstadoOrden = Relationship(back_populates="ordenes")
    items: list["ItemOrden"] = Relationship(back_populates="orden")
    historial_estados: list["HistorialEstadoOrden"] = Relationship(back_populates="orden")
    movimientos_stock: list["MovimientoStock"] = Relationship(back_populates="orden")


class ItemOrden(SQLModel, table=True):
    __tablename__ = "item_orden"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_item_orden_cantidad_positiva"),
        CheckConstraint("precio_unitario > 0", name="ck_item_orden_precio_positivo"),
        UniqueConstraint("orden_id", "repuesto_id", name="uq_item_orden_orden_repuesto"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    orden_id: int = Field(foreign_key="orden_trabajo.id", index=True, nullable=False)
    repuesto_id: int = Field(foreign_key="repuesto.id", index=True, nullable=False)
    cantidad: int = Field(nullable=False)
    precio_unitario: Decimal = Field(sa_type=Numeric(10, 2), nullable=False)

    orden: OrdenTrabajo = Relationship(back_populates="items")
    repuesto: "Repuesto" = Relationship(back_populates="items_orden")


class HistorialEstadoOrden(SQLModel, table=True):
    __tablename__ = "historial_estado_orden"

    id: Optional[int] = Field(default=None, primary_key=True)
    orden_id: int = Field(foreign_key="orden_trabajo.id", index=True, nullable=False)
    desde_estado: Optional[str] = Field(
        default=None,
        foreign_key="estado_orden.codigo",
        nullable=True,
    )
    hasta_estado: str = Field(foreign_key="estado_orden.codigo", nullable=False)
    usuario_id: int = Field(foreign_key="usuario.id", nullable=False)
    cuando: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    orden: OrdenTrabajo = Relationship(back_populates="historial_estados")
    usuario: "Usuario" = Relationship()
    desde_estado_rel: Optional[EstadoOrden] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[HistorialEstadoOrden.desde_estado]"},
    )
    hasta_estado_rel: EstadoOrden = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[HistorialEstadoOrden.hasta_estado]"},
    )
