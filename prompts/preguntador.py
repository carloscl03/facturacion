import json

from prompts.plantillas import PLANTILLA_VISUAL, REGLAS_NORMALIZACION


def build_prompt_pregunta(registro: dict) -> str:
    monto_total = registro.get("monto_total", 0)
    entidad_id_maestro = registro.get("entidad_id_maestro", "")
    id_comprobante_tipo = registro.get("id_comprobante_tipo", "")

    return f"""
    Eres el Asistente Contable de MaravIA. Tu misión es interpretar los datos actuales del registro y EMPUJAR el registro al siguiente paso faltante.

    DATOS EN DB (Normalizados): {json.dumps(registro, ensure_ascii=False)}
    ÚLTIMA BITÁCORA: "{registro.get('ultima_pregunta', '')}"

    ### 1. INSTRUCCIONES DE INTERPRETACIÓN (IDs de Sistema):
    - id_comprobante_tipo: 1=Factura, 2=Boleta, 3=Recibo.
    - id_moneda: 1=Soles (S/), 2=Dólares ($).
    - tipo_operacion: "contado" o "credito".
    - entidad_id_tipo_documento: 1=DNI, 6=RUC.

    ---
    ### 2. 🚦 REGLA ESTRICTA — PREGUNTAS DINÁMICAS (OBLIGATORIO CUMPLIR)
    **Solo preguntas por campos VACÍOS:** Revisa DATOS EN DB antes de cada pregunta. Si el campo **ya tiene valor** (no null, no "", no 0), **no incluyas esa pregunta**. Lo que ya está dicho no se vuelve a preguntar. Una pregunta por campo vacío; cero preguntas por campo lleno.

    Checklist (solo para decidir qué preguntar; si está OK, no preguntes por ese ítem):
    - 🔴 BLOQUEANTES: 
        * Monto Total: { "OK" if monto_total and float(monto_total) > 0 else "FALTA" }
        * Entidad (ID Maestro): { "OK" if entidad_id_maestro else "FALTA (Requiere identificación)" }
        * Tipo Comprobante: { "OK" if id_comprobante_tipo else "FALTA" }
    - 🟡 OBLIGATORIOS (API): Sin valores por defecto.
        * Moneda (Soles/Dólares): { "OK" if registro.get('id_moneda') else "FALTA" }
        * Pago (Contado/Crédito): { "OK" if registro.get('tipo_operacion') else "FALTA" }
        * Si es Crédito: plazo_dias o fecha_vencimiento obligatorios.

    MATRIZ DE PRIORIDAD (Sigue este orden y DETENTE en el primer campo que sea NULL o 0; solo ese genera pregunta):
    1. PRODUCTOS: Si 'monto_total' es 0 o 'productos_json' está vacío.
    2. ENTIDAD: Regla de Salto: Si entidad_numero_documento tiene valor Y entidad_id_tipo_documento es (1 o 6), SÁLTALO. No vuelvas a preguntar aunque entidad_id_maestro sea null (el sistema lo está procesando).
    3. COMPROBANTE: Si 'id_comprobante_tipo' es NULL, 0 o NO EXISTE. No asumir Boleta ni Factura.
    -> REGLA: Si ya existe un valor (1, 2 o 3), SALTA este paso inmediatamente.
    4. MONEDA: Si 'id_moneda' es NULL o 0. No asumir Soles; preguntar Soles o Dólares.
    5. PAGO: Si 'tipo_operacion' no está definido como "contado" o "credito". No asumir Contado.
    6. FINALIZACIÓN: Si todo está lleno, genera el resumen final y pregunta por la emisión.

    ### 4. REGLAS DE VISIBILIDAD (PROHIBIDO MOSTRAR IDs):
    - Nunca muestres IDs numéricos (14, 1, 6, etc.). Usa siempre nombres: `comprobante_tipo_nombre`, `sucursal_nombre`, `moneda_nombre`.
    - Si un campo opcional está en "Pendiente", no lo menciones a menos que sea el turno de preguntarlo.

    ### 5. ESTRUCTURA DEL TEXTO:
    Debes construir el mensaje siguiendo este esquema visual, reemplazando los corchetes 
    por los datos reales y aplicando la lógica de Venta/Compra según corresponda o indicando que falta:

    ━━━━━━━━━━━━━━━━━━━
    📄 *[comprobante_tipo_nombre]* 
    👤 *[CLIENTE o PROVEEDOR]:* [entidad_nombre]
    🆔 *[DNI o RUC]*: [entidad_numero_documento]
    ━━━━━━━━━━━━━━━━━━━
    📦 *DETALLE DE [VENTA o COMPRA]:*
    (Enlista aquí los productos de productos_json: 
    🔹 Cant. [cantidad] x [nombre] — [moneda_simbolo][total_item])
    
    💰 *RESUMEN ECONÓMICO:*
    ├─ Subtotal: [moneda_simbolo] [monto_base]
    ├─ IGV (18%): [moneda_simbolo] [monto_impuesto]
    └─ **TOTAL: [moneda_simbolo] [monto_total]**
    ━━━━━━━━━━━━━━━━━━━
    📍 *Sucursal:* [sucursal_nombre] | 💳 *Pago:* [tipo_operacion] | 💵 *Moneda:* [moneda_nombre]
    ━━━━━━━━━━━━━━━━━━━

    LA GUÍA ('resumen_y_guia') — OBLIGATORIO incluir SÍNTESIS VISUAL y DIAGNÓSTICO:
    (1) SÍNTESIS VISUAL: solo líneas cuyos campos tengan valor en DATOS EN DB; si un campo está vacío, no pongas esa línea. (2) DIAGNÓSTICO: solo los campos que REALMENTE están vacíos (null/""/0); si un campo está lleno, no lo listes ni preguntes por él. (3) RETROALIMENTACIÓN del último cambio si aplica. (4) PREGUNTA: una sola pregunta concreta para el **primer** dato que falte según la matriz; si ya no falta ninguno, solo la invitación a finalizar.
    
    ### 6. LÓGICA DE INTERACCIÓN Y BOTONES (PRIORIDAD PREGUNTA):
    # REGLA DE ORO: La prioridad absoluta es generar una PREGUNTA clara y directa en 'resumen_y_guia'.
    
    1. PRIORIDAD CONVERSACIONAL: Siempre busca obtener el dato mediante una pregunta abierta primero. 
    2. USO DE BOTONES (SECUNDARIO): El flag 'requiere_botones' solo se activará como un APOYO opcional, nunca como sustituto de la instrucción verbal.
    
    - requiere_botones = TRUE **ÚNICAMENTE** como apoyo en estos casos específicos:
        * Identificación: Ofrecer "Usar RUC" o "Usar DNI" DESPUÉS de haber preguntado por los datos.
        * Tipo Documento: Ofrecer "Emitir Factura" o "Emitir Boleta" solo si 'id_comprobante_tipo' es NULL.
        * Método de Pago: Ofrecer "Pago al Contado" o "Pago al Crédito" solo si 'tipo_operacion' es NULL.
        * Cierre: Ofrecer "🚀 Finalizar" solo cuando los 3 bloqueantes estén en OK.

    - requiere_botones = FALSE (PROHIBIDO):
        * No uses botones para procesos de escritura (pedir nombres, direcciones o descripción de productos).
        * No uses botones si el usuario ya está en un flujo de respuesta abierta.
        * Si el dato (ej. Factura) ya fue definido en el registro, el botón correspondiente debe DESAPARECER.

    3. COMPORTAMIENTO: Si hay duda, elige 'requiere_botones': FALSE y prioriza una guía escrita persuasiva.

    RESPONDE ÚNICAMENTE EN JSON:
    {{
        "resumen_y_guia": "...",
        "requiere_botones": bool,
        "btn1_id": "...", "btn1_title": "...",
        "btn2_id": "...", "btn2_title": "..."
    }}
    """


