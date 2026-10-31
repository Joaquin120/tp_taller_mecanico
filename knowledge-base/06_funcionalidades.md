# Funcionalidades

## Épica 1: Monitoreo y Ciclo de Vida
### US-001 — Monitoreo de Liveness y Readiness
**Como** operador del sistema / balanceador de carga  
**Quiero** consultar los endpoints `/health/live` y `/health/ready`  
**Para** saber si el proceso está activo y si la base de datos PostgreSQL responde correctamente.  
**Criterios de aceptación:**
- `/health/live` responde HTTP 200 inmediatamente sin tocar la base de datos.
- `/health/ready` ejecuta `SELECT 1` en la sesión asincrónica de base de datos; si responde da HTTP 200, si la base está caída devuelve HTTP 503.

---

## Épica 2: Autenticación, Sesiones y Seguridad
### US-002 — Auto-registro de Clientes
**Como** cliente nuevo del taller  
**Quiero** registrarme en la plataforma ingresando mi email, contraseña, nombre, documento y teléfono  
**Para** poder gestionar mis vehículos y consultar órdenes de trabajo.  
**Criterios de aceptación:**
- En una sola transacción Unit of Work se crean el `usuario`, la `asignacion_rol` (con rol `CLIENTE`) y la ficha `cliente`.
- Si el documento o email ya existen, rechaza con HTTP 409 y no deja filas sueltas (RN-02).
- Responde HTTP 201.

### US-003 — Inicio de Sesión Seguro (Rate-Limit y Cookie HttpOnly)
**Como** usuario del sistema  
**Quiero** iniciar sesión con mis credenciales  
**Para** obtener acceso a las funciones autorizadas según mi rol.  
**Criterios de aceptación:**
- Cuenta intentos fallidos por `(email, ip)` en los últimos 60 segundos sobre `intento_acceso`. Al 6to fallo consecutivo responde HTTP 429 con cabecera `Retry-After` sin calcular hash (RN-08).
- Verificación de contraseña mediante bcrypt fuera del loop con semáforo. Si el usuario no existe, verifica contra hash ficticio para evitar timing attacks (RN-09).
- Emite token JWT en cookie `access_token` con atributos `HttpOnly`, `SameSite=Lax`, `Max-Age` y `Secure` configurable (RN-03/04). El body no contiene el token.
- Cada intento se registra en `intento_acceso` en transacción independiente confirmada.

### US-004 — Cierre de Sesión y Consulta de Identidad
**Como** usuario autenticado  
**Quiero** cerrar sesión o consultar mis datos con `GET /auth/yo`  
**Para** verificar mis roles vigentes o destruir la cookie de sesión.  
**Criterios de aceptación:**
- `/auth/logout` limpia la cookie `access_token` con Max-Age=0.
- `GET /auth/yo` devuelve el usuario, los roles vigentes en la base y los que informaba el token.

### US-005 — Cambio Obligatorio de Contraseña
**Como** usuario con contraseña provisoria (`debe_cambiar_password=True`)  
**Quiero** cambiar mi contraseña mediante `POST /auth/cambiar-password`  
**Para** desbloquear el resto de las funcionalidades del sistema.  
**Criterios de aceptación:**
- Mientras esté pendiente, cualquier llamada a rutas protegidas devuelve HTTP 403 (RN-06).
- Al cambiar la contraseña, se actualiza `password_hash`, `debe_cambiar_password=False` y `password_cambiada_en=NOW()`.
- Se emite una cookie nueva. Las sesiones anteriores devuelven HTTP 401 de inmediato porque su `iat` es menor a `password_cambiada_en` (RN-07).

---

## Épica 3: Clientes y Flota de Vehículos
### US-006 — Gestión de Fichas de Clientes y Vehículos
**Como** personal de recepción o administrador  
**Quiero** dar de alta clientes y asignarles vehículos  
**Para** vincularlos a los ingresos de reparación.  
**Criterios de aceptación:**
- `POST /clientes` crea ficha (documento único).
- `POST /clientes/{id}/vehiculos` asocia vehículo (patente única entre vigentes, año entre 1950 y 2100).
- `DELETE /vehiculos/{id}` realiza borrado lógico (`borrado_en = NOW()`). Si tiene órdenes no finales, responde HTTP 409 (RN-16).
- Un vehículo dado de baja puede volver a registrarse con la misma patente para otro cliente (C-19).

