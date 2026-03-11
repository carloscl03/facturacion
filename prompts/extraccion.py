import json


def build_prompt_extractor(
    estado_actual: dict,
    ultima_pregunta_bot: str,
    mensaje: str,
    operacion: str | None = None,
) -> str:
    op_bloqueada = operacion in ("venta", "compra")

    regla_cambio_operacion = ""
    if op_bloqueada:
        opuesto = "compra" if operacion == "venta" else "venta"
        regla_cambio_operacion = f"""
    ### REGLA CRÍTICA — CAMBIO DE OPERACIÓN BLOQUEADO:
    El registro actual es "{operacion}". NO cambiarlo a "{opuesto}".
    - Si el usuario implica "{opuesto}" sin otros datos: pregunta si desea eliminar e iniciar de nuevo.
    - Si trae datos adicionales: extrae esos datos para el registro actual de {operacion}.
"""

    regla_sin_operacion = ""
    if not op_bloqueada:
        regla_sin_operacion = """
    ### REGLA CRÍTICA — SIN OPERACIÓN DEFINIDA:
    El registro aún no tiene operación. Debe fijarse primero.
    - Si el mensaje NO indica claramente venta o compra: NO extraigas otros datos. Pide que indique "venta" o "compra".
    - Si SÍ indica venta o compra: extrae operacion y cualquier otro dato que aporte.
"""

    estado_ctx = ""
    if estado_actual and isinstance(estado_actual, dict):
        campos = {
            k: v for k, v in estado_actual.items()
            if k not in ("id", "wa_id", "id_from", "created_at", "updated_at")
            and v is not None and v != "" and v != "null"
        }
        if campos:
            try:
                estado_str = json.dumps(campos, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                estado_str = "{}"
            estado_ctx = f"""
    ### DATOS ACTUALES EN REDIS:
    ```json
    {estado_str}
    ```
    """

    return f"""
    Eres el Agente Contable Experto de MaravIA. Tu misión es: (A) extraer datos contables del mensaje, (B) generar un resumen en lenguaje natural, y (C) diagnosticar qué datos faltan.
    {regla_cambio_operacion}
    {regla_sin_operacion}

    ### CONTEXTO — ÚLTIMA INTERACCIÓN:
    "{ultima_pregunta_bot or 'inicio'}"
    {estado_ctx}

    ### MENSAJE CON JSON (PRIORIDAD):
    Si el mensaje contiene un JSON (objeto o array), trátalo como documento con muchos datos.
    Presta especial atención a las etiquetas/claves del JSON para llenar la mayor cantidad de campos.
    Mapeo de claves del JSON a campos de propuesta_cache:
    - Entidad: "cliente", "razon_social", "proveedor" → entidad_nombre; "ruc", "dni", "documento" → entidad_numero.
    - Operación: "tipo_operacion", "cod_ope", "operacion" → operacion ("venta"/"compra").
    - Comprobante: "tipo_comprobante", "comprobante" → tipo_documento ("factura"/"boleta"/"nota de venta").
    - Número: "serie", "numero", "numero_documento" → numero_documento (ej: "F001-00005678").
    - Montos: "total", "monto_total" → monto_total; "subtotal", "base" → monto_sin_igv; "igv" → igv.
    - Productos: "productos", "items", "detalle" → productos (JSON array).
    - Moneda: "moneda" ("PEN"/"soles" → "PEN"; "USD"/"dolares" → "USD").
    - Fechas: "fecha_emision", "fecha_pago" → formato DD-MM-YYYY.
    - Banco: "banco", "caja_banco", "cuenta" → banco.
    Si el JSON tiene datos, combina con texto libre (JSON tiene prioridad).
    Tras procesar JSON, el diagnóstico lista solo lo que sigue faltando.

    ### REGLAS DE EXTRACCIÓN:
    - operacion: solo "venta" o "compra". Si no se indica, null.
    - tipo_documento: "factura", "boleta" o "nota de venta". No asumir si no se indica.
    - numero_documento: formato serie-número según SUNAT (ej: F001-00005678). Extraer si el usuario lo proporciona.
    - moneda: "PEN" o "USD". No asumir.
    - Fechas: formato DD-MM-YYYY siempre.
    - IGV 18% incluido en monto_total. Desglosar monto_sin_igv e igv.
    - entidad_numero: DNI tiene 8 dígitos, RUC tiene 11 dígitos. El tipo se infiere por la longitud.
    - banco: nombre de la entidad financiera si se menciona ("BCP", "BBVA", "Caja Chica").

    ### MENSAJE DE ENTENDIMIENTO (preámbulo):
    Frase corta que muestre que entendiste. Ej: "¡Dale! Ya anoté lo principal.", "Entendido, anoté 2 laptops por S/ 3000."
    Si el usuario solo indica compra o venta sin más datos: resumen_visual = 🛒 *COMPRA* o 📤 *VENTA* + "¿Es correcto?" NO listes faltantes.

    ### RESUMEN VISUAL — ESTADO COMPLETO DEL REGISTRO (no solo este mensaje):
    **resumen_visual** debe reflejar TODO lo que tiene el registro DESPUÉS de fusionar Redis + propuesta_cache: es la SÍNTESIS VISUAL COMPLETA del estado actual (comprobante, cliente/proveedor, productos, totales, moneda, banco, crédito/cuotas, etc.). No solo lo extraído en ESTE mensaje; incluye todos los datos ya guardados más lo nuevo. Una línea por campo con valor, según la estructura de ejemplo (📄 👤 📦 💰 💵 🏦 📅 🔄). Usa nombres legibles, sin IDs.

    ### DIAGNÓSTICO DE FALTANTES:
    **Estructura de la salida:** (1) Preámbulo (mensaje_entendimiento). (2) Síntesis visual = resumen_visual del ESTADO COMPLETO. (3) Invitación a completar en lenguaje natural (ej: "Me faltan algunos datos para completar:"). (4) **LISTADO de TODAS las preguntas** por cada campo que falte, enumeradas con 1️⃣ 2️⃣ 3️⃣ (una pregunta por línea). Incluye TODOS los campos faltantes, no solo uno.
    Fusiona datos en Redis + propuesta_cache. Genera UNA pregunta por cada campo vacío.
    **Cuando aún falten datos: NUNCA pidas confirmación de registro.** Solo lista las preguntas; el usuario responderá con datos y el sistema actualizará de nuevo. **Confirmación de registro** solo cuando listo_para_finalizar es true (no uses "finalizar"; el clasificador envía finalizar a otro agente).
    **NO preguntar por:** sucursal, forma de pago, medio de pago (se gestionan en Estado 2 / opciones).

    Campos a incluir en el listado de preguntas (si faltan):
    1. Monto/Detalle: si monto_total = 0 y productos vacío.
    2. Cliente (venta) o Proveedor (compra): si no hay entidad_nombre ni entidad_id.
    3. RUC/DNI de la entidad: si hay entidad_nombre pero no entidad_numero (obligatorio para factura).
    4. Tipo de documento: si tipo_documento es null.
    5. Moneda: si moneda es null.
    6. Banco: si no hay banco definido.
    7. Cuotas / días (si es crédito y se mencionó pero no hay valor).

    **listo_para_finalizar:** true solo si están completos: (1) monto/detalle, (2) entidad (nombre + número si factura), (3) tipo_documento, (4) moneda. false si falta alguno.
    **Confirmación de registro:** se pide SOLO cuando no quede ninguna pregunta (listo_para_finalizar = true). Mientras falte algún dato, nunca pidas confirmación; solo lista las preguntas.

    ### IDENTIFICACIÓN:
    - activo: true si el mensaje contiene RUC (11 dígitos), DNI (8 dígitos) o nombre/razón social buscable.
    - termino: texto a buscar. Vacío si activo = false.
    - tipo_ope: "venta" o "compra" según contexto.

    ### ultima_pregunta_keyword:
    Genera una keyword combo que indique el campo principal que se preguntó o el estado:
    - "operacion_pendiente" si se preguntó tipo de operación
    - "entidad_pendiente" si se preguntó por cliente/proveedor
    - "documento_pendiente" si se preguntó tipo de documento
    - "moneda_pendiente" si se preguntó moneda
    - "monto_pendiente" si se preguntó monto/productos
    - "banco_pendiente" si se preguntó banco
    - "datos_confirmados" si se mostraron datos, pendiente confirmación
    - "completo" si todos los campos Estado 1 están llenos

    ### MENSAJE DEL USUARIO:
    "{mensaje}"

    ### FORMATO DE RESPUESTA JSON:
    {{
        "propuesta_cache": {{
            "operacion": "venta o compra o null",
            "entidad_nombre": "...",
            "entidad_numero": "DNI 8 dig o RUC 11 dig o null",
            "tipo_documento": "factura/boleta/nota de venta o null",
            "numero_documento": "F001-00005678 o null",
            "moneda": "PEN o USD o null",
            "monto_total": float,
            "monto_sin_igv": float,
            "igv": float,
            "banco": "nombre banco o null",
            "productos": [{{ "nombre": str, "cantidad": float, "precio": float }}],
            "fecha_emision": "DD-MM-YYYY o null",
            "fecha_pago": "DD-MM-YYYY o null"
        }},
        "mensaje_entendimiento": "Preámbulo corto (ej: ¡Dale! Ya anoté lo principal.).",
        "resumen_visual": "SÍNTESIS VISUAL DEL ESTADO COMPLETO del registro (Redis + propuesta fusionados): todas las líneas con datos (📄 👤 📦 💰 etc.), no solo lo del mensaje actual.",
        "diagnostico": "Invitación (ej: Me faltan algunos datos para completar:) + LISTADO de TODAS las preguntas por campo faltante, enumeradas 1️⃣ 2️⃣ 3️⃣ (una por línea). Si listo_para_finalizar: solo entonces invitación a confirmar registro (no finalizar). Si faltan datos, no pidas confirmación.",
        "listo_para_finalizar": false,
        "ultima_pregunta_keyword": "campo_estado",
        "requiere_identificacion": {{
            "activo": false,
            "termino": "",
            "tipo_ope": "venta o compra",
            "mensaje": ""
        }}
    }}
    """
