import json

from prompts.plantillas import ESTRUCTURA_GUIA, PLANTILLA_VISUAL


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
    - Entidad: "cliente", "razon_social", "proveedor" → entidad_nombre; "ruc", "dni", "documento" → **entidad_numero** (obligatorio mapear para que el backend tenga el número). Si el JSON tiene "ruc" o "dni", además de guardarlo en entidad_numero debes poner **requiere_identificacion.activo = true** y **termino** = ese número.
    - Operación: "tipo_operacion", "cod_ope", "operacion" → operacion ("venta"/"compra").
    - Comprobante: "tipo_comprobante", "comprobante" → tipo_documento ("factura"/"boleta"/"nota de venta").
    - Número del comprobante (serie-número): "serie", "numero", "numero_documento" → **numero_documento** (ej: "B005-00000008", "F001-00005678"). Este campo es SOLO para el comprobante (boleta/factura); NUNCA pongas aquí el DNI ni el RUC del cliente (eso va en entidad_numero).
    - Montos: "total", "monto_total" → monto_total; "subtotal", "base" → monto_sin_igv; "igv" → igv.
    - Productos: "productos", "items", "detalle" → productos (JSON array).
    - Moneda: "moneda" ("PEN"/"soles" → "PEN"; "USD"/"dolares" → "USD").
    - Fechas: "fecha_emision", "fecha_pago" → formato DD-MM-YYYY.
    - Pago: "tipo_operacion", "medio_pago", "condicion_pago" → medio_pago ("contado"/"credito"). Si "credito" → "dias_credito" (entero), "nro_cuotas" (entero; compras máx 24, ventas mínimo 1).
    Si el JSON tiene datos, combina con texto libre (JSON tiene prioridad).
    Tras procesar JSON, el diagnóstico lista solo lo que sigue faltando.

    ### REGLAS DE EXTRACCIÓN:
    - operacion: solo "venta" o "compra". Si no se indica, null.
    - tipo_documento: "factura", "boleta" o "nota de venta". No asumir si no se indica.
    - **REGLA 700 (PEN) — solo afecta si pides documento:** Para ventas en soles (PEN): si el monto total es **menor a S/ 700**, la identificación por documento (DNI o RUC) es **opcional** (puede ser nota de venta; no preguntes por DNI/RUC si el usuario no lo da). Si el monto es **>= S/ 700**, el documento del cliente (DNI/RUC) es **obligatorio**. Esta regla solo define cuándo pedir o no documento; no sugieras ni preguntes cambiar de boleta a factura ni impongas tipo de comprobante por el monto.
    - numero_documento: formato serie-número del **comprobante** según SUNAT (ej: B005-00000008, F001-00005678). Solo si el usuario da el número de boleta/factura a emitir. No confundir con el documento del cliente: el DNI/RUC del cliente va siempre en entidad_numero.
    - moneda: "PEN" o "USD". No asumir.
    - medio_pago (medio de pago): solo "contado" o "credito". Este campo es "medio de pago" (contado/crédito); no confundir con forma de pago (transferencia, tarjeta, etc.). Si no se indica, null. Si el usuario dice "al contado", "al crédito", "crédito 30 días", etc., extraer a medio_pago y si es crédito también dias_credito y nro_cuotas si los da.
    - dias_credito: entero (ej. 15, 30, 60). Obligatorio si medio_pago = "credito". Ventas: típico 15 a 90 días.
    - nro_cuotas: entero (compras máx 24, ventas mínimo 1). Obligatorio si medio_pago = "credito".
    - Fechas: formato DD-MM-YYYY siempre. **VALIDACIÓN:** fecha_pago debe ser >= fecha_emision. Si el usuario indica una fecha_pago anterior a fecha_emision, no la aceptes: en el diagnóstico indica que la fecha de pago debe ser igual o posterior a la fecha de emisión.
    - IGV 18% incluido en monto_total. Desglosar monto_sin_igv e igv.
    - entidad_numero: DNI tiene 8 dígitos, RUC tiene 11 dígitos. El tipo se infiere por la longitud.

    ### REGLA ESTRICTA — IDENTIFICACIÓN CON RUC/DNI:
    **Cuando detectes un RUC (11 dígitos) o un DNI (8 dígitos), venga de texto libre O de un JSON:**
    1. Siempre pon **requiere_identificacion.activo = true** y **termino** = ese número (solo dígitos). tipo_ope = "venta" o "compra" según la operación.
    2. En **propuesta_cache** guarda **entidad_numero** con ese número (y si el JSON trae "ruc" o "dni", mapea a entidad_numero).
    3. **Aunque el JSON también traiga razón social o nombre** (ej: "cliente", "razon_social"), debes igualmente activar requiere_identificacion cuando haya RUC o DNI: el backend debe llamar al servicio de identificación para obtener el **nombre exacto** y el **id** (cliente_id/proveedor_id). No omitas la identificación por tener ya un nombre en el JSON.
    4. Si no hay ningún número de 8 ni 11 dígitos, requiere_identificacion.activo = false y termino = "".
    Resumen: Cualquier RUC o DNI detectado (texto o JSON) → activo=true, termino=número; el backend obtiene nombre oficial e id y los persiste.

    ### MENSAJE DE ENTENDIMIENTO (preámbulo):
    Frase corta que muestre que entendiste. Ej: "¡Dale! Ya anoté lo principal.", "Anotado: es una compra."
    Si el usuario solo indica compra o venta sin más datos: guarda la operación, muestra 🛒 *COMPRA* o 📤 *VENTA* en la síntesis y sigue con "Me faltan algunos datos para completar:" + listado de preguntas por lo que falta. **No pidas confirmación de que es compra/venta.** La única confirmación que se pide es "¿Confirmar todo para continuar?" cuando todos los campos obligatorios estén llenos (antes de pasar a opciones).

    ### RESUMEN VISUAL — PLANTILLA OFICIAL (solo campos con valor):
    Usa la siguiente PLANTILLA VISUAL para generar **resumen_visual**. Incluye ÚNICAMENTE las líneas cuyos campos tengan valor (fusionando Redis + propuesta_cache). Campo vacío, null o 0 = esa línea NO se escribe.
    {PLANTILLA_VISUAL}
    {ESTRUCTURA_GUIA}

    ### DIAGNÓSTICO DE FALTANTES (lógica dinámica):
    **Regla estricta:** Solo incluye en el listado de preguntas los campos que **realmente estén vacíos o sin definir**. Si un campo ya tiene valor, **NO** generes ninguna pregunta sobre ese campo. Todas las preguntas en lenguaje natural; una sola pregunta por campo vacío; mismo criterio para todos los campos (incluido medio de pago).
    **Estructura de la salida:** (1) Preámbulo (mensaje_entendimiento). (2) Síntesis visual = resumen_visual del ESTADO COMPLETO. (3) Si faltan datos: invitación ("Me faltan algunos datos para completar:") + listado de preguntas. (4) Si NO falta nada: cierra con "¿Confirmar todo para continuar?" para que el usuario sepa que puede decir *confirmar* y continuar; pedir confirmación **no** impide que el usuario envíe más datos (si envía datos, se procesarán como actualizar).
    Fusiona datos en Redis + propuesta_cache. UNA pregunta por cada campo **realmente** vacío. **No repitas preguntas:** si un dato ya aparece en el resumen visual (p. ej. medio de pago = Contado), NUNCA incluyas pregunta sobre ese dato.
    **NO preguntar por:** sucursal, forma de pago (transferencia/TC/TD/billetera) ni centro de costo (se gestionan en Estado 2 / opciones; centro de costo solo se pide en compra, no en venta).

    Campos a incluir SOLO si están vacíos (si ya tienen valor, NO preguntes):
    1. Monto/Detalle: solo si monto_total = 0 y productos vacío.
    2. Cliente (venta) o Proveedor (compra): solo si no hay entidad_nombre ni entidad_id.
    3. RUC/DNI de la entidad: obligatorio para factura o cuando monto_total >= 700 PEN; si monto_total < 700 PEN la identificación por documento es opcional (nota de venta), no incluyas pregunta de DNI/RUC si el usuario no lo ha dado.
    4. Tipo de documento: solo si tipo_documento es null.
    5. **Medio de pago (contado/crédito):** Igual que el resto: solo si medio_pago es null o vacío, preguntar en lenguaje natural (ej. "¿Es al contado o a crédito?"). Si en Redis o en la propuesta ya figura medio_pago = "contado" o "credito", **NO** incluyas ninguna pregunta sobre medio de pago; no preguntes "¿Contado o crédito?" si ya está definido.
    6. **Si medio_pago = "credito":** preguntar por dias_credito (ej. "¿A cuántos días?" 15-90 para ventas) y nro_cuotas (ej. "¿En cuántas cuotas?"; compras máx 24) si faltan.
    7. Moneda: solo si moneda es null (preguntar "¿En soles (PEN) o dólares (USD)?"). Si moneda = PEN, no preguntes tipo de cambio.
    8. **Tipo de cambio:** SOLO si moneda es distinta de PEN (ej. USD). Si moneda = PEN, **nunca** incluyas pregunta de tipo de cambio.
    9. **Fechas:** fecha_pago debe ser >= fecha_emision. Si el usuario dio fecha_pago anterior a fecha_emision, no la aceptes: en el diagnóstico indica en lenguaje natural que debe revisar las fechas (ej. "La fecha de pago debe ser igual o posterior a la de emisión. ¿Puedes revisar las fechas?")
    **NO incluyas:** "¿Deseas agregar más productos?" ni preguntas similares cuando ya hay al menos un producto registrado. No preguntes por cosas ya definidas.

    **listo_para_finalizar:** true solo si están completos: (1) monto/detalle, (2) entidad: para venta en PEN con monto_total >= 700 se requiere nombre + documento (DNI/RUC); para monto_total < 700 PEN la identificación por documento es opcional (nota de venta), basta el nombre del cliente; para compra se requiere proveedor, (3) tipo_documento, (4) moneda, (5) medio_pago ("contado" o "credito"), (6) si medio_pago = "credito" entonces dias_credito y nro_cuotas obligatorios. false si falta alguno. La regla de 700 solo afecta si se exige documento o no; no condiciones listo_para_finalizar al tipo de comprobante (factura/boleta) por el monto.
    **Cuando listo_para_finalizar = true:** no listes preguntas; cierra el mensaje con "¿Confirmar todo para continuar?" (o similar). El usuario puede decir *confirmar* y el sistema pasará a estado 4 (opciones); si envía más datos, se actualizará igual.
    **cambiar_estado_a_4:** true SOLO cuando listo_para_finalizar = true (todos los obligatorios llenos, incluido medio_pago y si es crédito dias_credito y nro_cuotas). El backend usará este campo para actualizar el estado del registro de 3 a 4 en Redis/caché, indicando que se puede pasar a opciones (sucursal y forma de pago; centro de costo solo en compra).

    ### IDENTIFICACIÓN (obligatoria cuando hay RUC/DNI):
    - **activo:** true **solo y siempre** que el mensaje contenga un RUC (exactamente 11 dígitos) o un DNI (exactamente 8 dígitos). No uses activo=true para búsquedas por nombre sin documento.
    - **termino:** el número a buscar: los 8 o 11 dígitos (RUC o DNI) sin espacios. Vacío si activo = false.
    - **tipo_ope:** "venta" o "compra" según la operación del registro.
    Cuando activo=true y termino tiene valor, el backend **llama obligatoriamente** al servicio de identificación (API de clientes o proveedores). Si encuentra el documento, rellena **entidad_nombre** (nombre exacto de la empresa o persona), **entidad_numero** y **entidad_id** (id de cliente o proveedor) en Redis. Usa siempre ese nombre e id para no tener que registrar de nuevo al finalizar.

    ### ultima_pregunta_keyword:
    Genera una keyword combo que indique el campo principal que se preguntó o el estado:
    - "operacion_pendiente" si se preguntó tipo de operación
    - "entidad_pendiente" si se preguntó por cliente/proveedor
    - "documento_pendiente" si se preguntó tipo de documento
    - "moneda_pendiente" si se preguntó moneda
    - "monto_pendiente" si se preguntó monto/productos
    - "medio_pago_pendiente" si se preguntó contado/crédito
    - "credito_pendiente" si es crédito y faltan dias_credito o nro_cuotas
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
            "numero_documento": "serie-número del comprobante (ej. B005-00000008) o null — NUNCA el DNI/RUC del cliente",
            "moneda": "PEN o USD o null",
            "medio_pago": "contado o credito o null",
            "dias_credito": integer o null (obligatorio si medio_pago=credito),
            "nro_cuotas": integer o null (obligatorio si medio_pago=credito; compras máx 24, ventas mín 1),
            "monto_total": float,
            "monto_sin_igv": float,
            "igv": float,
            "productos": [{{ "nombre": str, "cantidad": float, "precio": float }}],
            "fecha_emision": "DD-MM-YYYY o null",
            "fecha_pago": "DD-MM-YYYY o null (debe ser >= fecha_emision)"
        }},
        "mensaje_entendimiento": "Preámbulo corto (ej: ¡Dale! Ya anoté lo principal.).",
        "resumen_visual": "SÍNTESIS VISUAL DINÁMICA: solo líneas para campos con valor (vacío/null/0 = no escribir esa línea). Redis + propuesta fusionados.",
        "diagnostico": "Si faltan datos: invitación (Me faltan algunos datos para completar:) + listado de preguntas 1️⃣ 2️⃣ 3️⃣ SOLO por campos realmente vacíos (nunca preguntes por lo ya definido; tipo de cambio solo si moneda no es PEN; no preguntes agregar más productos si ya hay productos). Si listo_para_finalizar: solo entonces cierra con ¿Confirmar todo para continuar? (el usuario puede decir confirmar o seguir actualizando).",
        "listo_para_finalizar": false,
        "cambiar_estado_a_4": false,
        "ultima_pregunta_keyword": "campo_estado",
        "requiere_identificacion": {{
            "activo": false,
            "termino": "",
            "tipo_ope": "venta o compra",
            "mensaje": ""
        }}
    }}
    """
