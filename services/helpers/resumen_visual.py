"""
Generador estructural de resumen visual y diagnóstico de faltantes.

Reemplaza la generación por IA de resumen_visual, diagnostico y sintesis_visual
con lógica determinista en Python. Reutilizable por cualquier servicio.

Sigue exactamente las reglas de PLANTILLA_VISUAL y ESTRUCTURA_GUIA
definidas originalmente en prompts/plantillas.py.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from services.helpers.igv import calcular_igv, es_tipo_sin_igv
from services.helpers.registro_domain import (
    metodo_contado_credito_desde_registro,
    operacion_desde_registro,
)

# ── Constantes ──────────────────────────────────────────────────────

_MONEDA_SIMBOLO = {"PEN": "S/", "pen": "S/", "USD": "$", "usd": "$"}

_SEP = "━━━━━━━━━━━━━━━━━━━"

# Emojis para listar preguntas
_EMOJI_NUM = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣")


# ── Helpers internos ────────────────────────────────────────────────

def _s(reg: Dict[str, Any], key: str) -> str:
    """Lee un campo como string limpio; '' si vacío/null."""
    v = reg.get(key)
    if v is None:
        return ""
    return str(v).strip()


def _f(reg: Dict[str, Any], key: str) -> float:
    """Lee un campo como float; 0.0 si vacío/null."""
    v = reg.get(key)
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _productos_lista(reg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Obtiene la lista de productos del registro (deserializa si es string)."""
    prod = reg.get("productos")
    if isinstance(prod, list):
        return prod
    if isinstance(prod, str):
        s = prod.strip()
        if s and s != "[]":
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
    return []


# ── Generador del resumen visual ────────────────────────────────────

