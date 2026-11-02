# Design: clientes-vehiculos-module

## Context
El proyecto cuenta con las entidades `Cliente` y `Vehiculo` en `app/modules/clientes/models.py`, así como sus respectivos repositorios (`ClienteRepository`, `VehiculoRepository`) y el gestor transaccional `ClientesUnitOfWork` en `app/modules/clientes/unit_of_work.py`.
Este diseño define la capa de contratos (schemas), la lógica de negocio en servicios (`ClienteService`, `VehiculoService`), y la exposición en controladores web protegidos (`router.py`) cumpliendo la arquitectura en 6 capas y las reglas RN-01, RN-16 y RN-17.

## Goals / Non-Goals

**Goals:**
- Definir contratos Pydantic con `model_config = ConfigDict(extra="forbid")`, normalización de patentes y validación de año (1950..2100).
- Implementar `ClienteService` para altas con validación de documento único y consulta con precarga de flota vigente.
- Implementar `VehiculoService` para alta con validación de patente activa única, baja lógica condicionada a la inexistencia de órdenes de trabajo con `es_final=False` (RN-16), y consulta de vehículos del cliente autenticado (RN-17).
- Exponer los endpoints bajo autorización RBAC estricta (`requiere_rol(["ADMIN", "RECEPCION"])` para personal, `requiere_rol(["CLIENTE"])` para mis vehículos).
- Inyectar `ClientesUnitOfWork` desde los handlers y asegurar que los servicios encapsulan la transacción dentro de un único bloque `async with uow:`.

**Non-Goals:**
- Modificar la estructura base de los repositorios o tablas de la base de datos (ya fijadas en C-02 y Ejercicio 6).
- Implementar la lógica de creación o transición de órdenes de trabajo (alcance de C-08).

## Decisions

### Decisión 1: Contratos DTO con normalización y restricción de campos extras
Los esquemas de entrada `ClienteCreateRequest` y `VehiculoCreateRequest` declaran `model_config = ConfigDict(extra="forbid")`. Para patentes, se normaliza eliminando espacios y convirtiendo a mayúsculas mediante un validator `@field_validator("patente")`. Para el año, se valida `ge=1950, le=2100`.

*Alternativas descartadas:* Permitir cualquier cadena en patente sin normalizar (podría generar duplicados con variaciones de mayúsculas/minúsculas).

### Decisión 2: Reutilización de `ClientesUnitOfWork`
El módulo ya dispone de `ClientesUnitOfWork` que agrupa `ClienteRepository`, `VehiculoRepository` y `OrdenTrabajoRepository`. Toda la verificación y mutación se ejecuta sobre la misma sesión compartida sin llamadas a `commit()` en los repositorios.

*Alternativas descartadas:* Crear repositorios independientes por llamada o inyectar sesiones SQLAlchemy directamente en los servicios.

### Decisión 3: Verificación de órdenes abiertas para baja lógica (RN-16)
Antes de llamar a `soft_delete(vehiculo)`, `VehiculoService` consulta las órdenes asociadas al vehículo a través de `uow.ordenes.get_por_vehiculo(vehiculo_id)` o precargando `vehiculo.ordenes`. Si alguna orden tiene un estado con `es_final == False`, se detiene la operación y se lanza `HTTPException(status_code=409, detail="No se puede dar de baja un vehículo con órdenes de trabajo abiertas")`.

*Alternativas descartadas:* Permitir la baja y dejar órdenes huérfanas en estado activo, o eliminar las órdenes en cascada.

### Decisión 4: Aislamiento estricto de vehículos por cliente (RN-17)
En `GET /mis-vehiculos`, el servicio recibe el `usuario_id` del usuario autenticado obtenido de la base de datos (vía `UsuarioActual`), localiza el registro `Cliente` correspondiente (`uow.clientes.get_by_usuario_id(usuario_id)`), y lista sus vehículos con `uow.vehiculos.listar_por_cliente(cliente.id)`. Si el usuario no tiene cliente asociado, retorna lista vacía.

*Alternativas descartadas:* Permitir pasar el `cliente_id` como parámetro de consulta (vulnerabilidad IDOR).

## Risks / Trade-offs

- **[Riesgo: Condición de carrera al dar de baja un vehículo mientras se abre una orden]** → Mitigación: Toda la consulta y la mutación de `borrado_en` se realizan dentro del bloque transaccional del Unit of Work.
- **[Riesgo: Reutilización de patentes dadas de baja en SQLite]** → Mitigación: SQLite no soporta índices únicos parciales `WHERE borrado_en IS NULL`, por lo que `test/infra_sqlite.py` descarta `uq_vehiculo_patente_activa` en las pruebas locales, manteniéndose activo en PostgreSQL.
