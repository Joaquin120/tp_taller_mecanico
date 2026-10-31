# auth-session Specification

## Purpose
Gestiona la autenticación de usuarios del taller: verificación de credenciales con bcrypt fuera del event loop, emisión y revocación de sesión JWT en cookie HttpOnly, y registro de intentos de acceso en transacción independiente.

## Requirements

### Requirement: Verificación de contraseña fuera del event loop
El sistema SHALL ejecutar `bcrypt.checkpw` y `bcrypt.hashpw` siempre mediante `asyncio.to_thread` bajo un `asyncio.Semaphore(MAX_CONCURRENT_BCRYPT)`. La contraseña ingresada MUST truncarse a 72 bytes antes de cualquier operación con bcrypt.

#### Scenario: Hash generado fuera del event loop
- **WHEN** se llama a `hash_password` con una contraseña válida
- **THEN** el hash resultante es verificable con `verify_password` y la operación no bloquea el event loop

#### Scenario: Contraseña superior a 72 bytes
- **WHEN** se llama a `hash_password` con una contraseña de más de 72 bytes
- **THEN** el sistema trunca la entrada a 72 bytes antes de invocar bcrypt sin error

### Requirement: Rate-limit de intentos de login
El sistema SHALL rechazar con HTTP 429 y cabecera `Retry-After: 60` cuando existan 5 o más intentos fallidos para la misma combinación de `email + IP` en los últimos 60 segundos. Un login exitoso SHALL reiniciar la cuenta de fallos.

#### Scenario: Límite superado
- **WHEN** se realizan 5 intentos fallidos de login con el mismo email e IP en menos de 60 segundos
- **THEN** el sexto intento responde HTTP 429 con `Retry-After: 60` sin verificar la contraseña

#### Scenario: Login exitoso reinicia contador
- **WHEN** después de 4 fallos se realiza un login correcto
- **THEN** el sistema acepta un nuevo intento fallido sin activar el rate-limit

### Requirement: Timing uniforme ante email inexistente
El sistema SHALL calcular bcrypt contra un hash ficticio precalculado en el Lifespan cuando el email no existe, de modo que el tiempo de respuesta sea indistinguible de un email válido con contraseña incorrecta. El mensaje de error SHALL ser siempre `"Credenciales inválidas"`.

#### Scenario: Email no registrado
- **WHEN** se realiza un login con un email que no existe en la base
- **THEN** el sistema responde HTTP 401 con `"Credenciales inválidas"` tras un tiempo equivalente al de verificación bcrypt real

#### Scenario: Contraseña incorrecta
- **WHEN** se realiza un login con un email existente y contraseña incorrecta
- **THEN** el sistema responde HTTP 401 con `"Credenciales inválidas"`

### Requirement: Sesión JWT en cookie HttpOnly
Al autenticarse correctamente el sistema SHALL emitir un JWT y transportarlo exclusivamente en la cabecera `Set-Cookie` con flags `HttpOnly; SameSite=Lax; Max-Age=1800`. El cuerpo de la respuesta NO SHALL contener el token.

#### Scenario: Login exitoso emite cookie
- **WHEN** se envía `POST /auth/login` con credenciales correctas
- **THEN** la respuesta tiene HTTP 200, la cabecera `Set-Cookie` contiene `access_token` con flags `HttpOnly` y `SameSite=Lax`, y el cuerpo no incluye el token

### Requirement: Cierre de sesión elimina cookie
`POST /auth/logout` SHALL eliminar la cookie de sesión estableciendo `Max-Age=0` en la respuesta. El endpoint SHALL ser accesible solo para usuarios autenticados.

#### Scenario: Logout elimina cookie
- **WHEN** se envía `POST /auth/logout` con una cookie de sesión válida
- **THEN** la respuesta tiene HTTP 200 y la cabecera `Set-Cookie` establece `Max-Age=0` para `access_token`

### Requirement: Registro de intentos en transacción independiente
Cada intento de login (exitoso o fallido) SHALL registrarse en la tabla `intento_acceso` en una sesión y transacción separadas que hagan `commit()` de forma independiente, de modo que el rollback del login fallido no borre el registro del intento.

#### Scenario: Intento fallido persiste tras rollback
- **WHEN** un login falla por credenciales incorrectas
- **THEN** el intento queda registrado en `intento_acceso` con `exitoso=False` aunque la transacción principal haga rollback

#### Scenario: Intento exitoso persiste
- **WHEN** un login es exitoso
- **THEN** el intento queda registrado en `intento_acceso` con `exitoso=True`

### Requirement: Consulta de sesión actual
`GET /auth/yo` SHALL devolver los datos del usuario autenticado incluyendo sus roles vigentes consultados en la base en tiempo real (no solo los del token).

#### Scenario: Usuario autenticado
- **WHEN** se envía `GET /auth/yo` con cookie de sesión válida
- **THEN** la respuesta HTTP 200 incluye email, nombre y lista de roles activos del usuario

#### Scenario: Sin cookie
- **WHEN** se envía `GET /auth/yo` sin cookie o con cookie inválida
- **THEN** la respuesta es HTTP 401
