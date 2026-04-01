# Helpers — Lógica de Dominio y Mappers

Módulos auxiliares que encapsulan reglas de negocio, transformaciones de datos y comunicación con APIs externas.

---

## Módulos

| Archivo | Propósito |
|---------|-----------|
| `registro_domain.py` | Cálculo de estados, validación de campos, normalización |
| `opciones_domain.py` | Campos y orden del flujo de opciones (estado 4) |
| `venta_mapper.py` | Construye payload para `ws_venta.php` (REGISTRAR_VENTA_N8N) |
| `compra_mapper.py` | Construye payload para `ws_compra.php` (REGISTRAR_COMPRA) |
| `productos.py` | Normalización de productos, enriquecimiento con catálogo, listas WhatsApp, IGV |
| `sunat_client.py` | Cliente SUNAT (login + emisión de comprobantes) |
| `fechas.py` | Conversión de formatos de fecha |

---

## registro_domain.py

### Funciones

| Función | Descripción |
|---------|-------------|
| `calcular_estado(registro)` | Retorna 0-3 según campos completos |
| `obtener_estado(registro)` | Lee campo `estado` o `paso_actual` como int |
| `operacion_desde_registro(registro)` | Lee `operacion` o `cod_ope`, normaliza a "venta"/"compra" |
| `operacion_normalizada(op)` | "ventas"→"venta", "compras"→"compra", otro→None |
| `normalizar_documento_entidad(doc)` | Valida DNI (8) / RUC (11); rechaza serie-número |
| `metodo_contado_credito_desde_registro(reg)` | Extrae "contado"/"credito" de metodo_pago o medio_pago |
| `opciones_completas(registro)` | True si sucursal + forma_pago (+ centro_costo en compra) están elegidos |

### calcular_estado — lógica

```
estado 0: sin operacion
estado 1: tiene operacion pero faltan obligatorios
estado 2: al menos un obligatorio lleno
estado 3: TODOS los obligatorios completos
         (monto/productos + entidad + tipo_documento + moneda + metodo_pago)
```

### normalizar_documento_entidad — edge cases

- `"10728842496"` (11 dígitos) → `"10728842496"` (RUC válido)
- `"12345678"` (8 dígitos) → `"12345678"` (DNI válido)
- `"EB01-4"` → `""` (serie-número de comprobante, rechazado)
- `"F001-00005678"` → `""` (serie-número, rechazado)
- `""` → `""`

---

## opciones_domain.py

### Campos del Estado 4

```python
CAMPOS_ESTADO2 = ("sucursal", "centro_costo", "forma_pago")
```

### siguiente_campo_pendiente(registro, tiene_parametros)

Orden:
1. `sucursal` — si falta `id_sucursal`
2. `centro_costo` — solo si `operacion != "venta"` y `tiene_parametros` y falta `id_centro_costo`
3. `forma_pago` — si falta `id_forma_pago` y `forma_pago`
4. `None` — todo completo

**Diferencia venta vs compra:** en venta se salta `centro_costo`.

### Funciones auxiliares

- `lista_para_redis(raw)` — convierte lista heterogénea a `[{id, nombre}, ...]`
- `normalizar_opciones_actuales(raw)` — parsea JSON/bytes/list a lista de dicts

---

## venta_mapper.py

### Mapas de referencia

### _safe_int(val, default=None)

Conversión segura de cualquier valor a int. Maneja `None`, `""`, strings no numéricos, floats. Usado en todo el mapper para proteger contra datos sucios de Redis.

```python
TIPO_DOCUMENTO_MAP = {
    "factura": 1,
    "boleta": 2,
    "recibo por honorarios": 3,
    "nota de venta": 7,
    "nota de compra": 7,
}

MONEDA_MAP = {"PEN": 1, "USD": 2}
MONEDA_SIMBOLO = {"PEN": "S/", "USD": "$"}

FORMA_PAGO_MAP = {
    "efectivo": 1, "transferencia": 2, "tarjeta de credito": 3,
    "tarjeta de debito": 4, "billetera virtual": 5, ...
}
```

### traducir_registro_a_parametros(registro) → (operacion, params)

Convierte el registro Redis en parámetros listos para el payload:
- `id_tipo_comprobante` desde `TIPO_DOCUMENTO_MAP`
- `id_moneda` desde `MONEDA_MAP`
- `fecha_emision` / `fecha_pago` convertidas a `YYYY-MM-DD`
- `tipo_venta`: "Contado" o "Credito" (capitalize de metodo_pago)

### construir_payload_venta_n8n(reg, id_cliente, id_empresa, id_usuario, params) → dict

