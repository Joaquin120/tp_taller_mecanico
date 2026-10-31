# Tasks

## 1. Fundaciones de seguridad y autorización

- [ ] 1.1 Extender `crear_access_token` con `emitido_en` opcional para fijar `iat`/`exp` desde un timestamp dado; verificar con `pytest test/test_security.py`.
- [ ] 1.2 Implementar en `get_current_user` la comparación `iat` vs `password_cambiada_en` sin truncar (401 si `iat` es estrictamente menor; igualdad permitida; naive normalizado a UTC); verificar con casos nuevos en `pytest test/test_auth_deps.py`.
- [ ] 1.3 Agregar `requiere_password_actualizada` (403 si `debe_cambiar_password`) y reexportarla en `app/core/dependencies.py`; verificar con `pytest test/test_auth_deps.py`.
- [ ] 1.4 Crear el validador reutilizable de 72 bytes UTF-8 y aplicarlo a `RegistroClienteRequest` y `LoginRequest`; verificar con casos multibyte en `pytest test/test_schemas.py`.
- [ ] 1.5 Documentar en el test de dependencias el caso “mismo segundo, fracción anterior” y el caso “iat igual al cambio”; verificar que ambos escenarios existen y pasan.

## 2. Cambio de contraseña

- [ ] 2.1 Agregar `CambiarPasswordRequest` con contraseña actual y nueva, mínimo 6 y máximo 72 bytes; verificar con `pytest test/test_schemas.py`.
- [ ] 2.2 Implementar `AuthService.cambiar_password`: verificar actual off-loop, hashear nueva antes del UoW, actualizar `password_hash`, apagar bandera, guardar `password_cambiada_en` y auditar `CAMBIO_PASSWORD`; verificar con `pytest test/test_auth_service.py`.
- [ ] 2.3 Exponer `POST /auth/cambiar-password` en el grupo Abierto con `get_current_user` y emitir cookie nueva usando `emitido_en=momento`; verificar con `pytest test/test_auth_router.py`.
- [ ] 2.4 Verificar integración: token anterior al cambio responde 401, token nuevo responde 200 inmediatamente y contraseña actual incorrecta responde 401 sin escribir; cubrir en `pytest test/test_auth_router.py`.

## 3. Repositorios y Unit of Work

- [ ] 3.1 Agregar `EventoSeguridadRepository` con alta, conteo y listado paginado ordenado por `cuando DESC`, e incorporarlo a `UsuariosUnitOfWork`; verificar con `pytest test/test_repository.py` y `pytest test/test_unit_of_work.py`.
- [ ] 3.2 Ampliar `AsignacionRolRepository` con `get_abierta(usuario_id, rol, for_update)`, `listar_por_usuario` y `contar_admins_vigentes(excluir_id)`; verificar con pruebas de repositorio que el `FOR UPDATE` y el filtro de vigencia se aplican.
- [ ] 3.3 Definir las constantes de acción de auditoría (`ALTA_USUARIO`, `ASIGNACION_ROL`, `REVOCACION_ROL`, `CAMBIO_PASSWORD`) y un helper que inserte el evento con `actor` textual; verificar que cada operación de los grupos siguientes deja su fila.

## 4. Personal y roles

- [ ] 4.1 Agregar DTOs `CrearUsuarioRequest`, `UsuarioCreadoResponse`, `AsignarRolRequest`, `AsignacionRolResponse` y `MensajeResponse`; validar rol de personal, `vence_en` con zona horaria y futuro; verificar con `pytest test/test_schemas.py`.
- [ ] 4.2 Implementar `POST /usuarios`: hashear antes del UoW, rechazar email repetido con 409, crear usuario con bandera activa, asignación vigente y evento; verificar 201/409/422 en `pytest test/test_personal_router.py`.
- [ ] 4.3 Implementar `POST /usuarios/{id}/roles`: 404 sin usuario, 409 con rol vigente, 422 con vencimiento inválido, cierre de fila vencida y alta nueva en el mismo UoW; verificar con `pytest test/test_personal_router.py`.
- [ ] 4.4 Probar la concurrencia de reasignación: dos solicitudes simultáneas producen un 201 y un 409, y queda exactamente una fila abierta; verificar con una prueba dedicada en `pytest test/test_personal_router.py` o de servicio.
- [ ] 4.5 Implementar `DELETE /usuarios/{id}/roles/{rol}`: 404 sin asignación abierta o rol inválido, 409 por auto-revocación o último admin vigente, 200 con `revocada_en` y fila conservada; verificar con `pytest test/test_personal_router.py`.
- [ ] 4.6 Implementar `GET /usuarios/{id}/roles` con historial completo, indicador `vigente` y 404 sin usuario; verificar con `pytest test/test_personal_router.py`.
- [ ] 4.7 Exponer las rutas de personal en `router_personal` con `requiere_rol("ADMIN")`; verificar 403 para roles no ADMIN en `pytest test/test_personal_router.py`.

## 5. Eventos de seguridad

- [ ] 5.1 Implementar `GET /eventos` paginado y ordenado por `cuando DESC`, sólo ADMIN; verificar 200, 403 y 422 en `pytest test/test_eventos_router.py`.
- [ ] 5.2 Verificar que alta, asignación, revocación y cambio de contraseña insertan su evento en el mismo UoW y que un rollback no deja evento; cubrir en `pytest test/test_eventos_router.py`.

## 6. Integridad de base de datos

- [ ] 6.1 Implementar el handler global de `IntegrityError` con lista explícita de constraints y fallback por SQLSTATE conocido; cualquier otro error responde 400 genérico; verificar con `pytest test/test_integrity_handler.py`.
- [ ] 6.2 Verificar que email duplicado y asignación concurrente responden 409, y que el cuerpo no contiene SQL, nombres de constraints, tablas ni columnas; cubrir en `pytest test/test_integrity_handler.py` y en la prueba de concurrencia.

## 7. Montaje e integración

- [ ] 7.1 Montar en `main.py` el grupo Abierto y el Protegido con `requiere_password_actualizada`; verificar 401 sin sesión, 403 con bandera activa y 200 tras el cambio con `pytest test/test_auth_router.py`.
- [ ] 7.2 Ajustar las pruebas existentes afectadas por el nuevo montaje y la dependencia de grupo; verificar que `pytest` completo sigue pasando.
- [ ] 7.3 Crear `test/C-07.http`, `test/C-08.http` y `test/C-09.http` con las respuestas esperadas en comentarios; verificar que cada archivo cubre los códigos de su caso.
- [ ] 7.4 Ejecutar la suite completa con `pytest` y confirmar que todos los casos de C-05, C-07, C-08 y C-09 pasan.

## Workflow follow-up

- Revisar los artefactos y, con aprobación, ejecutar `/opsx-apply`.
- Tras verificar, archivar el change y marcar `[x]` en `CHANGES.md` para C-05.
