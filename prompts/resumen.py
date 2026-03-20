import json

from prompts.plantillas import ESTRUCTURA_GUIA, PLANTILLA_VISUAL


def build_prompt_resumen(registro: dict) -> str:
    return f"""
    Eres el Auditor de MaravIA. Debes generar un TEXTO FINAL con el mismo formato visual que el mensaje retornado en el flujo principal (preámbulo + síntesis visual dinámica + diagnóstico de faltantes).

    DATOS EN REDIS (JSON):
    {json.dumps(registro, ensure_ascii=False)}

    Reglas de salida:
    - Sigue SOLO el PLANTILLA_VISUAL: no agregues líneas nuevas, no inventes valores, y elimina cualquier línea cuyo campo correspondiente esté vacío/null/0.
    - El orden y estilo del texto debe respetar ESTRUCTURA_GUIA.
    - Las preguntas del diagnóstico solo deben incluir campos realmente pendientes (estricto por lógica).
    - Si en algún campo ya viene texto con la etiqueta literal "(catálogo)", no la repitas: mantén el texto sin esa etiqueta.

    {PLANTILLA_VISUAL}

    ### DIAGNÓSTICO DINÁMICO (solo lo que REALMENTE falta):
    Incluye en el diagnóstico ÚNICAMENTE los campos obligatorios que estén vacíos o sin definir para poder avanzar al paso de *opciones*:
    1. Monto/Detalle (monto_total y productos)
    2. Cliente/Proveedor (entidad_nombre o entidad_id, y el documento si corresponde)
    3. Tipo de documento (tipo_documento: factura, boleta, nota de venta)
    4. Moneda (moneda: PEN o USD)
    5. Método de pago (metodo_pago: contado o credito)
    6. Si metodo_pago = "credito": dias_credito y nro_cuotas
    
    **NO listar como faltantes:** sucursal, forma de pago, medio de pago, banco (se gestionan en opciones / Estado 2).

    Redacta cada ítem como una pregunta en lenguaje natural.
    Si no falta ningún dato obligatorio: usa un cierre tipo "✅ No falta ningún dato obligatorio. Puedes *confirmar registro* para continuar."

    {ESTRUCTURA_GUIA}
    """
