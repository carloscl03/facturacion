# Tests — Guía de Pruebas

## Tipos de tests

| Tipo | Requiere servidor | Crea registros reales | Descripción |
|------|-------------------|-----------------------|-------------|
| **Integración API** | No (llama APIs PHP directamente) | Sí | Envía payloads a las APIs PHP de producción |
| **Unitario** | No | No | Prueba funciones/servicios con mocks o lógica pura |
| **Infraestructura** | No | No | Verifica conexiones (Redis, OpenAI) |
| **WhatsApp** | No | No (solo envía mensajes) | Envía mensajes reales por WhatsApp |

---

## Prerrequisitos

```bash
# Activar entorno virtual
venv\Scripts\activate    # Windows

# Variables de entorno necesarias
cp .env.example .env     # Configurar OPENAI_API_KEY, CACHE_BACKEND, etc.
```

**Para tests de integración API:** requieren acceso a `api.maravia.pe` (APIs PHP).

**Para tests unitarios:** no requieren conexión externa.

**Para tests de WhatsApp:** requieren credenciales WhatsApp configuradas.

---

## Ejecución

```bash
# Test individual (script directo)
python test/test_url.py

# Con pytest
pytest test/test_helpers_domain.py -v

# Todos los tests pytest
pytest test/ -v
```

---

## Tests de integración API

Llaman directamente a las APIs PHP. **Crean registros reales** en la base de datos.

| Test | API | Descripción |
|------|-----|-------------|
| `test_registro.py` | `ws_compra.php` | Registra compra completa con todos los campos |
| `test_pdf_sunat.py` | `ws_venta.php` | Registra nota de venta (sin SUNAT, `generacion_comprobante=0`) |
| `test_nota_venta.py` | `ws_venta.php` | Nota de venta con payload mínimo |
| `test_nota_compra.py` | `ws_compra.php` | Nota de compra con payload mínimo |
| `test_nota_docu.py` | `ws_venta.php` + `ws_compra.php` | Nota sin entidad (id_cliente/id_proveedor = null), monto < 700 |
| `test_url.py` | `ws_venta.php` + `ws_compra.php` | Verifica que `pdf_url` (venta) y `enlace_documento` (compra) se acepten |
| `test_validar_ids_venta.py` | `ws_venta.php` | Prueba compatibilidad de `id_tipo_comprobante` en venta |
| `test_validar_ids_compra.py` | `ws_compra.php` | Prueba compatibilidad de `id_tipo_comprobante` en compra |

### Tests de entidades (crean registros)

| Test | API | Descripción |
|------|-----|-------------|
| `test_cliente.py` | `ws_cliente.php` | Búsqueda de clientes (solo lectura) |
| `test_cliente_obtener_o_crear.py` | `ws_cliente.php` | Busca cliente; si no existe, lo registra |
| `test_proveedor_obtener_o_registrar.py` | `ws_proveedor.php` | Registra proveedor nuevo |
| `test_proveedor_obtener_o_crear.py` | `ws_proveedor.php` | Busca proveedor; si no existe, lo registra |

### Tests de catálogos (solo lectura)

| Test | API | Descripción |
|------|-----|-------------|
| `test_obtener_pagos.py` | `ws_medio_pago.php` | Lista métodos de pago |
| `test_inventario.py` | `ws_informacion_ia.php` | Consulta catálogo público |
| `test_opciones.py` | `ws_informacion_ia.php` + `ws_forma_pago.php` | Flujo completo de listas (sucursales + formas pago) |

---

## Tests unitarios / locales

No requieren servidor ni conexión a APIs externas (excepto `test_opciones_service_unit.py` que llama APIs pero no FastAPI).

| Test | Descripción |
|------|-------------|
| `test_helpers_domain.py` | Funciones de `registro_domain`, `opciones_domain`, `productos`, `venta_mapper`. Cubre: `operacion_normalizada`, `normalizar_documento_entidad`, `calcular_estado`, `opciones_completas`, `siguiente_campo_pendiente`, etc. |
| `test_opciones_service_unit.py` | `OpcionesService` con APIs reales (formas pago, sucursales) pero sin levantar FastAPI |
| `test_sunat_payload_contracts_debug.py` | Valida estructura de payloads para SUNAT |

---

## Tests de infraestructura

| Test | Descripción |
|------|-------------|
| `test_redis.py` | Conecta a Redis, prueba operaciones básicas (set/get/delete) |
| `test_conexion.py` | Verifica conexión con OpenAI (envía prompt de prueba) |
| `test_leer_historial.py` | Lee caché HTTP (`ws_historial_cache.php`) |
| `test_actualizar_historial.py` | Actualiza caché HTTP |

---

## Tests de WhatsApp

**Envían mensajes reales** al número configurado.

| Test | Descripción |
|------|-------------|
| `test_pdf_wsp.py` | Envía PDF por WhatsApp via `ws_send_whatsapp_oficial.php` |
| `test_whatsapp_buttons.py` | Envía botones interactivos via `ws_send_whatsapp_buttons.php` |

---

## Tests de flujo completo

| Test | Descripción |
|------|-------------|
| `test_fastapi.py` | Simulación end-to-end (requiere servidor en `localhost:3000`) |
| `test_api_campos.py` | Valida campos de login y venta contra la API |

---

## Archivos auxiliares (no son tests pytest)

| Archivo | Descripción |
|---------|-------------|
| `cache_manager.py` | Utilidad para gestión de caché |
| `prueba_cache.py` | Script de prueba de caché |
| `act_historial.py` | Script de actualización de historial |
| `sig_preg_historial.py` | Script de siguiente pregunta |
| `asistente_api.py` | Simulación de asistente |
| `run_factura_minima.py` | Factura mínima de prueba |
| `extraccion_service.py` | Ejecución directa del servicio de extracción |
