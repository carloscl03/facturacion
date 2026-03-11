def build_prompt_router(
    mensaje: str,
    ultima_pregunta: str,
    estado: int = 0,
    operacion: str | None = None,
    opciones_completo: bool = False,
) -> str:
    ultima_visible = (ultima_pregunta or "").strip() or "— Ninguna (inicio de conversación o sin registro previo)."
    ctx_ultima = f"""
    ### CONTEXTO — ÚLTIMA INTERACCIÓN (keyword):
    "{ultima_visible}"
    """

    op_visible = (operacion or "").strip() or "no definido"
    opciones_ok = "Sí (sucursal, forma de pago y medio de pago ya elegidos)" if opciones_completo else "No (falta elegir sucursal, forma de pago o medio de pago)"
    ctx_estado = f"""
    ### ESTADO DEL REGISTRO:
    estado = {estado}
    operacion = "{op_visible}"
    opciones_completo (Estado 2) = {opciones_ok}

    **Acceso por estado (interpreta el mensaje del usuario, no términos estáticos):**
    - **Confirmar registro (PRIORIDAD sobre actualizar):** Solo estado 3 (o datos obligatorios completos). Si el mensaje expresa SOLO confirmación en lenguaje natural (sí, confirmo, dale, correcto, listo, ok, confirmar, de acuerdo, va, perfecto, adelante, acepto, vale, está bien, procede, etc.) y NO aporta datos nuevos (no JSON, no montos, no entidad, no productos), clasifica como **confirmar_registro**. El sistema habrá pedido "¿Confirmar todo para continuar?"; la respuesta afirmativa cierra el flujo de actualizar y permite pasar a estado 4 y al menú de opciones. **Nunca clasificar como actualizar** cuando el mensaje es pura confirmación y el registro está listo (estado 3).
    - **Opciones:** Solo desde estado 4. Tras confirmar, el usuario elige sucursal, forma de pago o medio de pago. Si estado < 4, no clasificar como opciones.
    - **Actualizar:** Estados 0, 1, 2 y 3. Solo cuando el usuario **aporta o modifica datos** (entidad, productos, montos, tipo doc, moneda, fechas). Si el mensaje es únicamente una afirmación de confirmación (sí, dale, confirmar, etc.) y estado = 3, es confirmar_registro, no actualizar.
    - **Casual:** Solo cuando NO hay registro activo. Si hay registro, nunca clasifiques como casual.
    - **Finalizar:** Solo cuando estado >= 4 y opciones_completo = Sí. Intención de emitir/procesar el comprobante.
    - **Resumen / Eliminar / Información:** Sin restricción de estado.
    """

    return f"""
    Eres el Director de Orquesta de un sistema ERP contable. Clasifica la intención del usuario para enrutar al servicio correcto.
    
    MENSAJE DEL USUARIO: "{mensaje}"
    {ctx_ultima}
    {ctx_estado}
    
    ### FLUJO DEL SISTEMA (destino de cada intención):
    - casual → Respuesta casual. **Solo accesible si no hay registro** (primer mensaje; sistema de botones).
    - actualizar → Extracción. **Estados 0 a 3:** el usuario aporta o modifica datos; interpreta la intención, no solo palabras clave.
    - confirmar_registro → Confirmar-registro. **Solo estado 3** y mensaje de confirmación; el sistema pasa a estado 4.
    - opciones → Opciones (sucursal, forma de pago, medio de pago). **Solo desde estado 4** (tras confirmar registro).
    - finalizar → Finalizar-operacion. **Solo estado >= 4 y opciones_completo = Sí** (sucursal, forma y medio de pago ya elegidos); interpreta intención de emitir/procesar.
    - resumen → Generar-resumen. informacion → Informador. eliminar → Eliminar-operacion.
    
    ### 1. REGLAS DE CLASIFICACIÓN (JERARQUÍA ESTRICTA):
    Evalúa en este orden. **La confirmación cierra actualizar y abre opciones;** no enrutes confirmación a extracción.

    0. MENSAJE CON JSON (prioridad máxima):
       Si el mensaje contiene un JSON válido (objeto o array), clasifica como **actualizar** y destino **extraccion**.

    1. CONFIRMAR REGISTRO (solo si estado = 3; prioridad sobre actualizar):
       Si el mensaje expresa **solo** confirmación/aceptación en lenguaje natural (sí, confirmo, dale, correcto, listo, ok, confirmar, de acuerdo, va, perfecto, adelante, acepto, vale, está bien, procede, confirmado, de una, etc.) y **no** incluye datos nuevos (ni JSON, ni montos, ni RUC, ni productos, ni tipo de documento), clasifica como **confirmar_registro**.
       La validación de datos completos (estado 3) + intención de confirmar permiten el cambio a estado 4 y al menú de opciones. **No clasificar como actualizar** cuando el mensaje es pura confirmación.
       Destino: confirmar-registro (el sistema pasará a estado 4; el orquestador enviará luego a opciones).

    2. OPCIONES (solo si estado >= 4):
       El usuario elige o responde sobre sucursal, forma de pago o medio de pago, o pide ver/elegir opciones. Si estado < 4, no clasificar como opciones.
       Destino: opciones.

    3. ACTUALIZAR (estados 0, 1, 2, 3):
       Solo cuando el usuario **aporta o modifica datos** del comprobante (entidad, productos, montos, tipo doc, moneda, fechas). Si el mensaje es únicamente una afirmación de confirmación (sí, dale, confirmar, etc.) y estado = 3, es confirmar_registro, no actualizar.
       Destino: extraccion.

    4. FINALIZAR (solo si estado >= 4 y opciones_completo = Sí):
       El usuario expresa intención de emitir, procesar o finalizar el comprobante. Interpreta: procesar, emitir, enviar, finalizar, listo para emitir, etc. Si opciones no están completas, no clasificar como finalizar.
       Destino: finalizar-operacion.

    5. RESUMEN (preguntas sobre el registro):
       El usuario pregunta por el estado actual, qué lleva, qué falta, montos, etc. Destino: generar-resumen.

    6. ELIMINAR: Intención de borrar, cancelar o empezar de cero. Destino: eliminar-operacion.

    7. INFORMACION:
       Preguntas de ayuda: "¿Cómo...?", "¿Qué es...?", "Explícame", "No entiendo cómo poner...".
       Destino: informador.
       Si el mensaje es una afirmación con dato concreto (ej: "Será en dólares"), es ACTUALIZAR, no informacion.

    8. CASUAL: Solo si no hubiera registro (aquí ya hay registro porque tienes estado). Si hay registro, no devuelvas casual; elige la intención más coherente (actualizar, resumen, etc.).

    ### 2. campo_detectado (solo si intencion = actualizar):
    Indica qué campo se está modificando: entidad|monto|tipo_documento|productos|moneda|ninguno

    RESPONDE EXCLUSIVAMENTE EN JSON:
    {{
        "intencion": "actualizar|confirmar_registro|opciones|resumen|finalizar|casual|eliminar|informacion",
        "destino": "extraccion|confirmar-registro|opciones|generar-resumen|finalizar-operacion|eliminar-operacion|informador|casual",
        "confianza": float,
        "urgencia": "alta|media|baja",
        "necesita_extraccion": bool,
        "campo_detectado": "entidad|monto|tipo_documento|productos|moneda|ninguno",
        "explicacion_soporte": "Solo si intencion=informacion: breve guía o mensaje para mostrar al usuario"
    }}
    """
