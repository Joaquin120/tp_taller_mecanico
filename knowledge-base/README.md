# Taller Mecánico — Base de Conocimiento (Knowledge Base)

Base de conocimiento canónica generada para el Trabajo Práctico Integrador (Unidades 1 a 6) de Programación III (UTN - Tecnicatura Universitaria en Programación).

## Índice Canónico de Archivos

| Archivo | Contenido |
| :--- | :--- |
| [01_vision_y_objetivos.md](01_vision_y_objetivos.md) | Propósito del sistema, objetivos por actor, alcance v1.0, exclusiones y criterios de éxito. |
| [02_descripcion_general.md](02_descripcion_general.md) | Stack técnico (FastAPI, SQLModel, PostgreSQL, Alembic), arquitectura en capas y catálogo de endpoints. |
| [03_actores_y_roles.md](03_actores_y_roles.md) | Actores, roles dinámicos vigentes en BD, matriz RBAC de permisos y autoprotección de administradores. |
| [04_modelo_de_datos.md](04_modelo_de_datos.md) | Dominios, ERD, 13 tablas, claves foráneas, índices únicos parciales, restricciones y datos de `seed.py`. |
| [05_reglas_de_negocio.md](05_reglas_de_negocio.md) | Tabla completa de reglas de negocio codificadas de **RN-01 a RN-20** con garantes y códigos HTTP. |
| [06_funcionalidades.md](06_funcionalidades.md) | Historias de usuario y criterios de aceptación por épica (Salud, Auth, Clientes, Repuestos, Órdenes). |
| [07_flujos_principales.md](07_flujos_principales.md) | Flujos extremo a extremo: Login con timing defense, registro atómico, apertura y terminación de órdenes. |
| [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md) | Estructura de carpetas obligatoria, patrones UoW/Repositorio, variables de entorno y migración de triggers. |
| [09_decisiones_y_supuestos.md](09_decisiones_y_supuestos.md) | Decisiones arquitectónicas justificadas (DD-01 a DD-06) y supuestos del entorno de evaluación. |
| [10_preguntas_abiertas.md](10_preguntas_abiertas.md) | Resoluciones de inconsistencias y notas operativas. |

## Quick Start para Desarrolladores y Agentes

1. **Entender el Dominio y Reglas:** Leer [01_vision_y_objetivos.md](01_vision_y_objetivos.md), [03_actores_y_roles.md](03_actores_y_roles.md) y [05_reglas_de_negocio.md](05_reglas_de_negocio.md).
2. **Entender la Estructura y Capas:** Leer [02_descripcion_general.md](02_descripcion_general.md) y [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md).
3. **Entender la Persistencia:** Leer [04_modelo_de_datos.md](04_modelo_de_datos.md) y [07_flujos_principales.md](07_flujos_principales.md).
4. **Implementación de Changes:** Consultar el backlog en `CHANGES.md`.
