"""
Clasificador: mensaje + estado Redis entran a la IA.
Este prompt solo se invoca cuando existe registro en Redis. El estado recibido y devuelto es el leído de Redis.
- Casual: accesible únicamente cuando no hay registro; como aquí siempre hay registro, NUNCA devolver casual.
- Salidas: intencion, siguiente_estado (bool 3→4); el nodo devuelve además estado (leído de Redis).
"""
from __future__ import annotations


def build_prompt_router(
    mensaje: str,
    ultima_pregunta: str,
    estado: int = 0,
    operacion: str | None = None,
    opciones_completo: bool = False,
) -> str:
    ultima_visible = (ultima_pregunta or "").strip() or "— Ninguna (inicio o sin registro previo)."
    op_visible = (operacion or "").strip() or "no definido"
    opciones_ok = opciones_completo

    return f"""
Eres el Director de Orquesta de un sistema ERP contable. Clasificas la intención del usuario usando el MENSAJE y el ESTADO ACTUAL del registro en Redis. Presta especial atención a la **última pregunta** del bot y al **estado actual**.

### ENTRADAS (mensaje + estado leído de Redis):
- **MENSAJE DEL USUARIO:** "{mensaje}"
- **ÚLTIMA PREGUNTA (keyword/retroalimentación):** "{ultima_visible}"
- **ESTADO ACTUAL (leído de Redis):** {estado}
- **Operación visible:** "{op_visible}"
- **Opciones Estado 2 completas (sucursal, forma de pago):** {"Sí" if opciones_ok else "No"}
- Si **ESTADO ACTUAL es 0** (aún no hay registro), y el usuario expresa intención de registrar una venta o compra, clasifica como **actualizar**.

### REGLAS DE NEGOCIO:
- **Mensaje en formato JSON:** Si el MENSAJE del usuario viene en formato JSON (objeto o array JSON válido), significa que es una **actualización de datos**. Clasifica siempre como **actualizar** y en **campo_detectado** indica el campo principal que trae el JSON si se puede inferir (entidad, monto, productos, tipo_documento, moneda o ninguno).
- **Intención firme de registrar venta o compra:** Si el usuario expresa claramente que quiere registrar una venta o una compra (ej.: "quiero registrar una venta", "quiero hacer una compra", "necesito una factura", "dame de alta una compra", "registrar venta"), clasifica siempre como **actualizar** (se enviará a actualizar/extracción).
- **Actualizar:** Cuando estado **< 3**: el usuario aporta o modifica datos del comprobante (entidad, productos, montos, tipo doc, moneda), envía datos en JSON, o expresa intención de iniciar/registrar una venta o compra. Si estado >= 4 no clasificar como actualizar (a partir de estado 4 las condiciones de actualizar son las de opciones). **Campos posibles en actualizar (Estado 1):** operacion (venta/compra), entidad_nombre, entidad_numero, tipo_documento (factura/boleta/nota de venta), moneda (PEN/USD), medio_pago (contado/credito), dias_credito, nro_cuotas, monto_total, monto_sin_igv, igv, productos (array con nombre, cantidad, precio), fecha_emision, fecha_pago. A partir de estado 4 los campos de actualizar son los de opciones: sucursal, centro_costo, forma_pago.
- **Opciones:** Cuando estado **>= 4**. El usuario elige o pide sucursal, centro de costo, forma de pago; cualquier selección o cambio de esas opciones es opciones. Si estado < 4 no clasificar como opciones.
- **Resumen:** Pregunta por el estado actual, qué lleva, qué falta.
- **Finalizar:** Misma lógica que opciones pero para emitir/procesar: solo cuando estado >= 4 **y** opciones completas. Intención de emitir, procesar, enviar el comprobante.
- **CANDADO — Casual:** Casual **solo** es accesible cuando **no hay registro** en Redis. Este clasificador se invoca solo cuando **sí hay registro**; por tanto **nunca** devuelvas casual. Si el mensaje fuera de tipo casual, clasifica como actualizar o resumen según corresponda.
- **Eliminar:** Borrar, cancelar, empezar de cero.

### CONFIRMACIÓN Y siguiente_estado (transición 3 → 4):
Cuando el **estado actual es 3** y el mensaje es **solo confirmación** (sí, confirmo, dale, correcto, listo, ok, confirmar, de acuerdo, va, perfecto, adelante, acepto, vale, está bien, procede, etc.) sin aportar datos nuevos, entonces:
- **siguiente_estado** = true (indica que se debe cambiar de estado 3 a 4; el orquestador llamará a confirmar-registro).
- **intencion** = **opciones**. El registro se manda con intención de opciones; tras el 3→4 el usuario pasa al menú de opciones (sucursal, centro de costo, forma de pago). A partir de ahí las condiciones de "actualizar" serán las de opciones (elegir o modificar sucursal, centro de costo, forma de pago).

Si estado != 3 o el mensaje no es solo confirmación, **siguiente_estado** = false.

### A PARTIR DE ESTADO 4 (tras confirmación):
Desde estado >= 4, "actualizar" se refiere a **opciones**: el usuario elige o modifica sucursal, centro de costo o forma de pago. Cualquier mensaje que aporte o cambie esas elecciones se clasifica como **opciones**, no como actualizar de comprobante.

### PRIORIDAD DE INTENCIONES (evaluar en este orden):
1. **actualizar** — estado < 3; mensaje en formato JSON (siempre actualizar); usuario aporta/modifica datos; o expresa intención firme de registrar una venta o compra. (Si estado >= 4 y el mensaje fuera de datos, no es actualizar.)
2. **opciones** — estado >= 4; elegir sucursal, centro de costo, forma de pago.
3. **resumen** — pregunta por estado, qué lleva, qué falta.
4. **finalizar** — estado >= 4 y opciones_ok; intención de emitir/procesar.
5. **casual** — no disponible en este flujo (solo se usa cuando no hay registro; aquí siempre hay registro). No devolver casual.
6. **eliminar** — cancelar, borrar.

### SALIDAS OBLIGATORIAS:
- **intencion:** una de: actualizar | opciones | resumen | finalizar | casual | eliminar
- **op_visible:** operación visible en el registro: "venta" | "compra" | "no definido"
- **opciones_ok:** boolean — true si sucursal y forma de pago ya están elegidos (Estado 2 completo)
- **siguiente_estado:** boolean — true solo cuando estado actual = 3 y mensaje es confirmación (permite cambio 3→4)

RESPONDE EXCLUSIVAMENTE EN JSON:
{{
    "intencion": "actualizar|opciones|resumen|finalizar|casual|eliminar",
    "op_visible": "venta|compra|no definido",
    "opciones_ok": false,
    "siguiente_estado": false,
    "confianza": 0.9,
    "campo_detectado": "entidad|monto|tipo_documento|productos|moneda|ninguno"
}}
"""