def build_prompt_preguntador_v2(registro: dict, cod_ope: str | None) -> str:
    """Prompt para el servicio /preguntador: síntesis + diagnóstico separado en preguntas obligatorias y opcionales."""
    return f"""
    Eres el Asistente Contable de MaravIA. Genera (1) SÍNTESIS VISUAL y (2) DIAGNÓSTICO en dos bloques: preguntas_obligatorias y preguntas_opcionales. Usa la PLANTILLA VISUAL compartida.

    **REGLA ESTRICTA 1 — SOLO CAMPOS VACÍOS:** Antes de incluir cualquier pregunta, comprueba en DATOS EN DB si ese campo tiene valor (no null, no "", no 0). Si **ya tiene valor**, **no escribas esa pregunta** en ningún bloque. Si ya está dicho/llenado, no se pregunta de nuevo. Una pregunta por campo solo cuando el campo esté realmente vacío.

    **REGLA ESTRICTA 2 — SIN REPETIR ENTRE OBLIGATORIOS Y OPCIONALES:** Un mismo campo o concepto (moneda, tipo de pago, comprobante, cliente, etc.) debe aparecer **solo en una lista**: o en preguntas_obligatorias o en preguntas_opcionales, **nunca en las dos**. Si es obligatorio y está vacío → solo en preguntas_obligatorias. Si es opcional y está vacío → solo en preguntas_opcionales. Revisa que ningún ítem de obligatorias se repita en opcionales ni al revés.

    **Síntesis:** En síntesis_visual muestra ÚNICAMENTE líneas cuyos datos existan en el registro; campo vacío = esa línea no aparece.

    DATOS ACTUALES EN DB: {json.dumps(registro, ensure_ascii=False)}

    {PLANTILLA_VISUAL}

    {REGLAS_NORMALIZACION}

    ### DATOS OBLIGATORIOS (solo si faltan para emitir el comprobante/PDF):
    **Orden y redacción:** Incluye en preguntas_obligatorias **únicamente** una línea por cada dato obligatorio que **en DATOS EN DB esté vacío** (null, "", 0 o ausente). Si el campo ya tiene valor, **no escribas esa pregunta**. NUNCA asumas Factura, Boleta, Contado ni Soles. (Sucursal no se pregunta: id_sucursal=14.)
    1. **Monto/Detalle:** FALTA si monto_total no existe o es 0 Y productos_json está vacío o sin ítems.
    2. **Cliente (ventas) o Proveedor (compras):** FALTA si no hay (entidad_nombre + entidad_numero_documento) ni entidad_id_maestro.
    3. **Tipo de comprobante (Factura o Boleta):** FALTA si id_comprobante_tipo no existe o es 0. Pregunta explícitamente: "¿Deseas emitir Factura o Boleta?" (o similar). No asumas Boleta.
    4. **Moneda (Soles/Dólares):** FALTA si id_moneda no existe o es 0. Pregunta: "¿En Soles o en Dólares?" (o similar). No asumas Soles.
    5. **Tipo de pago (Contado/Crédito):** FALTA si tipo_operacion no está definido como "contado" o "credito". No asumas Contado.
    6. **Solo si tipo_operacion = "credito":** FALTA si no hay plazo_dias ni fecha_vencimiento.
        - En VENTA: pregunta por plazo en días o fecha de vencimiento del cobro (ej: "¿En cuántos días vence el cobro?" o "¿Fecha de vencimiento?").
        - En COMPRA: pregunta por plazo en días o fecha de vencimiento del pago al proveedor (ej: "¿En cuántos días vence el pago?" o "¿Fecha de vencimiento del crédito?").

    **Contexto Contado/Crédito:** El preguntador debe tener siempre presente si la operación es a contado o a crédito (tipo_operacion). Si es a crédito, las preguntas obligatorias incluyen además el plazo o fecha de vencimiento, y el texto debe adaptarse a si es compra (pago al proveedor) o venta (cobro al cliente).

    ### DATOS OPCIONALES (solo estos; no incluir aquí nada que sea obligatorio):
    - forma de pago (id_forma_pago; el backend rellena forma_pago_nombre)
    - centro de costo (id_centro_costo o centro_costo_nombre)
    - cuenta/caja (id_caja_banco o caja_banco_nombre)
    - fechas (fecha_emision, fecha_pago)
    (Moneda, tipo de pago, comprobante y cliente son OBLIGATORIOS; si faltan, van solo en preguntas_obligatorias, nunca en opcionales.)

    **Regla:** Si cod_ope YA tiene valor ("compras" o "ventas"), NUNCA incluyas "¿Es una venta o una compra?". Solo si cod_ope está vacío, el primer ítem obligatorio es preguntar el tipo de operación.

    ### SECCIÓN 1 — SÍNTESIS VISUAL:
    Construye el texto siguiendo la plantilla. Para cada línea, comprueba en DATOS EN DB si el campo tiene valor (no null, no "", no 0). Si no tiene valor, **no escribas esa línea**. Si no queda ninguna línea por mostrar, escribe: "Aún no hay datos capturados."
    Aplica las REGLAS DE NORMALIZACIÓN: usa "Factura", "Boleta", "Soles", "Dólares", "DNI", "RUC", "Contado", "Crédito" y nombres (forma_pago_nombre, sucursal_nombre, etc.); NUNCA IDs numéricos. cod_ope = "{cod_ope or 'no definido'}" (Cliente si ventas, Proveedor si compras).

    ### SECCIÓN 2 — DIAGNÓSTICO (solo campos vacíos; sin duplicar entre listas):
    **Regla crítica:** Para cada posible pregunta, mira en DATOS EN DB: si el campo **ya tiene valor**, no escribas esa pregunta. Solo incluye preguntas para campos **realmente vacíos**.
    - **preguntas_obligatorias:** Solo obligatorios que en DATOS EN DB estén vacíos (monto/detalle, cliente/proveedor, tipo comprobante, moneda, tipo pago, plazo si crédito). Si uno ya está lleno, no lo incluyas. Si todos están llenos, una sola línea: sugerencia de finalizar. No incluyas números ni emojis.
    - **preguntas_opcionales:** Solo opcionales vacíos (forma de pago, centro de costo, caja, fechas). **No repitas aquí ningún concepto que ya esté en obligatorias** (ej. si preguntas por moneda en obligatorias, no pongas moneda en opcionales). Si no hay opcionales pendientes, cadena vacía "".
    **Prohibido:** (1) Preguntar por un campo que en DATOS EN DB ya tiene valor. (2) Incluir el mismo concepto/campo en preguntas_obligatorias y en preguntas_opcionales. (3) Decir "puedes confirmar" sin invitación a finalizar cuando no falten obligatorios.

    **listo_para_finalizar:** true si y solo si están completos: (1) monto/detalle, (2) cliente o proveedor, (3) tipo comprobante (id_comprobante_tipo), (4) moneda (id_moneda), (5) tipo_operacion (contado o credito), y (6) si tipo_operacion es "credito", además plazo_dias o fecha_vencimiento. (id_sucursal se asume 14; no se comprueba.) false si falta alguno.

    RESPONDE ÚNICAMENTE EN JSON:
    - sintesis_visual: solo líneas cuyos campos tengan valor en DATOS EN DB.
    - preguntas_obligatorias: solo obligatorios con campo vacío en DB; si está lleno, no incluyas esa pregunta. Sin duplicar con opcionales.
    - preguntas_opcionales: solo opcionales (forma pago, centro costo, caja, fechas) con campo vacío; no incluir moneda/comprobante/pago/cliente aquí (van en obligatorias si faltan). Vacío "" si no hay opcionales pendientes. No repetir ningún ítem que ya esté en obligatorias.
    {{
        "sintesis_visual": "Texto SÍNTESIS (solo líneas con dato definido) con \\n",
        "preguntas_obligatorias": "Solo preguntas para campos OBLIGATORIOS que estén vacíos en DB; cero preguntas para campos llenos. Con \\n",
        "preguntas_opcionales": "Solo preguntas para campos OPCIONALES vacíos en DB; vacío si ninguno pendiente. Con \\n",
        "listo_para_finalizar": false
    }}
    """
