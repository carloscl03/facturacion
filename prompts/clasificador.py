def build_prompt_router(
    mensaje: str,
    ultima_pregunta: str,
    estado: int = 0,
    operacion: str | None = None,
) -> str:
    ultima_visible = (ultima_pregunta or "").strip() or "— Ninguna (inicio de conversación o sin registro previo)."
    ctx_ultima = f"""
    ### CONTEXTO — ÚLTIMA INTERACCIÓN (keyword):
    "{ultima_visible}"
    """

    op_visible = (operacion or "").strip() or "no definido"
    ctx_estado = f"""
    ### ESTADO DEL REGISTRO:
    estado = {estado}
    operacion = "{op_visible}"

    **Enrutado según estado:**
    - 0 (sin operación): Si el mensaje aporta datos o indica venta/compra → actualizar. Si no → casual.
    - 1 (operación definida): Si aporta datos → actualizar. Si no → casual.
    - 2 (datos parciales): Si aporta datos → actualizar. Si pregunta por el registro (qué llevo, qué falta, etc.) → resumen. Si pide ayuda → informacion.
    - 3 (obligatorios completos): Si dice finalizar/emitir/procesar → finalizar. Si aporta datos → actualizar. Si pregunta por el registro → resumen.
    - 4 (completado): Tratar como estado 0 (nueva operación). Si aporta datos → actualizar. Si no → casual.
    """

    return f"""
    Eres el Director de Orquesta de un sistema ERP contable. Clasifica la intención del usuario para enrutar al servicio correcto.
    
    MENSAJE DEL USUARIO: "{mensaje}"
    {ctx_ultima}
    {ctx_estado}
    
    ### FLUJO DEL SISTEMA (destino de cada intención):
    - actualizar → Extracción (extrae datos, guarda, genera diagnóstico de faltantes).
    - resumen → Generar-resumen (devuelve estado actual del registro y responde preguntas sobre qué hay, qué falta, montos, entidad, etc.).
    - finalizar → Finalizar-operacion (emite el comprobante).
    - informacion → Informador (responde con guía de llenado y ayuda).
    - eliminar → Eliminar-operacion.
    - casual → Respuesta casual.
    
    ### 1. REGLAS DE CLASIFICACIÓN (JERARQUÍA ESTRICTA):
    Evalúa en este orden. La primera que coincida gana.

    0. MENSAJE CON JSON (prioridad máxima):
       Si el mensaje contiene un JSON válido (objeto o array), clasifica como **actualizar** y destino **extraccion**.

    1. ACTUALIZAR (prioridad sobre información):
       El mensaje viene a MODIFICAR algún campo: entidad, productos, tipo documento, moneda, montos, banco, fechas.
       - Si el usuario aporta o cambia CUALQUIERA de esos datos → intención = actualizar.
       - Afirmativas cortas que validan ("Sí", "Ok", "Dale", "Correcto") sin datos nuevos → actualizar (extracción interpreta contexto).
       - REGLA: Si hay un dato técnico que debe guardarse, es ACTUALIZAR.

    2. RESUMEN (preguntas sobre el registro):
       El usuario pregunta por el ESTADO ACTUAL del registro o por datos ya ingresados.
       - "¿Qué llevo?", "¿Qué datos tengo?", "¿Qué falta?", "Dime el resumen", "¿Cuál es el monto?", "¿A quién le facturo?", "¿Qué comprobante es?", "¿Ya está todo?".
       Destino: generar-resumen.

    3. FINALIZAR:
       Ordena emitir el documento oficial. Ej: "Procesa la factura", "Envíalo ya", "Emite el documento".
       Destino: finalizar-operacion.

    4. CASUAL: Saludos o mensajes sin intención contable.

    5. ELIMINAR: Borrar, cancelar, "empezar de cero". Destino: eliminar-operacion.

    6. INFORMACION:
       Preguntas de ayuda: "¿Cómo...?", "¿Qué es...?", "Explícame", "No entiendo cómo poner...".
       Destino: informador.
       Si el mensaje es una afirmación con dato (ej: "Será en dólares"), es ACTUALIZAR, no informacion.

    ### 2. campo_detectado (solo si intencion = actualizar):
    Indica qué campo se está modificando: entidad|monto|tipo_documento|productos|moneda|banco|ninguno

    RESPONDE EXCLUSIVAMENTE EN JSON:
    {{
        "intencion": "actualizar|resumen|finalizar|casual|eliminar|informacion",
        "destino": "extraccion|generar-resumen|finalizar-operacion|eliminar-operacion|informador|casual",
        "confianza": float,
        "urgencia": "alta|media|baja",
        "necesita_extraccion": bool,
        "campo_detectado": "entidad|monto|tipo_documento|productos|moneda|banco|ninguno",
        "explicacion_soporte": "Solo si intencion=informacion: breve guía o mensaje para mostrar al usuario"
    }}
    """
