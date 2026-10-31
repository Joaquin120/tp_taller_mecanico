# Design

## Context
Tras completar la base de configuración y ciclo de vida en `C-01`, el sistema requiere la persistencia de las 13 entidades del taller mecánico. La persistencia debe cumplir con el patrón de arquitectura en 6 capas, manteniendo los modelos dentro de sus respectivos módulos (`usuarios`, `clientes`, `repuestos`, `ordenes`), asegurando integridad referencial, índices parciales para bajas lógicas y disparadores PL/pgSQL de sólo agregado.

## Goals / Non-Goals

**Goals:**
- Definir las 13 entidades del dominio usando `SQLModel(table=True)` con `__tablename__`, restricciones CHECK, claves foráneas e índices únicos parciales (`postgresql_where`).
- Establecer relaciones bidireccionales con tipado estricto y navegación explícita (`uselist=False` para `Usuario.cliente`).
- Configurar el entorno asincrónico de Alembic integrando `Settings.database_url` en `migrations/env.py`.
- Generar la migración inicial 001 con el esquema completo y la migración manual 002 con los disparadores PL/pgSQL de sólo agregado.
- Implementar `seed.py` asincrónico que vacíe mediante `TRUNCATE ... CASCADE` y cargue los datos de prueba canónicos requeridos por la cátedra.

**Non-Goals:**
- Repositorios, Unit of Work y lógica de servicios (corresponden a `C-03`).
- Controladores y routers de negocio (corresponden a `C-04` en adelante).

## Decisions

### 1. Modelos SQLModel distribuidos por módulo con `__table_args__` explícitos
- **Decisión:** Declarar cada modelo heredando de `SQLModel, table=True` en su módulo funcional:
  - `app/modules/usuarios/models.py`: `Usuario`, `AsignacionRol`, `IntentoAcceso`, `EventoSeguridad`.
  - `app/modules/clientes/models.py`: `Cliente`, `Vehiculo`.
  - `app/modules/repuestos/models.py`: `Repuesto`, `MovimientoStock`, `HistorialPrecioRepuesto`.
  - `app/modules/ordenes/models.py`: `EstadoOrden`, `OrdenTrabajo`, `ItemOrden`, `HistorialEstadoOrden`.
- **Razón:** Agrupa la cohesión por dominio y permite que Alembic descubra los metadatos importándolos en `env.py`.
- **Alternativas:** Usar SQLAlchemy puro `DeclarativeBase`. Se eligió `SQLModel` porque la cátedra lo define en el stack tecnológico oficial y unifica validación con Pydantic.

### 2. Catálogo de estados de órdenes con clave primaria textual
- **Decisión:** `EstadoOrden` utiliza `codigo: str` como clave primaria (ej: `"PENDIENTE"`), y tanto `orden_trabajo.estado` como `historial_estado_orden.hasta_estado` son claves foráneas directas.
- **Razón:** Cumple con la regla RN-19. Permite lectura legible sin necesidad de joins tanto en SQL puro (`psql`) como en la API, y almacena metadatos como `es_final` y `posicion`.
- **Alternativas:** Un enum de PostgreSQL o restricción CHECK. Descartado por el enunciado (sección 1.4 y 1.9).

### 3. Índices únicos parciales (`postgresql_where`) para soft-delete y roles
- **Decisión:** Declarar índices únicos parciales en `__table_args__`:
  - `Index("uq_vehiculo_patente_activa", "patente", unique=True, postgresql_where=text("borrado_en IS NULL"))`
  - `Index("uq_repuesto_codigo_activo", "codigo", unique=True, postgresql_where=text("borrado_en IS NULL"))`
  - `Index("uq_asignacion_rol_activa", "usuario_id", "rol", unique=True, postgresql_where=text("revocada_en IS NULL"))`
- **Razón:** Permite que un vehículo o repuesto dado de baja pueda volver a ser registrado a futuro sin violar unicidad sobre filas activas.

### 4. Estrategia de migraciones en dos fases (001 autogenerada, 002 manual)
- **Decisión:**
  - Migración 001: Autogenerada con Alembic leyendo `SQLModel.metadata`.
  - Migración 002: Escrita a mano con `op.execute(...)` para la función `prohibir_update_delete()` y los 3 triggers `BEFORE UPDATE OR DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto`.
- **Razón:** Alembic autogenerate no detecta funciones ni triggers de PostgreSQL. Separar la migración 002 permite versionar y revertir (`downgrade`) los disparadores de forma aislada.

### 5. Vaciado en `seed.py` mediante `TRUNCATE ... CASCADE`
- **Decisión:** `seed.py` ejecutará `TRUNCATE TABLE <tablas> RESTART IDENTITY CASCADE`.
- **Razón:** Los disparadores de sólo agregado rechazan `DELETE` fila por fila (`FOR EACH ROW`). En PostgreSQL, `TRUNCATE` no activa disparadores `FOR EACH ROW` de borrado, permitiendo limpiar la base de datos de manera limpia, rápida y respetando el diseño append-only.

## Risks / Trade-offs

- **[Riesgo]** Importaciones circulares entre módulos en la definición de relaciones de SQLAlchemy.  
  → **Mitigación:** Usar cadenas de texto en los parámetros `relationship("Cliente", back_populates="usuario")` y centralizar la importación de todos los modelos en `migrations/env.py` y `app/core/database.py`.
- **[Riesgo]** Disparador de sólo agregado impidiendo el reseteo de pruebas locales.  
  → **Mitigación:** Uso exclusivo de `TRUNCATE CASCADE` en el comando de siembra `seed.py`.
- **[Riesgo]** Incompatibilidad entre tipos `Numeric` y floats en operaciones aritméticas.  
  → **Mitigación:** Declarar `sa_type=Numeric(10, 2)` con `Decimal` de Python para garantizar precisión bancaria.

## Migration Plan
1. Configurar `alembic.ini` y `migrations/env.py` para usar el motor asincrónico y `Settings.database_url`.
2. Generar migración 001: `alembic revision --autogenerate -m "001_initial_schema"`.
3. Crear migración 002 manual: `alembic revision -m "002_triggers_solo_agregado"` e incorporar el script PL/pgSQL.
4. Validar ciclo de vida: `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head`.
5. Ejecutar y validar `python seed.py`.
