-- test/solo_agregado.sql
-- Casos de prueba de integridad en PostgreSQL para la cátedra (Caso C-14)
-- Se ejecutan con: psql -d taller_mecanico -f test/solo_agregado.sql

\set ON_ERROR_STOP off

-- 1. Intento de UPDATE sobre historial_estado_orden (Disparador de sólo agregado)
-- Error esperado: ERROR: No se permite modificar ni eliminar registros de historial_estado_orden (tabla de sólo agregado)
UPDATE historial_estado_orden SET hasta_estado = 'CANCELADA' WHERE id = 1;

-- 2. Intento de DELETE sobre historial_estado_orden (Disparador de sólo agregado)
-- Error esperado: ERROR: No se permite modificar ni eliminar registros de historial_estado_orden (tabla de sólo agregado)
DELETE FROM historial_estado_orden WHERE id = 1;

-- 3. Intento de UPDATE sobre movimiento_stock (Disparador de sólo agregado)
-- Error esperado: ERROR: No se permite modificar ni eliminar registros de movimiento_stock (tabla de sólo agregado)
UPDATE movimiento_stock SET cantidad = 99 WHERE id = 1;

-- 4. Intento de DELETE sobre movimiento_stock (Disparador de sólo agregado)
-- Error esperado: ERROR: No se permite modificar ni eliminar registros de movimiento_stock (tabla de sólo agregado)
DELETE FROM movimiento_stock WHERE id = 1;

-- 5. Intento de UPDATE sobre historial_precio_repuesto (Disparador de sólo agregado)
-- Error esperado: ERROR: No se permite modificar ni eliminar registros de historial_precio_repuesto (tabla de sólo agregado)
UPDATE historial_precio_repuesto SET precio_nuevo = 9999 WHERE id = 1;

-- 6. Intento de DELETE sobre historial_precio_repuesto (Disparador de sólo agregado)
-- Error esperado: ERROR: No se permite modificar ni eliminar registros de historial_precio_repuesto (tabla de sólo agregado)
DELETE FROM historial_precio_repuesto WHERE id = 1;

-- 7. Intento de inserción de una orden con un estado que no existe en el catálogo estado_orden
-- Error esperado:
-- ERROR:  insert or update on table "orden_trabajo" violates foreign key constraint "fk_orden_trabajo_estado"
-- DETAIL:  Key (estado)=(ESTADO_INEXISTENTE) is not present in table "estado_orden".
INSERT INTO orden_trabajo (vehiculo_id, estado, falla, creada_en, total)
VALUES (1, 'ESTADO_INEXISTENTE', 'Falla de prueba para verificar integridad de FK', NOW(), 0.00);
