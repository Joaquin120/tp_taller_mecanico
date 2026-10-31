-- test/solo_agregado.sql
-- Casos de prueba manuales para disparadores de sólo agregado (RN-15)

-- 1. Intento de UPDATE sobre historial_estado_orden (Debe fallar con excepción)
UPDATE historial_estado_orden SET hasta_estado = 'CANCELADA' WHERE id = 1;

-- 2. Intento de DELETE sobre historial_estado_orden (Debe fallar con excepción)
DELETE FROM historial_estado_orden WHERE id = 1;

-- 3. Intento de UPDATE sobre movimiento_stock (Debe fallar con excepción)
UPDATE movimiento_stock SET cantidad = 99 WHERE id = 1;

-- 4. Intento de DELETE sobre movimiento_stock (Debe fallar con excepción)
DELETE FROM movimiento_stock WHERE id = 1;

-- 5. Intento de UPDATE sobre historial_precio_repuesto (Debe fallar con excepción)
UPDATE historial_precio_repuesto SET precio_nuevo = 9999 WHERE id = 1;

-- 6. Intento de DELETE sobre historial_precio_repuesto (Debe fallar con excepción)
DELETE FROM historial_precio_repuesto WHERE id = 1;
