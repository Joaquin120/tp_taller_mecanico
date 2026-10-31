# Design

## Context
El sistema implementa una arquitectura en 6 capas (`Router -> Service -> Unit of Work -> Repository -> Model`). En las etapas C-01 y C-02 se establecieron la configuración, ciclo de vida, motor asincrónico SQLAlchemy (`expire_on_commit=False`), migraciones Alembic y modelos de dominio SQLModel.
Actualmente falta la infraestructura transversal para que los futuros servicios y módulos interactúen con la persistencia respetando la atomicidad transaccional y el aislamiento de responsabilidades.
Ver `proposal.md` para la motivación y `specs/data-access-contracts/spec.md` para los requerimientos normativos.

## Goals / Non-Goals

**Goals:**
- Implementar `BaseRepository[T]` genérico asincrónico para operaciones CRUD estándar delegando la persistencia a `session.flush()` y prohibiendo llamadas a `commit()`.
- Implementar `SoftDeleteRepository[T]` como especialización que filtra automáticamente entidades marcadas con `borrado_en` y añade el método `soft_delete(id)`.
- Implementar `UnitOfWork` base como context manager asincrónico (`async with uow:`) que confirme la transacción al salir exitosamente y ejecute rollback ante errores, preservando la sesión abierta.
- Implementar esquema genérico `PaginatedResponse[T]` y helper de paginación con validación de límites (1 a 100) y rechazo con HTTP 422 si `page > pages` cuando `total > 0`.
- Establecer `app/core/schemas.py` con `BaseSchema` que configure `model_config = ConfigDict(extra="forbid")`.
- Proveer cobertura de tests unitarios completa para UoW, borrado lógico y paginación.

**Non-Goals:**
- Implementar repositorios de dominio concretos (e.g., `UsuarioRepository`, `OrdenTrabajoRepository`), los cuales pertenecen a sus respectivos módulos en los changes C-04 en adelante.
- Implementar lógica de autenticación, verificación de tokens o seguridad (perteneciente a C-04 y C-05).
- Crear endpoints HTTP de negocio en este change.

## Decisions

### Decisión 1: `flush()` exclusivo en Repositorios (DD-06)
- **Razón:** Para permitir que un caso de uso combine múltiples modificaciones (por ejemplo: descontar repuestos, registrar un movimiento de stock y actualizar el estado de una orden) en una única transacción atómica, los repositorios no deben cerrar la transacción.
- **Alternativas consideradas:**
  - `commit()` dentro de cada método de repositorio: descartado porque fragmenta transacciones complejas y hace imposible el rollback coordinado.
  - Dejar el SQL suelto en los servicios: descartado porque viola el desacoplamiento de capas de Clean Architecture.

### Decisión 2: Unit of Work no cierra ni desecha la sesión en `__aexit__`
- **Razón:** La sesión asincrónica de SQLAlchemy es provista típicamente por el contenedor de dependencias de FastAPI (`Depends(get_session)`) o inyectada por el router con un ciclo de vida propio por petición HTTP. El UoW es responsable de la delimitación transaccional (`commit()` / `rollback()`), no del cierre físico del socket de base de datos.
- **Alternativas consideradas:**
  - Ejecutar `await self.session.close()` en `__aexit__`: descartado porque rompería la reutilización de la sesión por middlewares posteriores o submódulos.

### Decisión 3: Verificación e inspección dinámica en `SoftDeleteRepository`
- **Razón:** Los modelos con soporte de baja lógica (`Vehiculo`, `Repuesto`, etc.) poseen el atributo `borrado_en`. Al inicializar `SoftDeleteRepository(model, session)`, se verifica que `model` declare la columna `borrado_en`. En las consultas de lectura (`get_by_id`, `get_all`, `count`), se añade automáticamente el predicado `model.borrado_en.is_(None)`.
- **Alternativas consideradas:**
  - Requerir que cada query manual incluya la condición `where(borrado_en == None)`: propenso a errores humanos y filtraciones accidentales de registros eliminados.

### Decisión 4: Paginación 1-based con cálculo de `pages` y control de desbordamiento
- **Razón:** La convención estandarizada en la cátedra y especificaciones del sistema requiere:
  - `page >= 1` (default 1).
  - `size` entre 1 y 100 (default 20).
  - Si `total == 0`: `pages = 1` y una petición con `page == 1` devuelve lista vacía `[]`.
  - Si `total > 0`: `pages = ceil(total / size)`. Si `page > pages`, se lanza un error HTTP 422 (`Unprocessable Entity`) indicando que la página solicitada excede el rango disponible.
- **Alternativas consideradas:**
  - Retornar lista vacía silenciosamente cuando `page > pages`: descartado porque la especificación del trabajo práctico exige validación explícita con HTTP 422.

### Decisión 5: Esquema base Pydantic con `extra="forbid"`
- **Razón:** Garantizar que ningún DTO de entrada acepte parámetros no declarados, mitigando ataques de inyección de atributos no deseados (mass assignment).

## Risks / Trade-offs

- **[Riesgo] Excepciones en UoW enmascaradas durante rollback:**
  - *Mitigación:* En `__aexit__`, la captura de excepciones ejecuta `await self.session.rollback()` en un bloque `try...finally` y no suprime la excepción original (`return False`).
- **[Riesgo] Modelo sin `borrado_en` usado con `SoftDeleteRepository`:**
  - *Mitigación:* Se valida la presencia del atributo en `__init__`, lanzando `TypeError` en tiempo de inicialización si se utiliza una entidad incompatible.
- **[Riesgo] Consultas N+1 en `get_all` de repositorios:**
  - *Mitigación:* `BaseRepository.get_all` aceptará cláusulas opcionales de precarga (`*options`), permitiendo a repositorios derivados o llamadas específicas inyectar `selectinload` o `joinedload`.
