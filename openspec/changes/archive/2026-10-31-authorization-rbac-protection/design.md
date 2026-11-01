# Design

## Context

Ver `proposal.md - Why`. C-04 dejó `get_current_user` consultando roles vigentes, pero no existe `requiere_rol` aplicado, ni grupo protegido, ni cambio de contraseña, ni gestión de roles, ni auditoría consultable. El esquema ya contiene `password_cambiada_en`, `asignacion_rol` (con índice único parcial `uq_asignacion_rol_activa`) y `evento_seguridad` (`actor` textual), por lo que C-05 no requiere migración. Ver los requisitos en `specs/authorization-rbac/spec.md`, `specs/security-audit/spec.md`, `specs/api-error-handling/spec.md` y el delta de `specs/auth-session/spec.md`.

## Goals / Non-Goals

**Goals:**
- Bloquear con 403 todo el grupo Protegido cuando `debe_cambiar_password=True`, incluidos GET.
- Invalidar sesiones anteriores al cambio de contraseña con precisión de microsegundos.
- Gestionar asignaciones de rol con vigencia, reasignación de vencidos y autoprotección admin.
- Auditar altas, cambios de rol y de contraseña, y exponer `GET /eventos`.
- Traducir errores de integridad sin filtrar detalles de PostgreSQL.

**Non-Goals:**
- RN-17 (`/mis-*`) y los módulos de clientes, vehículos, repuestos y órdenes (C-06+).
- `SoftDeleteRepository.get_by_id_including_deleted` (consigna Ejercicio 6, C-06).
- Login fallido en `evento_seguridad`: sigue registrándose sólo en `intento_acceso`.
- Paginación del historial de roles.
- Cambios de esquema o migraciones Alembic.

## Decisions

### D1. Dos grupos de rutas montados en `main.py`
`main.py` monta el grupo Abierto (`health_router` + router de `/auth`) y el grupo Protegido (`router_personal` con `/usuarios` y `/eventos`) usando `app.include_router(router_personal, dependencies=[Depends(requiere_password_actualizada)])`. La dependencia del grupo exige `get_current_user` y responde 403 si la bandera está activa; los routers declaran además `requiere_rol("ADMIN")` por ruta.

- **Por qué:** es el mecanismo prescripto por la consigna (Ejercicio 5 y §5.10): FastAPI suma dependencias y no las resta, y una dependencia montada una sola vez no puede distinguir métodos. Por eso RN-06 bloquea también GET; “y las de GET” se considera error de redacción superado por C-09 y §5.7.
- **Alternativas:** middleware que inspecciona el método — rechazado porque contradice el garante “dos grupos de rutas” y complica el acceso a la sesión de base.
- **Caché de dependencias:** `get_current_user` se ejecuta una sola vez por petición porque FastAPI cachea la misma callable; el grupo y `requiere_rol` comparten el resultado.

### D2. Comparación `iat` vs `password_cambiada_en` (punto 1)
`crear_access_token` acepta `emitido_en: datetime | None`. El cambio de contraseña toma **un único** `momento = datetime.now(timezone.utc)` con microsegundos, lo guarda en `password_cambiada_en` y emite el token nuevo con `emitido_en=momento`, de modo que `iat == password_cambiada_en`.

`get_current_user` compara sin truncar:

```text
si password_cambiada_en es NULL: aceptar
si falta iat o no es numérico: 401
referencia = password_cambiada_en (si es naive, se asume UTC)
si iat < referencia.timestamp(): 401
```

- **Igualdad permitida:** el token nuevo pasa porque `iat == password_cambiada_en` no es “estrictamente anterior”.
- **Anterior rechazado:** cualquier token de login previo tiene `iat` menor por microsegundos, aunque comparta el segundo, y recibe 401.
- **Por qué no `NOW()` de PostgreSQL:** `NOW()` es la hora de inicio de la transacción y depende del reloj de la base; un único timestamp de aplicación garantiza el orden `iat`/`password_cambiada_en` sin desfase. La comparación usa `.timestamp()` sobre el valor devuelto por asyncpg.
- **Alternativa:** truncar a segundos — rechazada por RN-07 y DD-05.

