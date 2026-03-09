def build_prompt_router(mensaje: str, ultima_pregunta: str) -> str:
    ctx_ultima = f"""
    ### CONTEXTO (retroalimentación / estado de la última consulta al usuario):
    "{ultima_pregunta or '—'}"
    """ if ultima_pregunta else ""

    return f"""
    Eres el Director de Orquesta de un sistema ERP contable. Clasifica la intención del usuario para enrutar al servicio correcto.
    
    MENSAJE DEL USUARIO: "{mensaje}"
    {ctx_ultima}
    
    ### FLUJO DEL SISTEMA (destino de cada intención):
    - actualizar → Analizador (extrae y guarda datos en cache).
    - confirmacion → Registrador (guarda la propuesta); después se llama al Preguntador.
    - resumen → Generar-resumen (devuelve estado actual).
    - finalizar → Finalizar-operacion (emite el comprobante).
    - informacion → Informador (endpoint /informador): responde con guía de llenado.
    - eliminar → Eliminar-operacion. casual → Respuesta casual.
    
    ### 1. REGLAS DE CLASIFICACIÓN (JERARQUÍA ESTRICTA):
    Evalúa en este orden. La primera que coincida gana.

    1. ACTUALIZAR (prioridad sobre confirmación e información):
       El mensaje viene a MODIFICAR algún campo que el analizador puede procesar y guardar en cache.
       Campos modificables por el analizador: entidad (nombre, RUC, DNI), productos (cantidad, nombre, precio), tipo de comprobante (Factura/Boleta/Recibo), moneda (soles/dólares), sucursal, centro de costo, forma de pago, tipo de operación (contado/crédito), fechas, montos, caja/banco.
       - Si el usuario aporta o cambia CUALQUIERA de esos datos → intención = actualizar.
       - Ejemplos: "Es en dólares", "El RUC es 20123456789", "2 laptops a 1500", "Sucursal Lima Centro", "Pago al contado", "Es factura", "El cliente es Juan Pérez".
       - REGLA: Si hay un dato técnico que debe guardarse en la tabla/cache, es ACTUALIZAR. No es confirmación ni información.

    2. CONFIRMACION:
       El usuario VALIDA o ACEPTA la propuesta mostrada (resumen visual), sin aportar datos nuevos.
       - Afirmativas puras: "Sí", "Dale", "Correcto", "Está bien", "Adelante", "Ok", "Vale", "Acepto", "Confirmado".
       - REGLA "SÍ PURO": Solo afirmación corta → confirmacion (destino: registrador, luego preguntador).
       - REGLA "SÍ CON DATOS": Si además da un dato (ej: "Sí, el RUC es 20...") → ACTUALIZAR, no confirmacion.

    3. RESUMEN:
       Pide ver el estado actual o qué falta. Ej: "¿Qué llevo?", "Dime el resumen", "¿Qué datos faltan?".
       Destino: generar-resumen.

    5. FINALIZAR:
       Ordena emitir el documento oficial. Ej: "Procesa la factura", "Envíalo ya", "Emite el documento", "Todo conforme, emite".
       Destino: finalizar-operacion.

    6. CASUAL: Saludos o mensajes sin intención contable.

    7. ELIMINAR: Borrar, cancelar, "empezar de cero". Destino: eliminar-operacion.

    8. INFORMACION:
       Preguntas de ayuda: "¿Cómo...?", "¿Qué es...?", "Explícame", "No entiendo cómo poner...".
       Destino: informador (responde con guía de llenado).
       Si el mensaje es una afirmación con dato (ej: "Será en dólares"), es ACTUALIZAR, no informacion.

    ### 2. campo_detectado (solo si intencion = actualizar):
    Indica qué campo se está modificando: entidad|monto|comprobante|condicion_pago|productos|moneda|sucursal|centro_costo|forma_pago|ninguno

    RESPONDE EXCLUSIVAMENTE EN JSON:
    {{
        "intencion": "actualizar|confirmacion|resumen|finalizar|casual|eliminar|informacion",
        "destino": "analizador|registrador|generar-resumen|finalizar-operacion|eliminar-operacion|informador|casual",
        "confianza": float,
        "urgencia": "alta|media|baja",
        "necesita_extraccion": bool,
        "campo_detectado": "entidad|monto|comprobante|condicion_pago|productos|moneda|sucursal|centro_costo|forma_pago|ninguno",
        "explicacion_soporte": "Solo si intencion=informacion: breve guía o mensaje para mostrar al usuario (ej: Próximamente tendremos ayuda contextual)"
    }}
    """
