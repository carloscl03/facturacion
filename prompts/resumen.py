import json

from prompts.plantillas import PLANTILLA_VISUAL


def build_prompt_resumen(registro: dict) -> str:
    return f"""
    Eres el Auditor de MaravIA. Genera un resumen que use la PLANTILLA VISUAL compartida. Muestra ÚNICAMENTE las líneas para las que el dato exista en el registro (no null, no vacío, no 0). Lo que falte irá al diagnóstico.

    DATOS EN DB (JSON):
    {json.dumps(registro, ensure_ascii=False)}

    {PLANTILLA_VISUAL}

    ### DIAGNÓSTICO DINÁMICO (solo lo que REALMENTE falta):
    **Regla crítica:** Incluye en el diagnóstico ÚNICAMENTE los campos que en DATOS EN DB están vacíos (null, "", 0 o ausentes). Si un campo YA tiene valor, NO lo menciones.
    **Obligatorios** (solo si faltan): 1) Monto/Detalle, 2) Cliente/Proveedor, 3) Tipo comprobante, 4) Moneda, 5) Tipo de pago, 6) Si crédito: plazo/vencimiento, 7) Fecha emisión / Fecha pago / Cuenta-Caja cuando aplique.
    **NO listar como faltantes:** sucursal, centro de costo, forma de pago (se gestionan por otro medio).
    Redacta cada ítem del diagnóstico en **lenguaje natural**, como preguntas o frases cortas (ej: "Falta el detalle o monto.", "Falta indicar el cliente (nombre o RUC).", "Falta el tipo de comprobante (Factura o Boleta)."). No uses listas técnicas ni nombres de campos.
    **Si no falta ningún obligatorio:** No listes faltantes; escribe algo como "✅ No falta ningún dato obligatorio. Puede confirmar o decir *finalizar* para emitir."

    ### INSTRUCCIONES:
    - Resumen: Sigue la plantilla; incluye SOLO las líneas cuyo "mostrar si" se cumpla con DATOS EN DB. No inventes valores.
    - Usa nombres (Factura, Soles, Cliente/Proveedor), nunca IDs numéricos.
    - Diagnóstico: Solo campos pendientes, en lenguaje natural. Si entidad_numero_documento o entidad_nombre tienen valor (o hay cliente_id/proveedor_id), no cuentes cliente/proveedor como faltante.
    """
