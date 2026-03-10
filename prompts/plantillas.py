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
- Sucursal, centro de costo y forma de pago: no se generan preguntas ni se listan como faltantes (se gestionan por otro medio). Si ya tienen valor, se muestran en resumen con sus nombres (sucursal_nombre, centro_costo_nombre, forma_pago_nombre); nunca IDs.
- Cuenta/caja y resto de campos: usa nombres (caja_banco_nombre, etc.), nunca IDs.
Las preguntas deben sonar naturales solo para los campos que sí se preguntan: "¿Cuál es el monto o detalle de los productos?", "¿Cuál es el RUC o nombre del cliente?", "¿Emitimos Factura o Boleta?", "¿Fue al contado o a crédito?", "¿Moneda: Soles o Dólares?", "¿Fecha de emisión/pago?", "¿Cuenta o caja?"
"""

PLANTILLA_RESUMEN_FINAL = """
ESTRUCTURA PARA RESUMEN FINAL (confirmación al usuario). Mostrar cada línea SOLO si el campo tiene valor.
Mapeo desde propuesta_cache: centro_costo → centro_costo o centro_costo_nombre; forma_pago; caja_banco; fecha_pago; tipo_operacion; sucursal_nombre; id_moneda → moneda_nombre.

0) TIPO DE OPERACIÓN (mostrar solo si cod_ope está definido)
   ━━━━━━━━━━━━━━━━━━━
   🛒 *COMPRA*   — si cod_ope = "compras"
   📤 *VENTA*    — si cod_ope = "ventas"
   ━━━━━━━━━━━━━━━━━━━

1) COMPROBANTE Y ENTIDAD
   ━━━━━━━━━━━━━━━━━━━
   📄 *[comprobante_tipo_nombre]* ([Compras/Ventas]) [serie]-[numero]  — si id_comprobante_tipo; serie/numero opcionales si existen
   🏢 *[entidad_nombre]* ([tipo_doc]: [entidad_numero_documento])  — si entidad_nombre; tipo_doc = RUC o DNI
   ━━━━━━━━━━━━━━━━━━━

2) DETALLE Y TOTALES
   📦 [cantidad]x [nombre]  — por cada ítem en productos_json (solo si hay ítems)
   💰 [moneda_simbolo] [monto_base] + IGV [moneda_simbolo] [monto_impuesto] = [moneda_simbolo] [monto_total]
   ━━━━━━━━━━━━━━━━━━━

3) LOGÍSTICA Y PAGO (solo si están definidos en propuesta_cache)
   📍 [sucursal_nombre] | [centro_costo o centro_costo_nombre]
   💳 *Pago:* [tipo_operacion]  — Contado o Crédito (campo tipo_operacion)
   💳 *Forma de pago:* [forma_pago o forma_pago_nombre]  — Yape, Transferencia, Efectivo, etc. (solo si forma_pago definido)
   🏦 *Caja/Cuenta:* [caja_banco]  — si caja_banco definido
   📅 *Fecha de pago:* [fecha_pago]  — si fecha_pago definido (YYYY-MM-DD)
   💵 Moneda: [moneda_nombre]  — Soles o Dólares (id_moneda → lenguaje natural)
   ━━━━━━━━━━━━━━━━━━━

4) CRÉDITO (solo si tipo_operacion = credito y hay plazo, vencimiento o cuotas)
   🔄 Crédito [plazo_dias] días  — si plazo_dias definido
   📅 *Vencimiento:* [fecha_vencimiento]  — si fecha_vencimiento definido (alternativa o complemento a plazo_dias)
   🔄 [nro_cuotas] cuotas  — si aplica
   📊 Cuota N: [moneda_simbolo] [monto] — [fecha]  — por cada cuota si existe cuotas_json o equivalente
   ━━━━━━━━━━━━━━━━━━━

5) CIERRE
   ¿Confirmo registro?

Ejemplo completo:
📄 Factura (Compras) F002-00045678
🏢 Tech Solutions Perú SAC (RUC: 20612345678)
📦 2x Servidores Dell PowerEdge
💰 S/ 42,372.88 + IGV S/ 7,627.12 = S/ 50,000.00
📍 Sucursal Principal | Tecnología
💳 Pago: Crédito | Forma de pago: Transferencia
🏦 Caja/Cuenta: BCP Cta. Corriente
📅 Fecha de pago: 2026-03-15
💵 Moneda: Soles
🔄 Crédito 60 días | Vencimiento: 2026-05-14
🔄 3 cuotas
📊 Cuota 1: S/ 16,666.67 — 23/04/2026
📊 Cuota 2: S/ 16,666.67 — 23/05/2026
📊 Cuota 3: S/ 16,666.66 — 22/06/2026
¿Confirmo registro?
"""


def formatear_ficha_identificacion(
    nombre_entidad: str,
    doc_identidad: str,
    tipo_doc_txt: str,
    comercial: str,
    correo_ent: str,
    telf_ent: str,
    dir_ent: str,
    rol_txt: str,
    tipo_ope: str,
) -> str:
    """Plantilla dinámica para confirmación pendiente del identificador. Solo se usa cuando hay identificación pendiente."""
    return (
        f"✅ *FICHA DE IDENTIDAD LOCALIZADA*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Nombre/Razón:* {nombre_entidad}\n"
        f"🏪 *N. Comercial:* {comercial}\n"
        f"🆔 *{tipo_doc_txt}:* {doc_identidad}\n"
        f"💼 *Rol:* {rol_txt}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📧 *Correo:* {correo_ent}\n"
        f"📞 *Teléfono:* {telf_ent}\n"
        f"📍 *Dirección:* {dir_ent}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"¿Los datos son correctos para continuar con la operación de *{tipo_ope.upper()}*?"
    )


def formatear_resumen_registro(datos: dict) -> str:
    """Formatea los datos registrados para mostrarlos como resumen aparte del informe de datos y datos faltantes."""
    if not datos or not isinstance(datos, dict):
        return ""
    lineas = ["📋 *Resumen del registro confirmado*", "━━━━━━━━━━━━━━━━━━━━"]
    cod_ope = (datos.get("cod_ope") or "").strip().lower()
    if cod_ope == "ventas":
        lineas.append("📤 *VENTA*")
    elif cod_ope == "compras":
        lineas.append("🛒 *COMPRA*")
    if datos.get("entidad_nombre"):
        lineas.append(f"👤 *Cliente/Proveedor:* {datos.get('entidad_nombre')}")
    if datos.get("entidad_numero_documento"):
        lineas.append(f"🆔 *Documento:* {datos.get('entidad_numero_documento')}")
    if datos.get("monto_total") is not None and float(datos.get("monto_total") or 0) > 0:
        lineas.append(f"💰 *Total:* {datos.get('monto_total')}")
    prod = datos.get("productos_json")
    if isinstance(prod, list) and prod:
        lineas.append("📦 *Productos:* " + ", ".join(f"{p.get('cantidad', 1)} x {p.get('nombre', '')}" for p in prod[:5]))
    if isinstance(prod, str) and prod.strip():
        lineas.append("📦 *Productos:* (ver detalle)")
    lineas.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lineas)
