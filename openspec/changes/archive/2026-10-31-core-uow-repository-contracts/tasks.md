# Tasks

## 1. Contratos Base Pydantic

- [x] 1.1 Implementar `BaseSchema` en `app/core/schemas.py` con `model_config = ConfigDict(extra="forbid")` y verificar que rechaza atributos adicionales lanzando `ValidationError`.

## 2. Esquema y Envoltorio de Paginación

- [x] 2.1 Implementar `PaginatedResponse[T]` y función helper de paginación en `app/core/paginacion.py` validando `page >= 1`, `size` entre 1 y 100, y lanzando HTTP 422 si `page > pages` con `total > 0`.
- [x] 2.2 Crear tests unitarios en `test/test_paginacion.py` verificando cálculo de páginas, caso borde `total = 0`, y lanzamiento de HTTP 422 ante páginas desbordadas.

## 3. Repositorios Base y Borrado Lógico

- [x] 3.1 Implementar `BaseRepository[T]` genérico en `app/core/repository.py` (`get_by_id`, `get_all`, `count`, `add`, `update`, `delete`) llamando a `session.flush()` y prohibiendo `commit()`.
- [x] 3.2 Implementar `SoftDeleteRepository[T]` en `app/core/repository.py` extendiendo `BaseRepository`, filtrando registros con `borrado_en` y añadiendo método `soft_delete()`.
- [x] 3.3 Crear tests unitarios en `test/test_repository.py` verificando operaciones CRUD, llamadas a `flush()`, exclusión de eliminados lógicos y actualización de `borrado_en`.

## 4. Unit of Work Asincrónico

- [x] 4.1 Implementar `UnitOfWork` en `app/core/unit_of_work.py` como gestor de contexto asincrónico (`__aenter__` / `__aexit__`) confirmando en salida limpia y ejecutando rollback ante excepción sin cerrar la sesión.
- [x] 4.2 Crear tests unitarios en `test/test_unit_of_work.py` verificando confirmación automática en éxito y reversión (rollback) automática ante excepciones.

## 5. Verificación de Integración

- [x] 5.1 Ejecutar la suite completa de tests de la infraestructura core (`test_health.py`, `test_persistence.py`, `test_paginacion.py`, `test_repository.py`, `test_unit_of_work.py`) y comprobar que todo finalice en verde.

## Workflow follow-up

- Ejecutar `/opsx:apply` para iniciar la implementación de tareas bajo Strict TDD.
- Ejecutar `/opsx:verify` para validar el paso de todas las pruebas.
- Ejecutar `/opsx:archive core-uow-repository-contracts` para sincronizar las especificaciones y marcar `[x]` en `CHANGES.md`.
