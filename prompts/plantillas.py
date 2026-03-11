PLANTILLA_VISUAL = """
RESUMEN VISUAL DINÁMICO: incluye ÚNICAMENTE las líneas cuyos campos tengan valor.
Campo vacío, null o 0 = esa línea NO se escribe. No muestres placeholders ni líneas en blanco.

ESTRUCTURA DE SECCIONES (cada línea se muestra SOLO si el campo tiene valor):

0) TIPO DE OPERACIÓN
   ━━━━━━━━━━━━━━━━━━━
   🛒 *COMPRA*  — si operacion = "compra"
   📤 *VENTA*   — si operacion = "venta"
   ━━━━━━━━━━━━━━━━━━━

1) COMPROBANTE Y ENTIDAD
   ━━━━━━━━━━━━━━━━━━━
   📄 *[tipo_documento]* [numero_documento]  — si tipo_documento tiene valor
   👤 *[CLIENTE o PROVEEDOR]:* [entidad_nombre]  — si entidad_nombre definido
   🆔 *[DNI o RUC]:* [entidad_numero]  — si entidad_numero definido
   ━━━━━━━━━━━━━━━━━━━

2) DETALLE Y MONEDAS
   📦 *DETALLE DE [VENTA o COMPRA]:*
   🔹 Cant. [cantidad] x [nombre] — [precio]  — por cada ítem en productos
   💰 *RESUMEN ECONÓMICO:*
   ├─ Subtotal: [monto_sin_igv]  — si monto_sin_igv > 0
   ├─ IGV (18%): [igv]
   └─ *TOTAL: [monto_total]*  — si monto_total > 0
   ━━━━━━━━━━━━━━━━━━━

3) PAGO Y LOGÍSTICA (solo si están definidos)
   💵 *Moneda:* [moneda]  — PEN o USD
   📅 *Emisión:* [fecha_emision]
   📅 *Pago:* [fecha_pago]
   ━━━━━━━━━━━━━━━━━━━

Nota: Sucursal, forma de pago y medio de pago NO se muestran aquí; se eligen en Estado 2 (opciones, tras confirmar registro).

REGLA CRÍTICA — DINÁMICO: Escribe solo las líneas para las que el campo tenga valor real. Si operacion está vacía, no pongas la línea de COMPRA/VENTA. Si tipo_documento está vacío, no pongas la línea del comprobante. Si monto_total es 0 y no hay productos, no pongas resumen económico. Campo vacío/null/0 = esa línea no aparece en el resumen.
"""

ESTRUCTURA_GUIA = """
Orden obligatorio del texto de guía (resumen_y_guia / salida combinada):
(1) PREÁMBULO: una frase en lenguaje natural (ej: "Perfecto, aquí va el resumen completo:").
(2) SÍNTESIS VISUAL DINÁMICA: solo líneas para campos con valor (vacío = no escribir esa línea). Estado completo del registro según PLANTILLA_VISUAL.
(3) Si faltan datos: INVITACIÓN A COMPLETAR (ej: "Me faltan algunos datos para completar:") + PREGUNTAS enumeradas 1️⃣ 2️⃣ 3️⃣ solo por campos realmente vacíos (nunca preguntar por lo ya definido; tipo de cambio solo si moneda ≠ PEN; no preguntar "agregar más productos" si ya hay al menos un producto).
(4) Si no falta nada: cierra con "¿Confirmar todo para continuar?" para que el usuario diga *confirmar* y pase a opciones (sucursal, forma de pago, medio de pago). Pedir confirmación no impide que el usuario siga enviando datos para actualizar.
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
    if not datos or not isinstance(datos, dict):
        return ""
    lineas = ["📋 *Resumen del registro confirmado*", "━━━━━━━━━━━━━━━━━━━━"]
    operacion = (datos.get("operacion") or "").strip().lower()
    if operacion == "venta":
        lineas.append("📤 *VENTA*")
    elif operacion == "compra":
        lineas.append("🛒 *COMPRA*")
    if datos.get("entidad_nombre"):
        lineas.append(f"👤 *Cliente/Proveedor:* {datos.get('entidad_nombre')}")
    if datos.get("entidad_numero"):
        lineas.append(f"🆔 *Documento:* {datos.get('entidad_numero')}")
    monto = float(datos.get("monto_total") or 0)
    if monto > 0:
        lineas.append(f"💰 *Total:* {monto}")
    prod = datos.get("productos")
    if isinstance(prod, list) and prod:
        lineas.append("📦 *Productos:* " + ", ".join(f"{p.get('cantidad', 1)} x {p.get('nombre', '')}" for p in prod[:5]))
    elif isinstance(prod, str) and prod.strip() and prod.strip() != "[]":
        lineas.append("📦 *Productos:* (ver detalle)")
    lineas.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lineas)