def generar_resumen_visual(reg: Dict[str, Any]) -> str:
    """
    Genera el resumen visual estructurado desde los datos del registro.

    Sigue la PLANTILLA_VISUAL: solo incluye líneas para campos con valor.
    Campo vacío/null/0 = línea omitida.
    """
    if not reg or not isinstance(reg, dict):
        return ""

    lineas: List[str] = []
    operacion = operacion_desde_registro(reg)
    tipo_doc = _s(reg, "tipo_documento")
    tipo_doc_lower = tipo_doc.lower()
    metodo = metodo_contado_credito_desde_registro(reg)

    # ── 0) Tipo de operación ──
    if operacion == "venta":
        lineas.append(_SEP)
        lineas.append("📤 *VENTA*")
        lineas.append(_SEP)
    elif operacion == "compra":
        lineas.append(_SEP)
        lineas.append("🛒 *COMPRA*")
        lineas.append(_SEP)

    # ── 1) Comprobante y entidad ──
    seccion1: List[str] = []

    if tipo_doc:
        num_doc = _s(reg, "numero_documento")
        # En ventas (factura/boleta) no mostrar numero_documento
        if operacion == "venta" and tipo_doc_lower in ("factura", "boleta"):
            seccion1.append(f"📄 *{tipo_doc.capitalize()}*")
        elif num_doc:
            seccion1.append(f"📄 *{tipo_doc.capitalize()}* {num_doc}")
        else:
            seccion1.append(f"📄 *{tipo_doc.capitalize()}*")

    entidad_nombre = _s(reg, "entidad_nombre")
    if entidad_nombre:
        rol = "CLIENTE" if operacion == "venta" else "PROVEEDOR" if operacion == "compra" else "CLIENTE/PROVEEDOR"
        seccion1.append(f"👤 *{rol}:* {entidad_nombre}")

    entidad_numero = _s(reg, "entidad_numero") or _s(reg, "entidad_numero_documento")
    if entidad_numero:
        tipo_id = "RUC" if len(entidad_numero) == 11 else "DNI" if len(entidad_numero) == 8 else "Doc"
        seccion1.append(f"🆔 *{tipo_id}:* {entidad_numero}")

    if seccion1:
        lineas.append(_SEP)
        lineas.extend(seccion1)
        lineas.append(_SEP)

    # ── 2) Detalle y montos ──
    productos = _productos_lista(reg)
    monto_total = _f(reg, "monto_total")
    monto_sin_igv = _f(reg, "monto_sin_igv") or _f(reg, "monto_base")
    igv_val = _f(reg, "igv") or _f(reg, "monto_impuesto")
    moneda_str = _s(reg, "moneda").upper() or "PEN"
    simbolo = _MONEDA_SIMBOLO.get(moneda_str, "S/")

    sin_igv = es_tipo_sin_igv(tipo_doc)

    seccion2: List[str] = []

    if productos:
        label_detalle = "VENTA" if operacion == "venta" else "COMPRA" if operacion == "compra" else "OPERACIÓN"
        seccion2.append(f"📦 *DETALLE DE {label_detalle}:*")
        for p in productos:
            nombre = p.get("nombre", "")
            cantidad = p.get("cantidad", 1)
            precio = float(p.get("precio_unitario") or p.get("precio") or 0)
            if nombre:
                # Formato cantidad: sin decimales si es entero
                cant_str = str(int(cantidad)) if float(cantidad) == int(float(cantidad)) else f"{cantidad}"
                if precio > 0:
                    seccion2.append(f"   🔹 Cant. {cant_str} x {nombre} — {simbolo} {precio:.2f}")
                else:
                    seccion2.append(f"   🔹 Cant. {cant_str} x {nombre}")

    # Resumen económico
    if monto_total > 0 or (monto_sin_igv > 0):
        seccion2.append("💰 *RESUMEN ECONÓMICO:*")

        # Para factura/boleta: mostrar desglose
        if not sin_igv and tipo_doc_lower in ("factura", "boleta"):
            # Calcular si no tenemos los valores
            if monto_total > 0 and (monto_sin_igv <= 0 or igv_val <= 0):
                igv_incluido = _s(reg, "igv_incluido").lower() != "false"
                _, monto_sin_igv, igv_val = calcular_igv(
                    monto_total, igv_incluido=igv_incluido, sin_igv=False
                )
            if monto_sin_igv > 0:
                seccion2.append(f"   ├─ Subtotal: {simbolo} {monto_sin_igv:.2f}")
            if igv_val > 0:
                seccion2.append(f"   ├─ IGV (18%): {simbolo} {igv_val:.2f}")

        # Total siempre si > 0
        if monto_total > 0:
            seccion2.append(f"   └─ *TOTAL: {simbolo} {monto_total:.2f}*")
        elif monto_sin_igv > 0:
            # Si solo tenemos base (igv_incluido=false), mostrar igualmente
            seccion2.append(f"   └─ *BASE: {simbolo} {monto_sin_igv:.2f}*")

    if seccion2:
        lineas.extend(seccion2)
        lineas.append(_SEP)

    # ── 3) Pago y logística ──
    seccion3: List[str] = []

    moneda_display = _s(reg, "moneda")
    if moneda_display:
        seccion3.append(f"💵 *Moneda:* {moneda_display.upper()}")

    if metodo:
        seccion3.append(f"💳 *Método de pago:* {metodo.capitalize()}")

    # Crédito: días y cuotas
    if metodo == "credito":
        dias = _s(reg, "dias_credito")
        cuotas = _s(reg, "nro_cuotas")
        partes_credito = []
        if dias:
            partes_credito.append(f"📆 *Días crédito:* {dias}")
        if cuotas:
            partes_credito.append(f"📋 *Cuotas:* {cuotas}")
        if partes_credito:
            seccion3.append(" | ".join(partes_credito))

        fecha_pago = _s(reg, "fecha_pago")
        if fecha_pago:
            seccion3.append(f"📅 *Pago:* {fecha_pago}")

    observacion = _s(reg, "observacion") or _s(reg, "observaciones")
    if observacion:
        seccion3.append(f"📝 *Observación:* {observacion}")

    if seccion3:
        lineas.extend(seccion3)
        lineas.append(_SEP)

    return "\n".join(lineas)


# ── Generador de diagnóstico de faltantes ───────────────────────────

