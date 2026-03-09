PLANTILLA_VISUAL = """
ESTRUCTURA DE SECCIONES (usa estos nombres de campo del registro; cada línea se muestra SOLO si el campo tiene valor definido):

0) TIPO DE OPERACIÓN (primera línea del encabezado; mostrar solo si cod_ope está definido)
   ━━━━━━━━━━━━━━━━━━━
   🛒 *COMPRA*  — mostrar si: cod_ope = "compras"
   📤 *VENTA*   — mostrar si: cod_ope = "ventas"
   ━━━━━━━━━━━━━━━━━━━

1) ENCABEZADO OPERACIÓN
   ━━━━━━━━━━━━━━━━━━━
   📄 *[comprobante_tipo_nombre]*  — mostrar si: id_comprobante_tipo definido
   👤 *[CLIENTE o PROVEEDOR]:* [entidad_nombre]  — mostrar si: entidad_nombre definido
   🆔 *[DNI o RUC]:* [entidad_numero_documento]  — mostrar si: entidad_numero_documento definido
   ━━━━━━━━━━━━━━━━━━━

2) DETALLE Y MONEDAS
   📦 *DETALLE DE [VENTA o COMPRA]:*
   🔹 Cant. [cantidad] x [nombre] — [moneda_simbolo][total_item]  — por cada ítem en productos_json (mostrar sección si productos_json tiene al menos un ítem)
   💰 *RESUMEN ECONÓMICO:*
   ├─ Subtotal: [moneda_simbolo] [monto_base]  — mostrar si: monto_base definido y > 0
   ├─ IGV (18%): [moneda_simbolo] [monto_impuesto]
   └─ *TOTAL: [moneda_simbolo] [monto_total]*  — mostrar si: monto_total definido y > 0
   ━━━━━━━━━━━━━━━━━━━

3) LOGÍSTICA Y PAGO (todos opcionales; incluir línea solo si el campo está definido)
   📍 *Sucursal:* [sucursal_nombre]  — si: id_sucursal o sucursal_nombre
   🏗️ *Centro de costo:* [centro_costo_nombre]  — si: id_centro_costo o centro_costo_nombre
   💳 *Pago:* [tipo_operacion]  — si: tipo_operacion (contado/credito)
   💵 *Moneda:* [moneda_nombre]  — si: id_moneda
   🏦 *Cuenta/Caja:* [caja_banco_nombre] o [forma_pago_nombre]  — si: caja_banco_nombre o id_forma_pago
   📅 *Emisión:* [fecha_emision]  — si: fecha_emision
   🔄 *Crédito:* [plazo_dias] días | *Vencimiento:* [fecha_vencimiento]  — si: tipo_operacion = credito y (plazo_dias o fecha_vencimiento)
   ━━━━━━━━━━━━━━━━━━━

Regla crítica: NO escribas ninguna línea cuya condición "mostrar si" no se cumpla. Si un campo está vacío, null o 0, esa línea NO debe aparecer en la síntesis (irá al diagnóstico).
"""

REGLAS_NORMALIZACION = """
REGLAS DE NORMALIZACIÓN (OBLIGATORIAS — lenguaje natural, nunca IDs):
En la Síntesis, el Resumen y el Diagnóstico NUNCA uses números ni códigos internos. Siempre traduce a lenguaje natural usando esta tabla:
- id_comprobante_tipo: 1 → "Factura", 2 → "Boleta", 3 → "Recibo". Pregunta p. ej. "¿Deseas emitir Factura o Boleta?" nunca "¿id_comprobante_tipo?"
- id_moneda: 1 → "Soles" (S/), 2 → "Dólares" ($).
- entidad_id_tipo_documento: 1 → "DNI", 6 → "RUC". Pregunta "¿Me das el RUC o DNI del cliente?" no el id.
- tipo_operacion: "contado" → "Contado", "credito" → "Crédito". Pregunta "¿Fue al contado o a crédito?"
- Sucursal, centro de costo, forma de pago, cuenta: usa siempre los nombres (sucursal_nombre, centro_costo_nombre, etc.), nunca id_sucursal ni números.
Las preguntas deben sonar naturales: "¿Cuál es el monto o detalle de los productos?", "¿Cuál es el RUC o nombre del cliente?", "¿Emitimos Factura o Boleta?", "¿En qué sucursal se realizó?", "¿Fue al contado o a crédito?"
"""
