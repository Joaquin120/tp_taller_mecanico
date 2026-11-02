# Tasks

## 1. Suite HTTP de Autenticación y Sesiones (`test/auth.http`)

- [x] 1.1 Crear `test/auth.http` estructurando las variables de base (`@baseUrl`), los logins nombrados (`# @name loginAdmin`, `loginRecepcion`, `loginMecanico`, `loginCliente`) y el soporte multi-sesión con `# @no-cookie-jar` y `Cookie: {{login...response.headers.Set-Cookie}}`.
- [x] 1.2 Implementar en `test/auth.http` los casos C-01 (parámetro de ruta no entero con 422 sin ejecutar el handler) y C-02 (registro de cliente 201, seguido de intentos con correo o documento repetidos respondiendo 409 con mensaje propio y sin filas huérfanas), documentando la respuesta esperada en comentarios.
- [x] 1.3 Implementar en `test/auth.http` los casos C-03 (Set-Cookie en login con HttpOnly, SameSite=Lax, Max-Age y sin token en el cuerpo; peticiones sin cookie o con Bearer respondiendo 401), C-04 (timing-safe: correo existente con contraseña errónea vs correo inexistente con 401 idéntico y tiempos parecidos) y C-05 (seis intentos fallidos seguidos donde el sexto responde 429 con Retry-After y los fallos se guardan en `intento_acceso`), documentando respuestas esperadas.
- [x] 1.4 Implementar en `test/auth.http` los casos C-06 (diferenciación 401 contra 403, cliente ve su orden con 200 y ajena con 403), C-07 (revocación de rol en caliente con `# @no-cookie-jar` respondiendo 403 en la petición siguiente, `/auth/yo` reflejando la pérdida y vencimientos inválidos con 422), C-08 (autoprotección: administrador intentando revocar su rol ADMIN responde 409) y C-09 (cambio obligatorio de contraseña bloqueando con 403 salvo `/auth`, y tras cambio, cookie nueva válida 200 y anterior invalidada 401 sin espera), documentando respuestas esperadas.

## 2. Suite HTTP de Órdenes de Trabajo (`test/ordenes.http`)

- [x] 2.1 Crear `test/ordenes.http` configurando variables de servidor y logins multi-sesión para Recepción, Mecánico, Administrador y Cliente con directivas `# @no-cookie-jar`.
- [x] 2.2 Implementar en `test/ordenes.http` el caso C-10 (alta de orden con 2 ítems respondiendo 201 con precios vigentes copiados desde el servidor, total calculado e historial PENDIENTE; y con repuesto inexistente respondiendo 409 sin dejar orden huérfana), documentando respuestas esperadas.
- [x] 2.3 Implementar en `test/ordenes.http` el caso C-11 (terminar orden que solicita más stock del disponible respondiendo 409 y garantizando rollback total con estado, stock, movimientos e historial intactos), documentando respuesta esperada.
- [x] 2.4 Implementar en `test/ordenes.http` el caso C-12 (reposición de stock por el administrador y terminación exitosa de la orden respondiendo 200 con baja de stock, generación de `movimiento_stock`, línea en `historial_estado_orden` y aviso al cliente simulado en `BackgroundTasks`), documentando respuestas esperadas.
- [x] 2.5 Implementar en `test/ordenes.http` el caso C-13 (cancelación por dueño de orden PENDIENTE con 200, orden ajena con 403 incluso si está terminada, y actor autorizado sobre orden terminada con 409), documentando respuestas esperadas.

## 3. Suite HTTP de Repuestos y Vehículos (`test/repuestos_vehiculos.http`)

- [x] 3.1 Crear `test/repuestos_vehiculos.http` configurando endpoints y sesiones autenticadas para Administrador, Recepción y Mecánico.
- [x] 3.2 Implementar en `test/repuestos_vehiculos.http` el caso C-16 (búsqueda con payload SQL injection `q=' OR '1'='1` devolviendo lista vacía con total 0; paginación con `q=freno&size=1` respondiendo `pages: 1` y `page=2` dando 422; `size=500` dando 422; PATCH parcial actualizando sólo lo enviado; y PATCH de stock respondiendo 422 por `extra="forbid"`), documentando respuestas esperadas.
- [x] 3.3 Implementar en `test/repuestos_vehiculos.http` el caso C-17 (catálogo de estados de orden `GET /estados-orden` ordenado por posición con TERMINADA y CANCELADA finales; sin sesión 401; y filtro de órdenes con estado inválido en query param respondiendo 422), documentando respuestas esperadas.
- [x] 3.4 Implementar en `test/repuestos_vehiculos.http` el caso C-18 (actualización de precio vía PATCH generando fila en `/repuestos/{id}/precios` con precio anterior y nuevo; segundo PATCH modificando sólo descripción sin agregar historial de precio; y recepción intentando modificar precio recibiendo 403), documentando respuestas esperadas.
- [x] 3.5 Implementar en `test/repuestos_vehiculos.http` el caso C-19 (baja lógica de vehículo sin órdenes con 204 y registro posterior de la misma patente para otro cliente con 201 por índice único parcial `postgresql_where`; e intento de registrar una segunda patente idéntica vigente respondiendo 409), documentando respuestas esperadas.

## 4. Integridad en Base de Datos y Verificación Cero N+1

- [x] 4.1 Completar `test/solo_agregado.sql` para el caso C-14 con las 6 sentencias de `UPDATE` y `DELETE` sobre las tablas de sólo agregado (`historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto`) más el caso 7 de inserción de una orden con un estado fuera de catálogo rechazado por clave foránea `fk_orden_trabajo_estado`.
- [x] 4.2 Implementar `test/test_c15_n_plus_one.py` para el caso C-15 instrumentando el motor SQLAlchemy mediante el listener `before_cursor_execute` para auditar el número de consultas SQL emitidas en `GET /ordenes/{id}` con 2 y con 4 ítems.
- [x] 4.3 Ejecutar `pytest test/test_c15_n_plus_one.py` y verificar que el conteo de consultas es idéntico entre órdenes con distinto número de ítems, capturando la salida para la entrega.

## 5. Documentación, Configuración y Validación Final

- [x] 5.1 Auditar y completar `env.example` asegurando que incluya todas las variables del sistema (`POSTGRES_*`, `JWT_*`, `BCRYPT_*`, `COOKIE_SECURE`, `SQL_ECHO`) con valores de ejemplo no productivos y el comando `openssl rand -hex 32` para generar el secreto.
- [x] 5.2 Redactar `README.md` exhaustivo con los pasos paso a paso para levantar el proyecto desde cero: requisitos, venv, dependencias, variables de entorno, migraciones con `alembic upgrade head`, datos de prueba con `seed.py`, servidor con `uvicorn`, ejecución de tests y evidencias de C-14 y C-15.
- [x] 5.3 Ejecutar la suite completa de pruebas con `.venv/bin/pytest -q` y confirmar que pasan todas las pruebas sin regresiones.
- [x] 5.4 Ejecutar `openspec validate verification-suite-e2e-docs --strict` y `openspec validate --all --strict` verificando 0 fallos.

## Workflow follow-up

- Archivar el change y sincronizar la spec `e2e-verification` a `openspec/specs/`.
- Marcar `[x]` la entrada de C-09 en `CHANGES.md` al finalizar el archivo.