def generar_diagnostico(reg: Dict[str, Any]) -> Tuple[str, bool]:
    """
    Genera el diagnóstico de campos faltantes siguiendo el orden estricto.

    Retorna (texto_diagnostico, listo_para_finalizar).
    - Si no falta nada: texto de cierre + listo_para_finalizar=True
    - Si faltan campos: preguntas enumeradas + listo_para_finalizar=False
    """
    if not reg or not isinstance(reg, dict):
        return ("No hay datos para diagnosticar.", False)

    operacion = operacion_desde_registro(reg)
    tipo_doc = _s(reg, "tipo_documento").lower()
    entidad_nombre = _s(reg, "entidad_nombre")
    entidad_numero = _s(reg, "entidad_numero") or _s(reg, "entidad_numero_documento")
    entidad_id = _s(reg, "entidad_id")
    moneda = _s(reg, "moneda")
    metodo = metodo_contado_credito_desde_registro(reg)
    monto_total = _f(reg, "monto_total")
    productos = _productos_lista(reg)
    dias_credito = _s(reg, "dias_credito")
    nro_cuotas = _s(reg, "nro_cuotas")

    preguntas: List[str] = []

    # 1. Monto/Detalle
    if monto_total <= 0 and not productos:
        preguntas.append("¿Cuál es el monto o detalle de productos de la operación?")

    # 2. Tipo de documento
    if not tipo_doc:
        if entidad_numero and len(entidad_numero) == 11:
            preguntas.append("¿Qué tipo de comprobante deseas? ¿Factura, recibo por honorarios o nota de "
                           + ("venta" if operacion == "venta" else "compra" if operacion == "compra" else "venta/compra")
                           + "?")
        elif entidad_numero and len(entidad_numero) == 8:
            preguntas.append("¿Qué tipo de comprobante deseas? ¿Boleta o nota de "
                           + ("venta" if operacion == "venta" else "compra" if operacion == "compra" else "venta/compra")
                           + "?")
        else:
            preguntas.append("¿Qué tipo de comprobante deseas? ¿Factura, boleta, recibo por honorarios o nota de "
                           + ("venta" if operacion == "venta" else "compra" if operacion == "compra" else "venta/compra")
                           + "?")

    # 3. Entidad + documento
    tiene_entidad = bool(entidad_nombre) or bool(entidad_id)
    tiene_doc_identidad = len(entidad_numero) in (8, 11) if entidad_numero else False
    rol = "cliente" if operacion == "venta" else "proveedor" if operacion == "compra" else "cliente/proveedor"

    # Determinar si el documento de identidad es requerido
    doc_requerido = True
    if tipo_doc in ("nota de venta", "nota de compra"):
        doc_requerido = False
    elif not tipo_doc:
        # Regla 700 PEN: si < 700 y PEN, doc es opcional
        if moneda.upper() == "PEN" and 0 < monto_total < 700:
            doc_requerido = False

    if not tiene_entidad and not tiene_doc_identidad:
        # Falta todo de entidad
        if doc_requerido:
            if tipo_doc == "factura" or tipo_doc == "recibo por honorarios":
                preguntas.append(f"¿Cuál es el nombre y RUC del {rol}?")
            elif tipo_doc == "boleta":
                preguntas.append(f"¿Cuál es el nombre y DNI del {rol}?")
            else:
                preguntas.append(f"¿Cuál es el nombre y documento (RUC/DNI) del {rol}?")
        else:
            preguntas.append(f"¿Cuál es el nombre del {rol}?")
    elif tiene_entidad and not tiene_doc_identidad and doc_requerido:
        # Tiene nombre pero falta documento
        if tipo_doc == "factura" or tipo_doc == "recibo por honorarios":
            preguntas.append(f"¿Cuál es el RUC del {rol}?")
        elif tipo_doc == "boleta":
            preguntas.append(f"¿Cuál es el DNI del {rol}?")
        else:
            preguntas.append(f"¿Cuál es el documento (RUC/DNI) del {rol}?")

    # 4. Moneda
    if not moneda:
        preguntas.append("¿En soles (PEN) o dólares (USD)?")

    # 5. Método de pago
    if not metodo:
        preguntas.append("¿Al contado o a crédito?")

    # 6. Días crédito y cuotas (solo si crédito)
    if metodo == "credito":
        if not dias_credito:
            preguntas.append("¿Cuántos días de crédito? (15, 30, 45, 60 o 90)")
        if not nro_cuotas:
            preguntas.append("¿En cuántas cuotas? (1 a 24)")

    # Armar texto final
    if not preguntas:
        return ("✅ No falta ningún dato obligatorio. Puedes decir *confirmar registro* para continuar.", True)

    lineas = ["📋 *Datos obligatorios (para emitir el comprobante):*"]
    for i, pregunta in enumerate(preguntas):
        emoji = _EMOJI_NUM[i] if i < len(_EMOJI_NUM) else f"{i+1}."
        lineas.append(f"{emoji} {pregunta}")

    return ("\n".join(lineas), False)


# ── Función combinada (principal) ──────────────────────────────────

def generar_resumen_completo(
    reg: Dict[str, Any],
    *,
    mensaje_entendimiento: str = "",
) -> Dict[str, Any]:
    """
    Genera resumen visual + diagnóstico combinados, listo para enviar por WhatsApp.

    Parámetros:
        reg: datos del registro (Redis o fusionado con propuesta_cache).
        mensaje_entendimiento: preámbulo generado por la IA (opcional).

    Retorna dict con:
        - resumen_visual: solo la síntesis visual
        - diagnostico: solo las preguntas de faltantes
        - texto_completo: preámbulo + resumen + diagnóstico (listo para WhatsApp)
        - listo_para_finalizar: bool
    """
    resumen = generar_resumen_visual(reg)
    diagnostico, listo = generar_diagnostico(reg)

    # Combinar partes
    partes: List[str] = []
    if mensaje_entendimiento and mensaje_entendimiento.strip():
        partes.append(mensaje_entendimiento.strip())
    if resumen:
        partes.append(resumen)
    if not listo:
        partes.append(diagnostico)
    else:
        partes.append(diagnostico)

    texto_completo = "\n\n".join(partes)

    return {
        "resumen_visual": resumen,
        "diagnostico": diagnostico,
        "texto_completo": texto_completo,
        "listo_para_finalizar": listo,
    }
