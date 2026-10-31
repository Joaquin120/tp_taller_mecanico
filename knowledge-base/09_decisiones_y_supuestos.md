# Decisiones de Diseño y Supuestos

## Decisiones Documentadas

### DD-01 — Catálogo `estado_orden` en lugar de `CHECK (estado IN (...))`
- **Decisión:** Modelar los estados de la orden como una tabla catálogo con clave primaria `codigo`, descripción, posición y bandera `es_final`.
- **Contexto:** Las transiciones de órdenes y el borrado lógico de vehículos requieren saber si una orden está activa o finalizada.
- **Alternativas consideradas:** `CHECK` en la tabla `orden_trabajo` con lista fija o enum nativo de Postgres.
- **Justificación:** El catálogo permite agregar metadata (`posicion`, `es_final`) que la API expone ordenadamente (`GET /estados-orden`) y que las reglas de negocio pueden consultar mediante SQL sin hardcodear strings en consultas complejas (RN-16 y RN-19).
- **Trade-offs:** Requiere que la migración cree la tabla y `seed.py` inserte los datos obligatorios antes de poder crear órdenes.

### DD-02 — Token JWT transportado exclusivamente en Cookie `HttpOnly`
- **Decisión:** Almacenar el token en cookie `HttpOnly`, `SameSite=Lax`, `Max-Age` y `Secure` configurable, en vez de devolverlo en el cuerpo o leer de cabecera `Authorization: Bearer`.
- **Contexto:** Seguridad web contra ataques de robo de sesión (XSS).
- **Justificación:** Si un script malicioso se ejecuta en el navegador, no puede leer cookies marcadas como `HttpOnly`. `SameSite=Lax` provee mitigación efectiva contra CSRF para navegación estándar.
- **Trade-offs:** Los clientes API o herramientas de prueba (REST Client en VS Code) deben manejar cookies manualmente (`Cookie: access_token=...`).

### DD-03 — Bcrypt fuera del Event Loop bajo Semáforo Concurrente
- **Decisión:** Ejecutar `bcrypt.hashpw` y `bcrypt.checkpw` mediante `asyncio.to_thread` acotado por `asyncio.Semaphore(MAX_CONCURRENT_BCRYPT)`.
- **Contexto:** Bcrypt es un algoritmo deliberadamente costoso en CPU (~300ms).
- **Justificación:** Si se ejecuta de forma síncrona en el bucle principal de FastAPI, congela el event loop impidiendo atender cualquier otra petición I/O concurrente. El semáforo previene saturar los cores de la CPU ante ráfagas de logins.
- **Trade-offs:** Complejidad adicional en la capa `security.py`.

### DD-04 — `intento_acceso` en Sesión y Transacción Independiente
- **Decisión:** Guardar los intentos de acceso en su propia sesión y transacción con `commit()` inmediato.
- **Contexto:** Un intento de login fallido dispara un error y revierte la transacción actual.
- **Justificación:** Si `intento_acceso` compartiera la transacción del login, el rollback del login fallido borraría el registro del fallo, haciendo imposible contar los 5 intentos en 60 segundos (RN-08).

### DD-05 — Comparación de `iat` y `password_cambiada_en` con Precisión de Microsegundos
- **Decisión:** No redondear ni truncar a enteros los timestamps `iat` del JWT y `password_cambiada_en`.
- **Contexto:** Al forzar cambio de contraseña, la sesión recién emitida debe funcionar mientras que las emitidas fracciones de segundo antes deben invalidarse inmediatamente (RN-07).
- **Justificación:** Truncar a segundos causaría colisiones en cambios de contraseña inmediatos al login, invalidando erróneamente la nueva sesión o permitiendo la anterior.

### DD-06 — Repositorios ejecutan `flush()` y nunca `commit()`
- **Decisión:** Prohibir terminantemente llamar a `session.commit()` dentro de cualquier repositorio (`BaseRepository` o derivados).
- **Contexto:** Gestión atómica de transacciones con Unit of Work.
- **Justificación:** Permite componer múltiples operaciones sobre distintas entidades (ej. restar stock, insertar movimiento, actualizar estado e insertar historial) dentro de un único bloque transaccional atómico. Si una operación falla, el rollback revierte todo.

## Supuestos Inferidos

### SU-01 — Entorno de Evaluación de Pruebas
- **Supuesto:** La corrección del trabajo práctico ejecutará `python seed.py` antes de correr los archivos `.http` y el script `solo_agregado.sql`.
- **Origen:** Sección "Casos de prueba mínimos" de la consigna.
- **Impacto si es falso:** Las pruebas podrían fallar por datos faltantes o estados no inicializados.
- **Validación:** Se documenta detalladamente el flujo de inicialización en el `README.md`.

### SU-02 — Concurrencia de Actualizaciones de Stock
- **Supuesto:** Se asume explícitamente como aceptado el fenómeno de "actualización perdida" (lost update) para terminación concurrente de órdenes en esta etapa del curso (Capítulo 6), postergando bloqueos `SELECT FOR UPDATE` para el Capítulo 7.
- **Origen:** Sección "QUÉ QUEDA AFUERA" de `trabajo_pr_ctico_1_a_6.md`.