### D3. Límite de 72 bytes en contratos
Un validador Pydantic reutilizable mide `len(valor.encode("utf-8"))` y rechaza con 422 si supera 72 bytes; se aplica a registro, login, alta de personal y a ambas contraseñas del cambio. El mínimo es 6 caracteres, consistente con `RegistroClienteRequest`.

- **Por qué:** bcrypt ≥5 rechaza entradas de más de 72 bytes con excepción; sin validación de contrato eso sería un 500 en lugar de 422. `max_length` de Pydantic cuenta caracteres, no bytes, por lo que el validador es la fuente de verdad.
- `hash_password` conserva el truncado defensivo a 72 bytes, pero el contrato impide que se llegue a él con entradas mayores.

### D4. Cambio de contraseña
`POST /auth/cambiar-password` vive en el grupo Abierto pero depende de `get_current_user` (autenticado). Secuencia:

1. Verificar `password_actual` con `verify_password` (off-loop, semáforo).
2. Si no coincide → 401 sin escribir.
3. Hashear `password_nueva` con `hash_password` **antes** de abrir el UoW.
4. Abrir UoW: actualizar `password_hash`, `debe_cambiar_password=False`, `password_cambiada_en=momento`, insertar evento `CAMBIO_PASSWORD`.
5. Al confirmar, emitir cookie nueva con `crear_access_token(..., emitido_en=momento)`.

- **Por qué hashear antes:** la consigna prohíbe retener la conexión durante bcrypt.
- El usuario puede cambiar su contraseña aunque la bandera ya esté apagada.

### D5. Asignación y reasignación de roles (punto 2)
`POST /usuarios/{id}/roles` valida `rol` con `Literal` del catálogo y `vence_en` con zona horaria y futuro (422). Dentro de un único UoW:

1. Verificar usuario → 404.
2. `get_abierta(usuario_id, rol, for_update=True)`: `SELECT ... WHERE revocada_en IS NULL FOR UPDATE`.
3. Si existe y está vigente → 409 (RN-03).
4. Si existe y está vencida → `revocada_en = ahora` y `flush()`.
5. Insertar la nueva asignación con `desde=ahora` y `otorgada_por=actor.id`.
6. Insertar evento `ASIGNACION_ROL`.

Concurrencia:
- `FOR UPDATE` serializa a los escritores sobre la misma fila abierta.
- Si dos peticiones no ven fila abierta y ambas intentan insertar, el índice único parcial `uq_asignacion_rol_activa` deja pasar una sola; la otra recibe `IntegrityError` 23505, el UoW revierte y el handler global responde 409.
- Si ambas ven la fila vencida, la segunda espera el lock; al continuar, su `SELECT ... FOR UPDATE` ya no encuentra fila abierta (o encuentra la nueva vigente) y termina en 409 sin duplicar.
- **Resultado garantizado:** exactamente una fila abierta por `(usuario_id, rol)` y ninguna fila parcial si algo falla.

### D6. Revocación y autoprotección
`DELETE /usuarios/{id}/roles/{rol}` usa `rol: str`; si no hay asignación abierta —incluido un rol fuera del catálogo— responde 404, respetando los códigos 200/404/409 de la consigna. Si el actor revoca su propio `ADMIN` → 409. Si el rol es `ADMIN`, cuenta administradores vigentes excluyendo la asignación objetivo (no revocadas y sin vencer); si el resultado es 0 → 409. La revocación escribe `revocada_en` sin borrar la fila y audita `REVOCACION_ROL`.

### D7. Historial de roles
`GET /usuarios/{id}/roles` devuelve todas las asignaciones ordenadas por `desde DESC`, con `rol`, `desde`, `vence_en`, `revocada_en`, `otorgada_por` y `vigente` calculado (`revocada_en IS NULL` y sin vencer). Sin paginación; 404 sólo si el usuario no existe.

