# Spec Delta

## ADDED Requirements

### Requirement: Cambio de contraseña autenticado
`POST /auth/cambiar-password` SHALL exigir una sesión válida y recibir la contraseña actual y la nueva. SHALL verificar la actual fuera del event loop, hashear la nueva antes de abrir el UoW, actualizar `password_hash`, apagar `debe_cambiar_password`, registrar `password_cambiada_en` y emitir una cookie nueva. Una contraseña actual incorrecta SHALL responder 401.

#### Scenario: Cambio exitoso
- **WHEN** un usuario autenticado envía su contraseña actual correcta y una nueva válida
- **THEN** responde HTTP 200, `debe_cambiar_password` queda en `false`, se registra `password_cambiada_en` y la respuesta incluye una cookie nueva

#### Scenario: Contraseña actual incorrecta
- **WHEN** la contraseña actual no coincide
- **THEN** responde HTTP 401 y no se modifica el hash ni la bandera

#### Scenario: Sin sesión
- **WHEN** se llama a `POST /auth/cambiar-password` sin cookie válida
- **THEN** responde HTTP 401

#### Scenario: Contraseña nueva fuera de límite
- **WHEN** la contraseña nueva supera 72 bytes UTF-8 o tiene menos de 6 caracteres
- **THEN** responde HTTP 422 y no se modifica nada

### Requirement: Invalidación de sesiones por cambio de contraseña
Al cambiar la contraseña, el sistema SHALL comparar el `iat` del token con `password_cambiada_en` sin truncar a segundos. Un token con `iat` estrictamente anterior SHALL responder 401; un token con `iat` igual o posterior SHALL ser válido. El token emitido por el propio cambio SHALL usar el mismo timestamp registrado.

#### Scenario: Token anterior al cambio
- **WHEN** se usa un token emitido antes de `password_cambiada_en`
- **THEN** responde HTTP 401

#### Scenario: Token con iat igual al cambio
- **WHEN** se usa el token emitido por el propio cambio, cuyo `iat` es igual a `password_cambiada_en`
- **THEN** el token es aceptado y la petición se ejecuta

#### Scenario: Mismo segundo pero fracción anterior
- **WHEN** el token anterior y el cambio ocurren en el mismo segundo, con `iat` menor por fracciones de segundo
- **THEN** el token anterior responde HTTP 401 porque la comparación no se trunca

#### Scenario: Token nuevo funciona de inmediato
- **WHEN** el usuario usa la cookie devuelta por el cambio sin esperar
- **THEN** la sesión nueva es válida y las rutas permitidas responden normalmente

### Requirement: Límite de 72 bytes en contratos de contraseña
Todo contrato que reciba una contraseña —registro, login, alta de personal y cambio— SHALL validar el límite de bcrypt y responder 422 si la entrada supera 72 bytes UTF-8. El límite SHALL medirse en bytes y no en caracteres, de modo que un carácter multibyte cuente por su tamaño real.

#### Scenario: Exactamente 72 bytes
- **WHEN** la contraseña ocupa exactamente 72 bytes UTF-8
- **THEN** el contrato la acepta

#### Scenario: Un byte de más
- **WHEN** la contraseña ocupa 73 bytes UTF-8
- **THEN** responde HTTP 422 sin invocar bcrypt

#### Scenario: Caracteres multibyte
- **WHEN** la contraseña tiene 40 caracteres «ñ», que ocupan 80 bytes
- **THEN** responde HTTP 422 porque el límite se mide en bytes

## MODIFIED Requirements

### Requirement: Cierre de sesión elimina cookie
`POST /auth/logout` SHALL eliminar la cookie de sesión estableciendo `Max-Age=0` en la respuesta. El endpoint SHALL ser abierto e idempotente: SHALL responder HTTP 200 exista o no una cookie válida y NO SHALL exigir autenticación.

#### Scenario: Logout elimina cookie
- **WHEN** se envía `POST /auth/logout` con una cookie de sesión válida
- **THEN** la respuesta tiene HTTP 200 y la cabecera `Set-Cookie` establece `Max-Age=0` para `access_token`

#### Scenario: Logout sin cookie
- **WHEN** se envía `POST /auth/logout` sin cookie
- **THEN** la respuesta tiene HTTP 200 y no exige autenticación

#### Scenario: Logout con token vencido
- **WHEN** se envía `POST /auth/logout` con una cookie vencida o inválida
- **THEN** la respuesta tiene HTTP 200 y elimina la cookie de todos modos
