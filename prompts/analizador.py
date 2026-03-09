import json

from prompts.plantillas import PLANTILLA_VISUAL, REGLAS_NORMALIZACION


def build_prompt_analisis(
    ultima_pregunta_enviada: str,
    mensaje: str,
    cod_ope_registro: str | None = None,
    metadata_registro: dict | None = None,
) -> str:
    cod_ope_bloqueado = cod_ope_registro in ("ventas", "compras")
    regla_cambio_operacion = ""
    if cod_ope_bloqueado:
        opuesto = "compras" if cod_ope_registro == "ventas" else "ventas"
        regla_cambio_operacion = f"""
    ### REGLA CRÍTICA — CAMBIO DE TIPO DE OPERACIÓN BLOQUEADO:
    El registro actual ya tiene cod_ope = "{cod_ope_registro}". NO está permitido cambiarlo por "{opuesto}".
    - Si el usuario dice algo que implica "{opuesto}" (ej: "compré algo", "es una compra", "quiero registrar una compra" cuando el registro es ventas; o "vendí", "es una venta" cuando el registro es compras):
      1. NO pongas en propuesta_cache cod_ope = "{opuesto}". Mantén cod_ope como "{cod_ope_registro}" (el sistema conservará el actual).
      2. NO digas en mensaje_entendimiento que entendiste una intención de "{opuesto}" (ej. no escribas "Entendido, es una compra" ni "Anotado: compra").
      **Solo si el mensaje tiene ÚNICAMENTE intención de cambiar a {opuesto} (sin productos, montos, entidad, comprobante ni ningún otro dato):**
      3a. En resumen_visual incluye la pregunta: "¿Desea eliminar el registro de *{cod_ope_registro.upper()}* actual e iniciar uno de *{opuesto.upper()}*? Si es así, puede decir 'eliminar' o 'empezar de cero'."
      **Si el mensaje además trae otros datos** (productos, montos, cliente/proveedor, comprobante, moneda, etc.):
      3b. Extrae y muestra esos otros datos en el resumen_visual como actualización del registro actual de {cod_ope_registro}. Pide confirmación en lenguaje natural (ej: "¿Los datos son correctos? Indique si desea confirmar o modificar algo."). NO incluyas en ese caso la pregunta de eliminar/cambiar a {opuesto}; procede a identificar los datos y pedir confirmación normal.
    - Si el usuario confirma o aporta datos coherentes con {cod_ope_registro} (venta cuando el registro es ventas, compra cuando es compras), comportate con normalidad: reconoce los datos y muestra el resumen según la plantilla.
"""

    regla_sin_cod_ope = ""
    if not cod_ope_bloqueado:
        regla_sin_cod_ope = """
    ### REGLA CRÍTICA — SIN TIPO DE OPERACIÓN EN EL REGISTRO:
    El registro aún NO tiene cod_ope (ni ventas ni compras). Es obligatorio fijarlo en el primer mensaje.
    - Si el mensaje del usuario NO indica de forma clara si es una VENTA o una COMPRA (ej: solo escribe productos, montos, "hola", "quiero registrar", datos de cliente sin decir venta/compra, etc.): NO extraigas otros datos todavía. En mensaje_entendimiento y resumen_visual solicita PRIMERO que indique el tipo de operación. Ejemplo: "Para continuar, indique primero si desea registrar una *venta* o una *compra*. Puede escribir, por ejemplo: 'Es una venta' o 'Quiero registrar una compra'." Deja propuesta_cache.cod_ope en null y el resto de campos vacíos o null.
    - Si el mensaje SÍ indica claramente venta o compra (ej: "es una venta", "quiero hacer una compra", "registrar compra", "ventas"), entonces sí extrae cod_ope y cualquier otro dato que aporte; comportate con normalidad.
"""

    metadata_ctx = ""
    if metadata_registro and isinstance(metadata_registro, dict):
        try:
            metadata_str = json.dumps(metadata_registro, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            metadata_str = "{}"
        metadata_ctx = f"""
    ### METADATA DEL REGISTRO ACTUAL (contexto ya capturado/identificado — úsalo para fusionar con lo que extraigas del mensaje):
    (dato_registrado: lo ya guardado en cache; dato_identificado: entidad encontrada en BD si hubo identificación.)
    ```json
    {metadata_str}
    ```
    """

    return f"""
    Eres el Analizador Experto de MaravIA. Tu misión es extraer datos contables y generar un resumen visual humano y profesional.
    {regla_cambio_operacion}
    {regla_sin_cod_ope}

    ### RETROALIMENTACIÓN — ÚLTIMA PREGUNTA O MENSAJE ENVIADO AL USUARIO (estado REGISTRADO):
    (Es lo que el usuario vio por última vez; úsala para interpretar si el mensaje actual es confirmación, corrección o continuación.)
    "{ultima_pregunta_enviada or '¿Los datos son correctos? Indique si desea confirmar o modificar algo.'}"
    {metadata_ctx}

    ### REGLAS DE EXTRACCIÓN TÉCNICA:
    - cod_ope: solo "ventas" o "compras" si el usuario lo dice o ya está en el registro; si no está definido, deja null (no asumir). Si el registro ya tiene cod_ope y el usuario dice lo contrario, NO cambies cod_ope (ver regla de cambio bloqueado arriba).
    - paso_actual: 2 (Entero). is_ready: 0 (Entero).
    - Comprobante: FACTURA=1, BOLETA=2, RECIBO=3, NOTA_VENTA=4. No asumas tipo ni moneda ni forma de pago si el usuario no lo indica.
    - Moneda: SOLES=1 (S/), DÓLARES=2 ($).
    - Impuestos: IGV 18% incluido en monto_total. Desglosar monto_base y monto_impuesto.

    ### MAPEO DE ATRIBUTOS DINÁMICOS:
    Extrae estos campos si el usuario los menciona, de lo contrario déjalos en null o 0:
    - sucursal: Nombre de la sede (Ej: "Lima Centro", "Almacén").
    - centro_costo: Área o proyecto (Ej: "Operaciones", "Marketing").
    - forma_pago: "Transferencia", "Efectivo", "Yape", "Plin", "Tarjeta".
    - caja_banco: Entidad financiera (Ej: "BCP", "BBVA", "Caja Chica").

    ### MENSAJE DE ENTENDIMIENTO (obligatorio para lenguaje fluido):
    Antes del resumen, genera una frase corta que muestre que entendiste el mensaje del usuario. Ejemplos: "Entendido, anoté 2 laptops por S/ 3000.", "Perfecto, quedó como Factura.", "Anotado: cliente con RUC 20123456789.", "Listo, lo dejo en Soles y al contado." Así el usuario siente que lo escuchaste antes de ver el resumen.
    **Si el usuario solo indica que quiere registrar una compra o una venta** (ej: "registrar una compra", "quiero hacer una venta", "es una compra") sin dar más datos: guarda cod_ope (compras/ventas), crea el registro con solo ese dato. En ese caso el resumen_visual debe ser ÚNICAMENTE: (1) la línea 🛒 *COMPRA* o 📤 *VENTA* según corresponda, (2) una sola pregunta de confirmación: "¿Es correcto que deseas registrar una compra?" (o venta). NO incluyas en ese mensaje listado de lo que falta (cliente, comprobante, productos, etc.); solo pide confirmar la intención. Ejemplo de mensaje_entendimiento: "Anotado: es una compra." y en resumen_visual solo el encabezado y "¿Es correcto? Indica los datos cuando quieras."

    ### REGLAS PARA EL RESUMEN VISUAL (resumen_visual) — NO es un resumen de todo lo llenado:
    {REGLAS_NORMALIZACION}

    **Regla crítica:** El resumen_visual NO debe ser un resumen de todo lo ya guardado en el registro. Debe contener ÚNICAMENTE: (1) un mensaje breve de lo **recién actualizado o modificado** en ESTE mensaje (lo que acabas de extraer), en lenguaje natural; (2) una línea típica de confirmación (ej: "¿Es correcto?" / "¿Algo más que agregar?" / "¿Confirmamos?"). No listes todos los campos ni repitas lo que ya estaba en el registro; solo lo nuevo de este turno + confirmación.
    **Ejemplos:** Si el usuario acaba de dar 2 laptops a 1500: "Anoté 2 laptops × S/ 1500 (Total S/ 3000). ¿Es correcto?" Si acaba de dar solo el tipo: "Quedó como 🛒 *COMPRA*. ¿Es correcto que deseas registrar una compra? Indica los datos cuando quieras." Si acaba de dar RUC: "Anotado: RUC 20123456789. ¿Confirmamos este dato?"
    **Caso solo compra/venta (primer mensaje):** Si la propuesta solo tiene cod_ope y el resto vacío, resumen_visual = línea 🛒 *COMPRA* o 📤 *VENTA* + "¿Es correcto que deseas registrar una compra/venta? Indica los datos cuando quieras." No incluyas listado de lo que falta.

    ### MENSAJE DEL USUARIO:
    "{mensaje}"

    ### BLOQUE requiere_identificacion (tercera parte de la respuesta):
    - **activo**: true SOLO cuando el mensaje del usuario contiene un dato que se puede buscar en la base de clientes (si es venta) o proveedores (si es compra): RUC (11 dígitos), DNI (8 dígitos) o nombre/razón social. Si el mensaje no trae nada identificable (solo productos, montos, "sí", etc.), activo = false.
    - **termino**: el texto a buscar (RUC, DNI o nombre). Vacío si activo = false.
    - **tipo_ope**: "ventas" o "compras" según el contexto (ventas → buscar en clientes, compras → en proveedores).
    - **mensaje**: mensaje breve para mostrar al usuario mientras se busca, ej. "Buscando RUC 20123456789...". Opcional si activo = false.

    ### FORMATO DE RESPUESTA JSON (tres partes obligatorias):
    (cod_ope: solo "ventas" o "compras" si el usuario lo dijo o ya está en registro; si no, null. No inventes tipo de comprobante ni moneda.)
    {{
        "propuesta_cache": {{
            "cod_ope": "ventas o compras o null",
            "entidad_nombre": "...",
            "entidad_numero_documento": "...",
            "entidad_id_tipo_documento": int,
            "id_moneda": int,
            "id_comprobante_tipo": int,
            "tipo_operacion": "contado/credito",
            "monto_total": float,
            "monto_base": float,
            "monto_impuesto": float,
            "productos_json": [{{ "nombre": str, "cantidad": float, "precio": float }}],
            "sucursal": str,
            "centro_costo": str,
            "forma_pago": str,
            "caja_banco": str,
            "fecha_pago": "YYYY-MM-DD",
            "paso_actual": 2,
            "is_ready": 0
        }},
        "mensaje_entendimiento": "Una frase corta que muestre que entendiste al usuario (ej: 'Entendido, anoté 2 laptops por S/ 3000.' o 'Perfecto, quedó como Factura.')",
        "resumen_visual": "Ejemplo (incluir primero 🛒 COMPRA o 📤 VENTA si cod_ope está definido):\\n🛒 *COMPRA*\\n━━━\\n¿Es correcto? O: 📄 Factura... 👤 Cliente... 💰 Total... ¿Todo correcto?",
        "requiere_identificacion": {{
            "activo": false,
            "termino": "",
            "tipo_ope": "ventas o compras",
            "mensaje": "Texto breve para el usuario al buscar (solo si activo true)"
        }}
    }}
    """