### D8. Auditoría con actor textual
`EventoSeguridad` no tiene `usuario_id`; `actor` es texto (`models.py:114`). Se escribe `actor = usuario.email` del autenticado y acciones estables `ALTA_USUARIO`, `ASIGNACION_ROL`, `REVOCACION_ROL`, `CAMBIO_PASSWORD`. El seed sigue usando `"SISTEMA"`. El evento se inserta en el mismo UoW de la operación: si la operación revierte, no queda evento.

### D9. `GET /eventos`
Paginado con `ParamsPaginacion` y `armar_paginacion` (`app/core/paginacion.py`), orden `cuando DESC`, sólo ADMIN. Se agrega `EventoSeguridadRepository` al `UsuariosUnitOfWork`.

### D10. Handler global de `IntegrityError` (punto 3)
`@app.exception_handler(IntegrityError)` inspecciona `exc.orig` (asyncpg) y traduce sólo una lista explícita:

| Nombre de constraint | HTTP | Mensaje |
|---|---|---|
| `usuario_email_key`, `ix_usuario_email` | 409 | “El correo ya se encuentra registrado” |
| `uq_asignacion_rol_activa` | 409 | “El usuario ya posee ese rol vigente” |
| `ck_asignacion_rol_rol_valido` | 422 | “Rol inválido” |
| FK de `asignacion_rol` | 404 | “Referencia a un recurso inexistente” |

Si el nombre no está en la lista pero el SQLSTATE es conocido (`23505` único, `23503` FK, `23514` CHECK, `23502` NOT NULL), se usa un mensaje genérico de esa clase (409/409/422/422). Cualquier otro error de integridad responde 400 genérico. La respuesta nunca incluye `exc.orig`, SQL, tabla, columna, constraint ni traza; el detalle técnico se registra sólo en el log del servidor. Las excepciones que no son `IntegrityError` no se interceptan.

- **Por qué lista explícita:** evita que un constraint nuevo se traduzca a un código incorrecto o filtre información. Ampliar la lista es una decisión consciente.
- **Rollback:** la excepción sale del `async with uow`, que revierte antes de que el handler formatee la respuesta.

### D11. Supuestos aceptados
- `POST /usuarios` acepta roles de personal `ADMIN`, `RECEPCION` y `MECANICO`; la asignación posterior acepta los cuatro del catálogo.
- `email` se mantiene como `str` con longitud acotada, sin agregar `email-validator`.
- `GET /usuarios/{id}/roles` devuelve una lista plana ordenada por `desde DESC`.
- Sin migraciones Alembic.

## Risks / Trade-offs

- **Reloj entre instancias** → el timestamp único es de la instancia que atiende el cambio; con varias instancias con desfase, un `iat` de otra instancia podría ordenarse mal. Mitigación: despliegue de una instancia para el TP y comparación contra el valor persistido; documentado como supuesto.
- **409 por concurrencia depende del handler global** → si el handler no traduce `uq_asignacion_rol_activa`, la petición perdedora daría 400. Mitigación: prueba dedicada de dos asignaciones concurrentes y lista de constraints.
- **`POST /usuarios` hashea antes de detectar email duplicado** → se gasta un bcrypt innecesario en el rechazo. Mitigación: aceptado; la consigna prioriza no retener la conexión y el índice único decide la carrera.
- **`GET /eventos` sin índice sobre `cuando`** → a gran volumen el ordenamiento degrada. Mitigación: paginación acotada (máx. 100); agregar índice en una migración futura si el volumen lo justifica.
- **Handler global amplio** → un `IntegrityError` no previsto en otro módulo responde 400 genérico. Mitigación: la lista es extensible y el log conserva el detalle.
- **Auditoría en el mismo UoW** → una operación fallida no deja evento. Es el comportamiento requerido por la spec (rollback no deja evento).

## Migration Plan

1. Sin migración de base de datos.
2. Desplegar el código y reiniciar la aplicación; el seed no cambia.
3. Verificar con `pytest` los casos de iat, concurrencia de roles, autoprotección, eventos y handler.
4. Rollback: revertir el código; no hay cambios de esquema que deshacer.
