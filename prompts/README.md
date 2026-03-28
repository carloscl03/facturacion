# Prompts — Sistema de Inteligencia Artificial

Los prompts son funciones Python que construyen dinámicamente el texto que se envía a GPT-4.1-mini. Cada prompt tiene reglas estrictas (candados) que controlan el comportamiento de la IA.

---

## Índice

| Archivo | Función | Servicio que lo usa |
|---------|---------|---------------------|
| `plantillas.py` | `PLANTILLA_VISUAL`, `ESTRUCTURA_GUIA`, `formatear_ficha_identificacion` | Todos los prompts |
| `extraccion.py` | `build_prompt_extractor()` | `ExtraccionService` |
| `clasificador.py` | `build_prompt_router()` | `ClasificadorService` |
| `informador.py` | `build_prompt_info()` | `InformadorService` |
| `resumen.py` | `build_prompt_resumen()` | `ResumenService` |
| `preguntador.py` | `build_prompt_preguntador_v2()` | `PreguntadorV2Service` |
| `casual.py` | Prompt directo | `CasualService` |

---

## plantillas.py — Templates compartidos

### PLANTILLA_VISUAL

Template dinámico para el resumen visual. Solo se muestran líneas para campos con valor:

```
0) TIPO DE OPERACIÓN: 🛒 *COMPRA* o 📤 *VENTA*
1) COMPROBANTE: 📄 tipo + número | 👤 entidad | 🆔 documento
2) DETALLE: 📦 productos | 💰 subtotal + IGV + total
3) PAGO: 💵 moneda | 💳 método | 📅 fechas | 📆 crédito
```

### ESTRUCTURA_GUIA

Define el orden obligatorio del texto de salida:
1. **Preámbulo**: frase natural (ej: "Perfecto, aquí va el resumen:")
2. **Síntesis visual**: solo campos con valor
3. **Si faltan datos**: invitación + preguntas enumeradas 1️⃣ 2️⃣ 3️⃣
4. **Si completo**: "¿Confirmar todo para continuar?"

### formatear_ficha_identificacion()

Genera la ficha de identificación cuando se encuentra un cliente/proveedor:
```
✅ Entidad encontrada
👤 Nombre: Empresa SAC
🆔 RUC: 20123456789
📧 Correo: ...
```

---

## extraccion.py — Prompt de extracción de datos

### build_prompt_extractor(estado_actual, ultima_pregunta_bot, mensaje, operacion)

**Rol de la IA:** "Agente Contable Experto de MaravIA"

### Mapeo de campos (entrada → Redis)

| Dato del usuario | Campo Redis |
|------------------|-------------|
| cliente, razón social, proveedor | `entidad_nombre` |
| ruc, dni, documento (8/11 dígitos) | `entidad_numero` + activa identificación |
| factura, boleta, nota | `tipo_documento` |
| serie-número (F001-00001) | `numero_documento` (nunca DNI/RUC aquí) |
| soles, dólares | `moneda` (PEN/USD) |
| contado, crédito | `metodo_pago` |
| productos, items | `productos` (JSON array) |

### Candados y reglas estrictas

**Método de pago (CANDADO):**
- Solo preguntar si `metodo_pago` es null
- Si ya tiene valor → NUNCA repreguntar
- Tratar igual que cualquier otro campo definido

**Días de crédito y cuotas (CANDADO):**
- Solo preguntar si `metodo_pago == "credito"` Y el campo está vacío
- Si `metodo_pago` es "contado" o aún no definido → estas preguntas NO existen

**Numero de documento / serie (CANDADO):**
- Si `tipo_documento` es "nota de venta" o "nota de compra" → NUNCA preguntar serie/número

**Regla 700 PEN:**
- Venta en soles, `monto_total < 700` → documento (RUC/DNI) es opcional
- `monto_total >= 700` → documento es obligatorio

**IGV en notas:**
- `tipo_documento` = "nota de venta" o "nota de compra" → `igv = 0`, `monto_sin_igv = 0`

### Identificación automática

