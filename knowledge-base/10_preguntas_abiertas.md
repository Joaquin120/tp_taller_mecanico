# Preguntas Abiertas e Inconsistencias Resueltas

## Inconsistencias Detectadas y Resueltas

### IN-01 — Driver Asincrónico de PostgreSQL (`asyncpg` vs `psycopg 3`)
- **Situación:** La tabla de requisitos menciona `asyncpg 0.30` como recomendado, pero la consigna aclara que también se acepta `psycopg 3` asincrónico.
- **Resolución adoptada:** Se utiliza `asyncpg` (`postgresql+asyncpg://...`) como estándar principal por ser el controlador asincrónico de mayor rendimiento y más probado con SQLAlchemy 2.0 en FastAPI, manteniendo compatibilidad total con la configuración de pydantic-settings.

### IN-02 — Simulación de Tareas en Segundo Plano (`BackgroundTasks`)
- **Situación:** En un entorno productivo los correos/mensajes se encolan con Redis / Celery para evitar pérdidas ante reinicios del proceso.
- **Resolución adoptada:** Se respeta la directiva del Capítulo 3 y sección "Qué queda afuera": el aviso al cliente se despacha mediante `fastapi.BackgroundTasks` con `await asyncio.sleep(0.5)` y un mensaje en el log del servidor, corriendo únicamente si la transacción de base de datos hizo commit exitoso.

## Preguntas Abiertas Priorizadas

| Prioridad | Pregunta / Tópico | Bloquea | Decisor | Estado |
| :--- | :--- | :--- | :--- | :---: |
| **Baja** | ¿El puerto de PostgreSQL por defecto debe ser 5432 o configurable? | Despliegue local | Desarrollador | Resuelto (configurable vía `POSTGRES_PORT` con default 5432) |
| **Baja** | ¿Se requiere soporte de HTTPS para cookies en entorno de desarrollo local? | Configuración de cookies | Desarrollador | Resuelto (`COOKIE_SECURE=False` por defecto en `.env`, `True` en producción) |
| **Baja** | ¿Las contraseñas de `seed.py` deben usar costo bajo de bcrypt para acelerar la inicialización? | Rendimiento de tests | Equipo docente | Resuelto (usar `BCRYPT_ROUNDS` configurable) |
