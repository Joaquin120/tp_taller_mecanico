# Proposal

## Why
El proyecto requiere desacoplar el acceso a datos y la lógica de negocio siguiendo una arquitectura estricta en 6 capas (`Router -> Service -> Unit of Work -> Repository -> Model`). Para permitir la composición de operaciones atómicas sobre múltiples entidades (como el consumo de repuestos, registro de movimientos y transiciones de estado) sin acoplar los servicios a detalles de persistencia SQL, se necesita una infraestructura transversal de Unit of Work asincrónico, repositorios base reutilizables que cumplan la regla estricta de no hacer `commit()`, paginación estandarizada y contratos Pydantic con validación estricta (`extra="forbid"`).

## What Changes
- **Nuevo Repositorio Base Genérico (`app/core/repository.py`)**:
  - `BaseRepository[T]`: Métodos genéricos asincrónicos (`get_by_id`, `get_all`, `count`, `add`, `update`, `delete`). Ejecuta exclusivamente `session.flush()` y prohíbe `commit()`.
  - `SoftDeleteRepository[T]`: Extensión que filtra automáticamente registros con `borrado_en` no nulo en lecturas/conteos y añade método `soft_delete()` que establece el timestamp en lugar de remover la fila físicamente.
- **Nuevo Gestor de Transacciones Unit of Work (`app/core/unit_of_work.py`)**:
  - `UnitOfWork` base como gestor de contexto asincrónico (`async with uow:`).
  - Confirma (`session.commit()`) automáticamente en salida limpia y ejecuta rollback (`session.rollback()`) ante cualquier excepción no manejada, sin cerrar la sesión de base de datos gestionada por el ciclo de vida o dependencia.
- **Nuevo Esquema y Envoltorio de Paginación (`app/core/paginacion.py`)**:
  - DTO genérico `PaginatedResponse[T]` con atributos `{items, total, page, size, pages}`.
  - Parámetros `page >= 1`, `size` entre 1 y 100 (por defecto 20).
  - Función de ayuda para calcular metadatos de paginación y validación con HTTP 422 cuando la página solicitada excede la última página calculable (cuando `total > 0`).
- **Contratos Base Pydantic Estrictos (`app/core/schemas.py`)**:
  - Esquema base con `model_config = ConfigDict(extra="forbid")` para que todos los DTOs de entrada rechacen campos adicionales.
- **Suite de Pruebas Unitarias (`test/test_core_uow.py` y `test/test_paginacion.py`)**:
  - Verificación de confirmación y rollback automático ante excepciones en UoW.
  - Verificación de filtrado y borrado lógico en `SoftDeleteRepository`.
  - Verificación de metadatos de paginación y límites de página.

## Capabilities

### New Capabilities
- `data-access-contracts`: Define los contratos transversales de persistencia asincrónica, Unit of Work transaccional atómico, repositorios base con borrado lógico y envoltorio estandarizado de paginación.

### Modified Capabilities
*(Ninguna - no se modifican requerimientos de capacidades existentes)*

## Impact
- **Código del proyecto**: Añade `app/core/repository.py`, `app/core/unit_of_work.py`, `app/core/paginacion.py` y `app/core/schemas.py`.
- **APIs y Módulos futuros**: Desbloquea la implementación de repositorios concretos y servicios en `C-04 auth-security-session`, `C-05 authorization-rbac-protection`, `C-06 clientes-vehiculos-module`, etc.
- **Dependencias**: Utiliza las ya existentes en `requirements.txt` (`sqlalchemy`, `sqlmodel`, `fastapi`, `pydantic`).