Si se detecta un número de 8 u 11 dígitos:
- `requiere_identificacion.activo = true`
- `termino` = el número detectado
- El backend llama a `IdentificadorService` para buscar/crear la entidad

### Salida JSON esperada

```json
{
    "propuesta_cache": {
        "operacion": "venta",
        "entidad_nombre": "...",
        "entidad_numero": "...",
        "tipo_documento": "factura",
        "numero_documento": "F001-00001",
        "moneda": "PEN",
        "metodo_pago": "contado",
        "monto_total": 100.00,
        "productos": [{"nombre": "X", "cantidad": 1, "precio": 100}],
        ...
    },
    "mensaje_entendimiento": "¡Anotado!",
    "resumen_visual": "📤 *VENTA*\n📄 *Factura*\n...",
    "diagnostico": "Por favor, bríndame estos datos:\n1️⃣ ...",
    "listo_para_finalizar": false,
    "cambiar_estado_a_4": false,
    "ultima_pregunta_keyword": "moneda",
    "requiere_identificacion": {
        "activo": true,
        "termino": "20123456789",
        "tipo_ope": "venta",
        "mensaje": ""
    }
}
```

---

## clasificador.py — Prompt del router

### build_prompt_router(mensaje, ultima_pregunta, estado, operacion, opciones_completo, hay_registro_en_redis)

**Rol de la IA:** "Director de Orquesta del sistema ERP contable"

### Intenciones posibles

| Intención | Destino | Condición |
|-----------|---------|-----------|
| `actualizar` | extraccion | estado ≤ 3, usuario aporta datos |
| `opciones` | opciones | estado ≥ 4, elige sucursal/forma pago |
| `resumen` | generar-resumen | pide ver resumen explícitamente |
| `finalizar` | finalizar-operacion | estado ≥ 5 |
| `casual` | casual | NUNCA con registro (candado) |
| `eliminar` | eliminar-operacion | cancelar, borrar |

### Confirmaciones (siguiente_estado)

**Transición 3 → 4:**
- `estado == 3` + mensaje de confirmación (sí, dale, ok, confirmo...) + sin datos nuevos
- `siguiente_estado = true`, `intencion = "opciones"`

**Transición 4 → 5:**
- `estado == 4` + `opciones_ok == true` + mensaje de confirmación + sin datos nuevos
- `siguiente_estado = true`, `intencion = "finalizar"`

### Prioridad de intenciones

1. `actualizar` (estado ≤ 3, JSON, datos)
2. `opciones` (estado ≥ 4)
3. `resumen` (explícito)
4. `finalizar` (estado ≥ 5)
5. `casual` (nunca con registro)
6. `eliminar`

### Salida JSON

```json
{
    "intencion": "actualizar",
    "op_visible": "venta",
    "opciones_ok": false,
    "siguiente_estado": false,
    "confianza": 0.9,
    "campo_detectado": "entidad"
}
```

---

## informador.py — Prompt de ayuda

### build_prompt_info(mensaje, estado_registro, resumen_debug)

**Rol:** "Agente de Información de MaravIA"

Responde preguntas como:
- "¿Qué me falta?" → lista datos pendientes
- "¿Ya confirmé?" → indica siguiente paso
- "¿Por qué no encontró mi RUC?" → explica problema de documento

---

## resumen.py — Prompt de auditoría

### build_prompt_resumen(registro)

**Rol:** "Auditor de MaravIA"

Genera resumen en formato PLANTILLA_VISUAL + diagnóstico de faltantes. Si todo completo: "✅ No falta ningún dato obligatorio."

---

## preguntador.py — Generador de preguntas

### build_prompt_preguntador_v2(registro, texto_previo, datos_registrados)

Separa la salida en:
- `sintesis_visual`: resumen del estado
- `preguntas_obligatorias`: campos realmente vacíos
- `preguntas_opcionales`: campos secundarios
- `listo_para_finalizar`: bool

---

## casual.py — Saludo inicial

Genera saludo contextual para primer mensaje sin registro. Ejemplo:
- "Hola" → "¡Hola! Para comenzar, elige entre las opciones:"