### US-007 — Consulta de Vehículos Propios
**Como** cliente autenticado  
**Quiero** acceder a `GET /mis-vehiculos`  
**Para** visualizar mis vehículos registrados y ninguno ajeno (RN-17).

---

## Épica 4: Repuestos, Stock y Precios
### US-008 — Catálogo y Búsqueda de Repuestos
**Como** personal del taller (Admin, Recepción, Mecánico)  
**Quiero** buscar repuestos por descripción con paginación  
**Para** consultar disponibilidad y precios.  
**Criterios de aceptación:**
- Listado con envoltorio `{ items, total, page, size, pages }`.
- Parámetros `q`, `page` (inicia en 1), `size` (1 a 100). Búsqueda segura con parámetros ligados (C-16).
- Solicitar una página inexistente responde HTTP 422.

### US-009 — Reposición y Cambio de Precio
**Como** administrador  
**Quiero** reponer stock o modificar precios de repuestos  
**Para** mantener el inventario y listas comerciales al día.  
**Criterios de aceptación:**
- `POST /repuestos/{id}/reponer` incrementa stock y registra fila en `movimiento_stock`.
- `PATCH /repuestos/{id}` permite cambiar descripción y/o precio.
- Si cambia el precio, genera fila en `historial_precio_repuesto` en la misma transacción (RN-20). Si el precio enviado es idéntico, no genera fila.
- Intentar modificar `stock` en el body de PATCH da HTTP 422 (`extra="forbid"`).

---

## Épica 5: Órdenes de Trabajo y Reparaciones
### US-010 — Apertura de Orden de Trabajo
**Como** recepción o administrador  
**Quiero** abrir una orden especificando vehículo, falla y lista de repuestos  
**Para** dar ingreso al taller.  
**Criterios de aceptación:**
- Valida al menos un ítem y sin repuestos repetidos (RN-10).
- El servidor copia el precio unitario vigente de cada repuesto y calcula el `total`.
- La orden nace en estado `PENDIENTE` y se crea la primera línea en `historial_estado_orden`.
- Responde HTTP 201.

### US-011 — Iniciar Reparación
**Como** mecánico  
**Quiero** iniciar una orden pendiente con `POST /ordenes/{id}/iniciar`  
**Para** asignarme el trabajo y pasar la orden a `EN_REPARACION`.  
**Criterios de aceptación:**
- Pasa de `PENDIENTE` a `EN_REPARACION`, asigna `mecanico_id` al usuario autenticado y crea línea de historial (RN-11).

### US-012 — Terminar Reparación y Descuento de Stock
**Como** mecánico asignado o administrador  
**Quiero** finalizar una orden con `POST /ordenes/{id}/terminar`  
**Para** registrar el trabajo completado y descontar el inventario usado.  
**Criterios de aceptación:**
- En un único Unit of Work:
  1. Descuenta stock de cada repuesto utilizado.
  2. Inserta una fila en `movimiento_stock` por cada ítem.
  3. Actualiza estado a `TERMINADA`.
  4. Inserta línea en `historial_estado_orden`.
- Si el stock de cualquier repuesto no alcanza, la transacción completa se revierte y devuelve HTTP 409 (RN-13).
- Tras confirmar, se dispara notificación simulada en segundo plano vía `BackgroundTasks` (Ej. 8).

### US-013 — Cancelación de Orden
**Como** recepción, administrador o dueño del vehículo  
**Quiero** cancelar una orden pendiente con `POST /ordenes/{id}/cancelar`  
**Para** anular el servicio sin penalización de stock.  
**Criterios de aceptación:**
- Evalúa permisos antes del estado: si quien intenta cancelar no es el dueño ni personal, devuelve HTTP 403 antes de chequear el estado (RN-12).
- Si tiene permisos pero la orden ya fue terminada o no está en estado cancelable, devuelve HTTP 409.
