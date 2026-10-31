# Proposal

## Why
El sistema del taller mecánico requiere una capa de persistencia relacional PostgreSQL íntegra y tipada con SQLModel/SQLAlchemy que modele las 13 entidades del dominio, garantice restricciones de integridad de negocio (CHECKs, soft deletes con índices únicos parciales y catálogo de estados) y blinde la auditoría mediante disparadores PL/pgSQL de sólo agregado. La infraestructura de migraciones asincrónicas con Alembic y el script de siembra determinística `seed.py` establecen el estado conocido indispensable para los casos de prueba de cátedra y los módulos de negocio subsiguientes.

## What Changes
- **Modelos de dominio en 4 módulos funcionales:**
  - `app/modules/usuarios/models.py`: `Usuario`, `AsignacionRol`, `IntentoAcceso`, `EventoSeguridad`.
  - `app/modules/clientes/models.py`: `Cliente`, `Vehiculo`.
  - `app/modules/repuestos/models.py`: `Repuesto`, `MovimientoStock`, `HistorialPrecioRepuesto`.
  - `app/modules/ordenes/models.py`: `EstadoOrden` (catálogo con PK código), `OrdenTrabajo`, `ItemOrden`, `HistorialEstadoOrden`.
- **Relaciones declarativas y navegación:** Relaciones bidireccionales explícitas (`relationship`), con relación uno-a-uno `Usuario.cliente` devolviendo un objeto único (`uselist=False`) y no una lista.
- **Restricciones de integridad y tipos precisos:**
  - Fechas con zona horaria (`timestamptz`).
  - Campos monetarios con `Numeric(10, 2)` (precios) y `Numeric(12, 2)` (totales).
  - Restricciones CHECK de base de datos para rangos válidos (año de vehículo entre 1950 y 2100, precios y cantidades estrictamente positivos, stock y totales no negativos, cambio de precio con valores distintos).
- **Índices únicos parciales (`postgresql_where`):**
  - `asignacion_rol`: `UNIQUE (usuario_id, rol) WHERE revocada_en IS NULL`.
  - `vehiculo`: `UNIQUE (patente) WHERE borrado_en IS NULL` (permite registrar un vehículo previamente dado de baja lógica).
  - `repuesto`: `UNIQUE (codigo) WHERE borrado_en IS NULL`.
- **Catálogo de estados de órdenes:** Clave foránea a `estado_orden.codigo` en `orden_trabajo` e `historial_estado_orden` en lugar de CHECK en código (RN-19).
- **Entorno de migraciones Alembic asincrónico:**
  - `alembic.ini` configurado para tomar la URL asincrónica de base de datos desde `Settings` en tiempo de ejecución.
  - Directorio `migrations/` con plantilla asincrónica `async_engine` en `migrations/env.py`.
  - Migración 001: Esquema relacional completo autogenerado y revisado manualmente con comentarios explicativos.
  - Migración 002: Escrita a mano con función PL/pgSQL `prohibir_update_delete()` y 3 triggers BEFORE UPDATE OR DELETE sobre las tablas append-only (`historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto`) (RN-15).
- **Script de siembra determinística (`seed.py`):**
  - Vaciado ordenado de tablas respetando claves foráneas.
  - Carga de los 4 estados del catálogo (`PENDIENTE`, `EN_REPARACION`, `TERMINADA`, `CANCELADA`).
  - Carga de usuarios de prueba con contraseñas hasheadas con bcrypt (ADMIN, RECEPCION, MECANICO, CLIENTE y mecánico nuevo con flag `debe_cambiar_password=True`).
  - Carga de clientes Laura y Jorge, vehículos asociados, catálogo inicial de repuestos con stock y movimientos iniciales, órdenes de prueba e historiales.

## Capabilities

### New Capabilities
- `domain-persistence`: Provee los modelos declarativos de las 13 entidades, el versionado de esquema mediante migraciones asincrónicas Alembic, los disparadores de sólo agregado en PostgreSQL y el script de siembra determinística.

### Modified Capabilities

## Impact
- **Persistencia y Arquitectura:** Establece las tablas y modelos de base de datos sobre los que operarán los Repositorios y Unit of Work en `C-03`.
- **Alembic:** Permite el ciclo de vida de esquema completo (`upgrade head`, `downgrade base`, `upgrade head`).
- **Puesta en marcha:** Habilita el arranque de entornos limpios con `python seed.py` exigido por los casos de prueba de cátedra.
