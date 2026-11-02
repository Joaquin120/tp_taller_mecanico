# Taller Mecánico API

API REST asincrónica para la gestión integral de un taller mecánico de reparación automotriz, desarrollada con **FastAPI**, **SQLAlchemy 2.0 (asincrónico)**, **SQLModel**, **PostgreSQL** y **Alembic**.

Implementa arquitectura limpia en 6 capas, patrón **Unit of Work** con repositorios genéricos y especializados, control de concurrencia y stock atómico, autenticación segura con **bcrypt off-loop** y cookies **HttpOnly**, autorización **RBAC** evaluada en tiempo real contra base de datos, mitigación de consultas N+1 y disparadores de sólo agregado.

---

## Requisitos Previos

- **Python**: 3.12 o superior.
- **PostgreSQL**: 16 o superior.
- **OpenSSL**: para generación de claves seguras.
- Extensión **REST Client** para Visual Studio Code (opcional, para ejecutar la suite `.http`).

---

## Puesta en Marcha Paso a Paso

### 1. Clonar el repositorio
```bash
git clone <url-del-repositorio>
cd tp_taller_mecanico
```

### 2. Crear y activar el entorno virtual
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno
Copiar la plantilla de configuración `.env.example`:
```bash
cp env.example .env
```

Generar una clave segura para la firma de JWT con OpenSSL:
```bash
openssl rand -hex 32
```
Editar el archivo `.env` configurando la contraseña de su instancia local de PostgreSQL (`POSTGRES_PASSWORD`) y pegando la clave generada en `JWT_SECRET_KEY`.

### 5. Crear la base de datos y ejecutar migraciones
En su servidor PostgreSQL local, asegurarse de que la base de datos `taller_mecanico` exista:
```bash
createdb -U postgres taller_mecanico
```
Aplicar las migraciones de esquema y disparadores PL/pgSQL con Alembic:
```bash
alembic upgrade head
```

### 6. Cargar datos iniciales de prueba (Seed)
Ejecutar el script determinístico de datos de prueba:
```bash
python seed.py
```
El script creará el catálogo de estados, usuarios con distintos roles (`admin@example.com`, `recepcion@example.com`, `mecanico@example.com`, `cliente@example.com`, `nuevo@example.com` todos con clave `Password123!`), clientes (Laura y Jorge), repuestos con stock inicial y órdenes de trabajo de prueba.

### 7. Iniciar el servidor ASGI
```bash
uvicorn main:app --reload --port 8000
```
La documentación interactiva Swagger estará disponible en: `http://localhost:8000/docs`.

---

## Ejecución de la Suite de Pruebas

### 1. Pruebas Automatizadas (Pytest)
Para ejecutar la suite completa de pruebas unitarias y de integración:
```bash
pytest -v
```

### 2. Verificación de Cero Consultas N+1 (Caso C-15)
Para ejecutar la prueba instrumentada de conteo de consultas SQL:
```bash
pytest -v -s test/test_c15_n_plus_one.py
```

### 3. Pruebas End-to-End con REST Client (`.http`)
Los casos de prueba mínimos de la cátedra se encuentran estructurados en tres archivos en la carpeta `test/`:
- `test/auth.http`: Casos C-01 a C-09 (parámetros inválidos, registro atómico, cookie HttpOnly, timing-safe, rate-limiting, RBAC, revocación en caliente, autoprotección y cambio de clave).
- `test/ordenes.http`: Casos C-10 a C-13 (alta con cálculo de servidor, rechazo por falta de stock con rollback total, reposición y terminación con background tasks, cancelación de órdenes).
- `test/repuestos_vehiculos.http`: Casos C-16 a C-19 (inyección SQL, paginación estricta, catálogo de estados ordenado, historial de precios y reciclado de patentes con índice parcial).

Abra cualquiera de estos archivos en VS Code con la extensión **REST Client** y ejecute cada petición secuencialmente mediante el botón `Send Request`.

### 4. Verificación de Tablas de Sólo Agregado en PostgreSQL (Caso C-14)
Para verificar el rechazo estricto de `UPDATE` y `DELETE` por disparadores PL/pgSQL y la clave foránea del catálogo:
```bash
psql -U postgres -d taller_mecanico -f test/solo_agregado.sql
```

---

## Evidencias de Verificación Requeridas

### Evidencia Caso C-15: Cero Consultas N+1
Al consultar el detalle de una orden de trabajo (`GET /ordenes/{id}`), el sistema realiza una carga anticipada fija mediante `selectinload` sobre las relaciones (`vehiculo`, `cliente`, `items`, `repuesto`, `historial_estados`, `mecanico`).

Salida verificada por `test/test_c15_n_plus_one.py`:
```
[C-15 EVIDENCIA] Consultas para orden de 2 ítems: 7
[C-15 EVIDENCIA] Consultas para orden de 4 ítems: 7
PASSED test/test_c15_n_plus_one.py::test_c15_detalle_orden_sin_n_plus_one
```
El número de consultas a la base de datos es exactamente **7**, siendo invariante e independiente de la cantidad de ítems de la orden.

### Evidencia Caso C-14: Disparadores de Sólo Agregado y Clave Foránea
Salida emitida por `psql` al ejecutar `test/solo_agregado.sql`:
```
psql:test/solo_agregado.sql:8: ERROR:  No se permite modificar ni eliminar registros de historial_estado_orden (tabla de sólo agregado)
psql:test/solo_agregado.sql:12: ERROR:  No se permite modificar ni eliminar registros de historial_estado_orden (tabla de sólo agregado)
psql:test/solo_agregado.sql:16: ERROR:  No se permite modificar ni eliminar registros de movimiento_stock (tabla de sólo agregado)
psql:test/solo_agregado.sql:20: ERROR:  No se permite modificar ni eliminar registros de movimiento_stock (tabla de sólo agregado)
psql:test/solo_agregado.sql:24: ERROR:  No se permite modificar ni eliminar registros de historial_precio_repuesto (tabla de sólo agregado)
psql:test/solo_agregado.sql:28: ERROR:  No se permite modificar ni eliminar registros de historial_precio_repuesto (tabla de sólo agregado)
psql:test/solo_agregado.sql:35: ERROR:  insert or update on table "orden_trabajo" violates foreign key constraint "fk_orden_trabajo_estado"
DETAIL:  Key (estado)=(ESTADO_INEXISTENTE) is not present in table "estado_orden".
```
Las 6 operaciones de modificación/borrado sobre tablas inmutables son abortadas por los disparadores de base de datos, y la inserción con estado inválido es rechazada por la restricción `fk_orden_trabajo_estado`.
