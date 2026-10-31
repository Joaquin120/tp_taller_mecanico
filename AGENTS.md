# Instrucciones del Proyecto — Taller Mecánico API

> Constitución operativa del repositorio para agentes de IA y desarrolladores.
> Este documento rige las convenciones, arquitectura, mapa de navegación y reglas duras del proyecto.

---

## 1. Resumen Ejecutivo y Propósito
API RESTful asincrónica en 6 capas para la gestión integral de un taller mecánico (clientes, vehículos, órdenes de trabajo, control de inventario de repuestos y autenticación/autorización RBAC dinámica). 
El proyecto garantiza integridad transaccional mediante Unit of Work, persistencia versionada con Alembic (incluyendo triggers PL/pgSQL de sólo agregado) y seguridad sin exponer secretos ni información interna de PostgreSQL.

---

## 2. Stack Tecnológico

| Componente | Versión | Uso en el Proyecto |
| :--- | :--- | :--- |
| **Python** | 3.12+ | Lenguaje base con tipado estricto (`type hints`) |
| **FastAPI** | 0.111+ | Framework web asincrónico (todos los handlers `async def`) |
| **SQLModel** | 0.0.24+ | Modelos declarativos compatibles con SQLAlchemy y Pydantic |
| **SQLAlchemy** | 2.0+ (async) | Motor asincrónico, `async_sessionmaker`, precarga (`selectinload`) |
| **asyncpg** | 0.30+ | Controlador asincrónico de PostgreSQL (`postgresql+asyncpg://...`) |
| **PostgreSQL** | 16+ | Base de datos relacional |
| **Alembic** | 1.13+ | Migraciones de base de datos con plantilla asincrónica |
| **pydantic-settings** | 2.0+ | Configuración tipada y `@computed_field` desde entorno / `.env` |
| **bcrypt** | 4.0+ | Hash de contraseñas fuera del event loop bajo semáforo concurrente |
| **PyJWT** | 2.8+ | Emisión y verificación de tokens en cookie `HttpOnly` |
| **uvicorn** | [standard] | Servidor ASGI |

---

## 3. Mapa de Navegación de la Knowledge Base

Antes de implementar o modificar código, consultar la fuente canónica de verdad en [`knowledge-base/`](knowledge-base/):

| Documento | Cuándo Consultarlo |
| :--- | :--- |
| [01_vision_y_objetivos.md](knowledge-base/01_vision_y_objetivos.md) | Alcance del proyecto, qué queda afuera (concurrencia y colas) y criterios de aprobación. |
| [02_descripcion_general.md](knowledge-base/02_descripcion_general.md) | Arquitectura en 6 capas, routers Abierto vs Protegido y lista de endpoints. |
| [03_actores_y_roles.md](knowledge-base/03_actores_y_roles.md) | Roles (`ADMIN`, `RECEPCION`, `MECANICO`, `CLIENTE`), matriz RBAC y autoprotección admin. |
| [04_modelo_de_datos.md](knowledge-base/04_modelo_de_datos.md) | Esquema de 13 tablas, restricciones CHECK, índices únicos parciales y datos de `seed.py`. |
| [05_reglas_de_negocio.md](knowledge-base/05_reglas_de_negocio.md) | Reglas codificadas **RN-01 a RN-20** con garantes y códigos HTTP. |
| [06_funcionalidades.md](knowledge-base/06_funcionalidades.md) | Historias de usuario (US-001 a US-013) y criterios de aceptación por épica. |
| [07_flujos_principales.md](knowledge-base/07_flujos_principales.md) | Diagramas de secuencia: login anti-timing, auto-registro atómico, inicio y fin de órdenes. |
| [08_arquitectura_propuesta.md](knowledge-base/08_arquitectura_propuesta.md) | Estructura de carpetas, Unit of Work, variables de entorno y triggers de sólo agregado. |
| [09_decisiones_y_supuestos.md](knowledge-base/09_decisiones_y_supuestos.md) | Decisiones de diseño (DD-01 a DD-06) y trade-offs aceptados. |
| [10_preguntas_abiertas.md](knowledge-base/10_preguntas_abiertas.md) | Resoluciones técnicas operativas. |

---

## 4. Skills Disponibles por Rol

Las skills registradas en [`.atl/skill-registry.md`](.atl/skill-registry.md) aplican según la tarea:

* **Arquitectura y Core:** `clean-architecture` (desacoplamiento de capas) y `domain-driven-design` (reglas e invariantes).
* **Backend y Persistencia:** `fastapi` (handlers, dependencias, lifespan) y `sqlalchemy-alembic-expert` (consultas sin N+1, migraciones).
* **Testing y Calidad:** `python-testing-patterns` (casos de prueba asincrónicos y validación de endpoints).

---

## 5. Roadmap de Implementación (OpenSpec)

El avance de los changes atómicos se gestiona en [`CHANGES.md`](CHANGES.md):
- **Camino crítico:** `C-01 → C-02 → C-03 → C-04 → C-05 → C-06 → C-08 → C-09`.
- **Primer change a implementar:** `C-01 foundation-config-lifespan`.
- **Flujo de change:**
  1. `/opsx:propose <nombre-change>`
  2. `/opsx:apply`
  3. `/opsx:verify`
  4. `/opsx:archive <nombre-change>` y marcar `[x]` en `CHANGES.md`.

---

## 6. Reglas Duras del Proyecto (Innegociables)

1. **`async-handlers-only`:** Todos los endpoints y operaciones I/O deben usar `async def`. Ninguna llamada bloqueante debe ejecutarse en el event loop.
2. **`clean-architecture-layers`:** Flujo unidireccional estricto: `Router -> Service -> Unit of Work -> Repository -> Model`. Los routers jamás ejecutan SQL ni contienen lógica de negocio.
3. **`no-commit-in-repositories`:** Los repositorios llaman exclusivamente a `session.flush()`. El `commit()` es responsabilidad exclusiva del gestor de contexto asincrónico `UnitOfWork`.
4. **`strict-pydantic-contracts`:** Todos los DTOs de entrada declaran `model_config = ConfigDict(extra="forbid")`. Las respuestas jamás deben exponer `password_hash` ni trazas internas de la base de datos.
5. **`off-loop-bcrypt`:** Todo cálculo o verificación de hash con bcrypt debe ejecutarse en `asyncio.to_thread` acotado por `asyncio.Semaphore(MAX_CONCURRENT_BCRYPT)`. Longitud máxima de password en contrato: 72 bytes.
6. **`database-rbac-enforcement`:** La autorización se valida en cada petición consultando los roles vigentes en `asignacion_rol` en la base de datos. Los roles del token JWT son meramente informativos.
7. **`append-only-tables`:** Las tablas `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` son de sólo agregado, blindadas mediante triggers PL/pgSQL instalados en la 2da migración.
8. **`no-secrets-in-repo`:** Prohibido hardcodear contraseñas o claves de firma en el código o en `alembic.ini`. Si faltan en las variables de entorno, la aplicación no debe arrancar.

---

## 7. Convenciones de Código y Commits

- **Nomenclatura:** `snake_case` para variables, funciones, tablas y columnas de base de datos; `PascalCase` para clases y modelos.
- **Formato de Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
- **Control de Cambios:** Ningún change se da por completado sin haber superado sus pruebas de integración y los casos de prueba de cátedra correspondientes.
