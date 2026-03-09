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
- id_forma_pago: en el registro se guarda el ID; el backend rellena forma_pago_nombre. En síntesis y diagnóstico usa siempre el nombre (ej. "Contado", "Crédito", "Yape", "Transferencia"), nunca el número. Pregunta "¿Cómo pagó? (Contado, Yape, Transferencia...)".
- Sucursal, centro de costo, cuenta/caja: usa siempre los nombres (sucursal_nombre, centro_costo_nombre, caja_banco_nombre), nunca id_sucursal ni números.
Las preguntas deben sonar naturales: "¿Cuál es el monto o detalle de los productos?", "¿Cuál es el RUC o nombre del cliente?", "¿Emitimos Factura o Boleta?", "¿En qué sucursal se realizó?", "¿Fue al contado o a crédito?", "¿Forma de pago?"
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
