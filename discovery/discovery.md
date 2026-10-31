# Discovery — Taller Mecánico API

**Fecha:** 2026-10-30  
**Fuente principal:** Especificación académica `trabajo_pr_ctico_1_a_6.md` (UTN Programación III)  
**Modalidad:** Opción A — Proyecto académico autocontenido y determinístico.

---

## 1. Problema que resuelve
Falta de trazabilidad y descontrol transaccional en talleres mecánicos (asociación cliente-vehículo, órdenes de trabajo que consumen repuestos sin descuento automático de stock y falta de control de accesos por rol).

---

## 2. Usuarios y Roles
- **Administrador (`ADMIN`):** Gestión integral de personal, roles vigentes, reposición de stock, precios y auditoría.
- **Recepción (`RECEPCION`):** Alta de clientes, vehículos y apertura de órdenes de trabajo.
- **Mecánico (`MECANICO`):** Auto-asignación de órdenes en reparación y finalización con descuento automático de inventario.
- **Cliente (`CLIENTE`):** Consulta exclusiva de vehículos y órdenes propias; cancelación de sus órdenes pendientes.
- **SISTEMA:** Identidad de auditoría para operaciones de inicialización (`seed.py`).

---

## 3. Casos de Uso Principales
1. **Auto-registro web:** Alta atómica de usuario, rol `CLIENTE` y ficha `cliente` en un único Unit of Work.
2. **Apertura de orden:** Recepción ingresa vehículo, falla e ítems; el servidor calcula precios y total.
3. **Reparación y terminación:** El mecánico asignado termina la orden; descuento atómico de stock, movimientos de inventario e historial en una sola transacción.
4. **Seguridad y autenticación:** Login con protección contra timing attacks (hash ficticio), rate limiting (5 fallos en 60s) y cookie `HttpOnly`.

---

## 4. Competidores y Soluciones Existentes
- **Planillas manuales / Excel:** Informales, sin integridad referencial ni control de concurrencia.
- **SaaS comerciales (TallerPro, DeTaller):** Complejos y con módulos fuera de alcance (facturación fiscal, pagos online). El presente proyecto es una API liviana, estricta y orientada al cumplimiento riguroso de la especificación técnica de cátedra.

---

## 5. Funcionalidades Necesarias (MVP)
- Arquitectura en 6 capas: `Router -> Service -> Unit of Work -> Repository -> Model`.
- Persistencia en PostgreSQL 16 con migraciones Alembic (incluyendo triggers de solo-agregado).
- Autenticación segura con bcrypt fuera del event loop y cookie `HttpOnly`.
- Control de cambio obligatorio de contraseña e invalidación instantánea de sesiones previas.
- Catálogo de estados de orden con repositorio de solo lectura.

---

## 6. Funcionalidades Opcionales / Fuera de Alcance
- Concurrencia pesimista/optimista (actualización perdida permitida según capítulo 7).
- Colas de tareas distribuidas con Redis / Celery (simulado con `BackgroundTasks` en memoria para capítulo 8).
- Edición manual de stock vía `PATCH` (prohibida expresamente por diseño).

---

## 7. Reglas de Negocio Críticas
- Cumplimiento estricto de las reglas **RN-01 a RN-20** (índices únicos parciales, autoprotección del admin, solo-agregado, rate limit y cálculo exclusivo de montos en servidor).

---

## 8. Integraciones
- PostgreSQL 16 vía controlador asincrónico `asyncpg`. Sin integraciones externas de terceros.

---

## 9. Restricciones Técnicas
- Python 3.12, FastAPI 0.111, SQLModel 0.0.24, SQLAlchemy 2.0 async, Alembic 1.13.
- Nombres inmutables de tablas y columnas. DTOs con `extra="forbid"`. Aprobación de los 19 casos de prueba mínimos (C-01 a C-19).

---

## 10. Riesgos
- Actualización perdida de stock en terminación simultánea (asumido por la cátedra).
- Pérdida de aviso simulado si el proceso cae antes de completarse el background task.

---

## 11. Preguntas Abiertas
- Variables de entorno locales configuradas en `.env` a partir de `env.example`.
