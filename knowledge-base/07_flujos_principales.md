# Flujos Principales

## Flujo 1: Inicio de Sesión (Login Seguro con Rate-Limit y Timing Attack Protection)

```
Cliente HTTP                 Router / Auth                 Service               Database (intento_acceso)    Database (usuario)
    │                             │                           │                            │                          │
    ├─── POST /auth/login ───────>│                           │                            │                          │
    │                             ├─── login(email, pwd, ip) ─>│                            │                          │
    │                             │                           ├─── contar_fallos_60s() ────>│                          │
    │                             │                           │<── recuento (< 5) ─────────│                          │
    │                             │                           │ (si >= 5: HTTP 429 Retry)  │                          │
    │                             │                           ├─── buscar_por_email() ─────────────────────────────────>│
    │                             │                           │<── usuario (o None) ────────────────────────────────────│
    │                             │                           │                                                        │
    │                             │                           │─── [to_thread + Semáforo]                              │
    │                             │                           │    bcrypt.checkpw(pwd, hash_real O hash_ficticio)      │
    │                             │                           │<── match (True / False)                                │
    │                             │                           │                                                        │
    │                             │                           ├─── registrar_intento(exito) ─> (nueva sesión UoW)     │
    │                             │                           │    COMMIT independiente    ─>│                          │
    │                             │                           │                                                        │
    │                             │<── resultado / token ─────│                                                        │
    │<── HTTP 200 (Set-Cookie) ───│                                                                                    │
```

**Puntos críticos del flujo:**
1. **Rate Limit previo:** Si en los últimos 60s hay 5 fallos con el mismo email e IP, responde 429 de inmediato sin calcular bcrypt (RN-08).
2. **Timing uniforme:** Si el email no existe, se calcula bcrypt contra un hash ficticio precalculado en Lifespan para tardar exactamente lo mismo (~300ms) y evitar enumeración de usuarios (RN-09).
3. **Persistencia del intento:** `intento_acceso` se inserta y confirma en una transacción y sesión independientes que sobreviven al rollback del login fallido (Ej. 7).
4. **Transporte:** El token JWT viaja exclusivamente en la cabecera `Set-Cookie: access_token=...; HttpOnly; SameSite=Lax`.

---

## Flujo 2: Auto-registro de Cliente (Atómico en un solo UoW)

```
Cliente HTTP                  Router                    Service                 Unit of Work / Repositories
    │                           │                          │                                 │
    ├── POST /auth/registro ───>│                          │                                 │
    │   (body con datos)        ├── registrar_cliente() ──>│                                 │
    │                           │                          ├── async with uow:               │
    │                           │                          │   ├── verificar email/doc       │
    │                           │                          │   ├── uow.usuarios.add(u) ─────>│ (flush)
    │                           │                          │   ├── uow.roles.add(rol_cliente)│ (flush)
    │                           │                          │   ├── uow.clientes.add(c) ─────>│ (flush)
    │                           │                          │   └── COMMIT AL SALIR           │
    │                           │                          │<── éxito                        │
    │<── HTTP 201 Creado ───────│                          │                                 │
```
- Si el documento o email ya existen, la base dispara conflicto de unicidad o el servicio lo detecta y el context manager revierte (`rollback()`), respondiendo HTTP 409 sin dejar filas huérfanas (RN-02).

---

## Flujo 3: Creación de Orden de Trabajo (Composición y Cálculo Servidor)

1. **Recepción / Admin** envía `POST /ordenes` con `vehiculo_id`, `falla` y lista de `items: [{"repuesto_id": X, "cantidad": Y}]`.
2. El Router pasa el payload al Service.
3. El Service valida que la lista no esté vacía y no tenga repuestos repetidos (RN-10).
4. El Service consulta en la base el catálogo `estado_orden`: si está vacío, rechaza con HTTP 409 (RN-19).
5. Abre `async with uow:`.
6. Para cada ítem, busca el repuesto vigente; copia su `precio` unitario actual y calcula `subtotal = precio * cantidad`.
7. Calcula el `total` sumando los subtotales.
8. Inserta la `orden_trabajo` en estado `PENDIENTE` con el total calculado.
9. Inserta los `item_orden`.
10. Inserta la primera fila en `historial_estado_orden` (`desde_estado=None`, `hasta_estado='PENDIENTE'`).
11. Confirma la transacción.
12. Responde HTTP 201 con la orden completa, patente del vehículo, ítems con precios copiados y el historial.

---

## Flujo 4: Terminación de Orden de Trabajo (Transacción Compleja y Stock)

```
Mecánico / Admin             Router                   Service                 Unit of Work (Transacción única)
      │                        │                         │                                  │
      ├── POST /terminar ─────>│                         │                                  │
      │                        ├── terminar_orden(id) ──>│                                  │
      │                        │                         ├── async with uow:                │
      │                        │                         │   ├── verificar permisos y estado│
      │                        │                         │   ├── para cada item:            │
      │                        │                         │   │   ├── descontar repuesto.stock
      │                        │                         │   │   └── add(movimiento_stock)  │
      │                        │                         │   │   (si stock < 0 -> ROLLBACK) │
      │                        │                         │   ├── orden.estado = TERMINADA   │
      │                        │                         │   ├── add(historial_estado)      │
      │                        │                         │   └── COMMIT                     │
      │                        │                         ├── agendar BackgroundTask (aviso) │
      │<── HTTP 200 ───────────│                         │                                  │
      │                        │                         ├── [Background] asyncio.sleep(0.5)│
      │                        │                         └── [Background] log aviso cliente │
```

**Garantías:**
- Si un solo repuesto no tiene stock suficiente, salta la excepción, se ejecuta el rollback del UoW y ni el estado de la orden, ni los movimientos ni el stock sufren alteraciones (RN-13, C-11).
- La tarea en background (notificación al cliente simulada con `asyncio.sleep(0.5)`) se ejecuta únicamente tras el commit exitoso de la respuesta (Ej. 8, C-12).
