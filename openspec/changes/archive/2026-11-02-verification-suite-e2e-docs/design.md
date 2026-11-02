# Design

## Context

Todos los módulos del backend (C-01 a C-08) se encuentran implementados con arquitectura en 6 capas, Unit of Work y repositorios. La consigna del trabajo práctico (`trabajo_pr_ctico_1_a_6.md`) exige como criterio de evaluación y entrega la suite de casos de prueba mínimos C-01 a C-19 dividida en archivos `.http`, un script `solo_agregado.sql`, la verificación del recuento de consultas SQL sin N+1 (C-15), la plantilla `env.example` y el manual operativo `README.md`.

## Goals / Non-Goals

**Goals:**
- Implementar la suite completa de archivos `.http` en `test/` documentando para cada caso la petición, los encabezados y la respuesta esperada en comentarios:
  - `test/auth.http`: Casos C-01 a C-09.
  - `test/ordenes.http`: Casos C-10 a C-13.
  - `test/repuestos_vehiculos.http`: Casos C-16 a C-19.
- Implementar manejo multi-sesión con la extensión "REST Client" de VS Code mediante directivas `# @name`, `# @no-cookie-jar` y reenvío dinámico de cabeceras `Cookie: {{login...response.headers.Set-Cookie}}`.
- Completar `test/solo_agregado.sql` para el caso C-14 con los 6 intentos de modificación/borrado en tablas de sólo agregado y el rechazo por clave foránea de catálogo.
- Implementar verificación automatizada y reproducible de C-15 mediante un test con SQLAlchemy listener (`before_cursor_execute`) que certifique idéntica cantidad de consultas en órdenes con 2 y con 4 ítems.
- Proveer `env.example` completo sin secretos sensibles y con guía de generación de `JWT_SECRET_KEY`.
- Elaborar `README.md` exhaustivo con la guía paso a paso para levantar el sistema en un entorno limpio.

**Non-Goals:**
- No se modifican modelos, contratos Pydantic ni lógica de negocio de los módulos previos.
- No se introducen dependencias externas adicionales a las ya presentes en `requirements.txt`.

## Decisions

### D-01: Modularización de los archivos `.http` y manejo de multi-sesión
- **Decisión:** Agrupar los casos en 3 archivos temáticos (`auth.http`, `ordenes.http`, `repuestos_vehiculos.http`), declarando al inicio de cada archivo bloques de login para cada actor (`admin`, `recepcion`, `mecanico`, `cliente`) utilizando `# @name <actorLogin>` y etiquetando cada petición subsecuente con `# @no-cookie-jar` y `Cookie: {{<actorLogin>.response.headers.Set-Cookie}}`.
- **Alternativas:** Un único archivo monolítico `suite.http`. Se descarta porque dificulta la lectura y no aísla las fases de evaluación de la cátedra.
- **Justificación:** Cumple con la directiva explícita de la consigna ("VARIAS SESIONES A LA VEZ") y permite correr peticiones intercaladas entre administrador y recepción sin interferencia de cookies globales.

### D-02: Verificación formal y reproducible de C-15 (Cero N+1)
- **Decisión:** Implementar un test automatizado en `test/test_c15_n_plus_one.py` que utilice SQLite en memoria instrumentado con `sqlalchemy.event.listen(engine.sync_engine, "before_cursor_execute", ...)` para contar exactamente las sentencias emitidas en `OrdenService.obtener_orden` para 2 ítems y para 4 ítems, comprobando que `count_2 == count_4`.
- **Alternativas:** Confiar únicamente en una captura de pantalla visual o inspección manual de terminal con `SQL_ECHO=true`.
- **Justificación:** Otorga garantía matemática en la suite de pytest (CI y local) de que no hay consultas N+1 en el detalle de órdenes, además de facilitar la extracción de la evidencia textual para la entrega.

### D-03: Completitud de `test/solo_agregado.sql` (C-14)
- **Decisión:** Estructurar el script SQL con comentarios claros y sentencias individuales para ejecución interactiva o por lotes en `psql`:
  - 1 a 6: `UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto`.
  - 7: `INSERT INTO orden_trabajo (..., estado, ...) VALUES (..., 'ESTADO_INEXISTENTE', ...)` que falla por `fk_orden_trabajo_estado`.
- **Justificación:** Cubre exactamente los 7 rechazos exigidos por el caso C-14 de la cátedra.

### D-04: Estructura del `README.md`
- **Decisión:** Organizar el `README.md` siguiendo el flujo estándar de evaluación:
  1. Requisitos previos (Python 3.12+, PostgreSQL 16+).
  2. Creación del entorno virtual y activación.
  3. Instalación de dependencias (`pip install -r requirements.txt`).
  4. Configuración de entorno (`cp env.example .env` y generación de `JWT_SECRET_KEY`).
  5. Migración de base de datos (`alembic upgrade head`).
  6. Siembra de datos iniciales (`python seed.py`).
  7. Ejecución de la aplicación con Uvicorn (`uvicorn main:app --reload`).
  8. Ejecución de pruebas (`pytest -q`, archivos `.http` y `solo_agregado.sql`).
  9. Evidencia de consultas C-15 y rechazos C-14.

## Risks / Trade-offs

- **[Riesgo: Expiración de cookie durante la ejecución manual de pruebas .http]** → Mitigación: Configurar en `env.example` un valor por defecto de `JWT_EXPIRATION_SECONDS=1800` (30 minutos), suficiente para completar las pruebas de forma interactiva sin tener que re-loguearse en cada paso.
- **[Riesgo: Divergencia entre SQLite en pytest y PostgreSQL en C-14]** → Mitigación: La lógica del disparador ya está empaquetada en la migración `002_triggers_solo_agregado.py` y `004_ordenes_triggers_y_fk.py` para PostgreSQL; `solo_agregado.sql` documenta los comandos psql nativos y el test UoW previene mutaciones en capa Python.
