import json

from prompts.plantillas import PLANTILLA_VISUAL


def build_prompt_resumen(registro: dict) -> str:
    return f"""
    Eres el Auditor de MaravIA. Genera un resumen VISUAL DINÁMICO: incluye en el resumen ÚNICAMENTE las líneas cuyos campos tengan valor (no null, no vacío, no 0). Si un campo está vacío, esa línea no se escribe. Lo que falte irá al diagnóstico.

    DATOS EN REDIS (JSON):
    {json.dumps(registro, ensure_ascii=False)}

    {PLANTILLA_VISUAL}

    ### DIAGNÓSTICO DINÁMICO (solo lo que REALMENTE falta):
    Incluye en el diagnóstico ÚNICAMENTE los campos que están vacíos (null, "", 0 o ausentes).
    **Obligatorios** (solo si faltan):
    1. Monto/Detalle (monto_total y productos)
    2. Cliente/Proveedor (entidad_nombre, entidad_numero o entidad_id)
    3. Tipo de documento (tipo_documento: factura, boleta, nota de venta)
    4. Moneda (moneda: PEN o USD)
    **NO listar como faltantes:** sucursal, forma de pago, medio de pago, banco (se gestionan en opciones / Estado 2).

    Redacta cada ítem en lenguaje natural: "Falta el tipo de documento (¿Factura o Boleta?)."
    Si no falta ningún obligatorio: "✅ No falta ningún dato obligatorio. Puede *confirmar registro* para continuar (la opción de emitir la lleva otro agente)."

    ### INSTRUCCIONES:
    - Resumen: Solo líneas cuyo dato exista. No inventes valores.
    - Usa nombres naturales (Factura, Soles, Cliente), nunca IDs numéricos.
    - Los campos ya usan nombres naturales (operacion, tipo_documento, moneda, etc.).
    """