Payload ejemplo:
```json
{
    "codOpe": "REGISTRAR_VENTA_N8N",
    "empresa_id": 2,
    "usuario_id": 3,
    "id_cliente": 5,
    "id_tipo_comprobante": 7,
    "fecha_emision": "2026-03-25",
    "fecha_pago": "2026-03-25",
    "id_moneda": 1,
    "id_forma_pago": 9,
    "id_sucursal": 14,
    "tipo_venta": "Contado",
    "pdf_url": "https://...",
    "generacion_comprobante": 1,
    "detalle_items": [...]
}
```

**Campo `pdf_url`**: se lee de `reg.get("url")` o `reg.get("enlace_documento")`. Es la URL del documento adjunto enviado por el usuario.

### construir_sintesis_actual(registro) → str

Genera el resumen visual (texto) del estado actual del registro para mostrar al usuario.

---

## compra_mapper.py

### construir_payload_compra(reg, params, id_from, id_usuario) → dict

Payload ejemplo:
```json
{
    "codOpe": "REGISTRAR_COMPRA",
    "empresa_id": 2,
    "usuario_id": 3,
    "id_proveedor": 5,
    "id_tipo_comprobante": 1,
    "fecha_emision": "2026-03-25",
    "nro_documento": "F001-00001",
    "id_moneda": 1,
    "tipo_compra": "Contado",
    "enlace_documento": "https://...",
    "detalles": [...]
}
```

### Normalización de tipo_compra

```python
tipo_compra_raw = (params.get("tipo_venta") or "Contado").strip()
tipo_compra = "Crédito" if tipo_compra_raw.lower() == "credito" else "Contado"
```

PostgreSQL tiene un CHECK constraint que requiere `"Crédito"` con tilde (no `"Credito"`).

### Campo enlace_documento

Se lee de `reg.get("url")` o `reg.get("enlace_documento")`. Si es None, se omite del payload.

### nro_documento (serie-número del comprobante)

Solo se envía si tiene formato válido `SERIE-NUMERO` (ej: `F001-00001`). Si no, se omite para que la API deje serie/número en null.

---

## productos.py

### normalizar_productos_raw(raw) → list[dict]

Acepta:
- Lista de dicts: `[{"nombre": "X", "cantidad": 1, "precio": 100}]`
- JSON string: `'[{"nombre": "X"}]'`
- Texto libre: `"2 x laptop"`, `"laptop, camara"`, `"3 laptops"`

### productos_a_str(productos) → str

Serializa lista de productos a JSON string para guardar en Redis.

### enriquecer_producto_con_catalogo(producto, catalogo_item) → dict

Enriquece un producto extraído por la IA con datos del catálogo (id_catalogo, precio, id_unidad, sku). Si el usuario indicó precio explícito, se respeta sobre el del catálogo.

### catalogo_a_filas_whatsapp(candidatos) → list[dict]

Convierte candidatos de catálogo en filas para lista WhatsApp (title con nombre+precio, description con stock).

### build_payload_lista_productos(id_empresa, phone, id_plataforma, candidatos, nombre_buscado) → dict

Construye payload para ws_send_whatsapp_list con candidatos de catálogo.

### construir_detalle_desde_registro(reg, monto_total, monto_base, monto_igv) → list[dict]

Construye el array de `detalle_items` / `detalles`:

**Cálculo de IGV (18%):**
```python
subtotal = monto_total / 1.18
igv = monto_total - subtotal
```

**Sin IGV para notas y recibos por honorarios:**
```python
if sin_igv:  # nota de venta, nota de compra, recibo por honorarios
    monto_sin_igv = 0.0
    igv = 0.0
```

---

## sunat_client.py

### login_maravia() → str

POST a `ws_login.php` con `{codOpe: "LOGIN", username, password}`. Retorna JWT token.

### SunatResult (dataclass)

```python
@dataclass
class SunatResult:
    success: bool
    url_pdf: str | None = None
    serie: str | None = None
    numero: int | None = None
    serie_numero: str = ""
    error_mensaje: str | None = None
    error_debug: dict | None = None
```

### SunatClient.crear_venta(payload) → SunatResult

POST a `ws_venta.php`. Extrae `pdf_url` en orden de prioridad:
1. `response["pdf_url"]` (REGISTRAR_VENTA_N8N)
2. `response["sunat"]["sunat_data"]["sunat_pdf"]`
3. `response["sunat"]["sunat_data"]["enlace_documento"]`
4. `response["sunat"]["data"]["payload"]["pdf"]["ticket"]`
5. `response["sunat"]["data"]["payload"]["pdf"]["a4"]`

---

## fechas.py

### fecha_ddmmyyyy_a_api(fecha) → str

Convierte `"25-03-2026"` (DD-MM-YYYY) → `"2026-03-25"` (YYYY-MM-DD) para las APIs PHP.
