"""
Clasificador: mensaje + estado Redis entran a la IA.
Se presta atención a la última pregunta y al estado actual.
Salidas: (1) intencion (prioridad: actualizar|opciones|resumen|finalizar|casual|eliminar), (2) siguiente_estado (bool 3→4).
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

### ENTRADAS (mensaje + estado Redis):
- **MENSAJE DEL USUARIO:** "{mensaje}"
- **ÚLTIMA PREGUNTA (keyword/retroalimentación):** "{ultima_visible}"
- **ESTADO ACTUAL (Redis):** {estado}
- **Operación visible:** "{op_visible}"
- **Opciones Estado 2 completas (sucursal, forma de pago, medio de pago):** {"Sí" if opciones_ok else "No"}

### REGLAS DE NEGOCIO:
- **Actualizar:** Solo cuando estado **< 3**. El usuario aporta o modifica datos del comprobante (entidad, productos, montos, tipo doc, moneda). Si estado >= 4 no clasificar como actualizar (a partir de estado 4 las condiciones de actualizar son las de opciones).
- **Opciones:** Cuando estado **>= 4**. El usuario elige o pide sucursal, forma de pago, medio de pago; cualquier selección o cambio de esas opciones es opciones. Si estado < 4 no clasificar como opciones.
- **Resumen:** Pregunta por el estado actual, qué lleva, qué falta.
- **Finalizar:** Misma lógica que opciones pero para emitir/procesar: solo cuando estado >= 4 **y** opciones completas. Intención de emitir, procesar, enviar el comprobante.
- **CANDADO — Casual:** El mensaje casual **solo** es accesible cuando **no hay registro o estado = 0**. A partir de **estado >= 1** no se puede clasificar como casual; en ese caso elige actualizar, resumen u otra intención según el mensaje.
- **Eliminar:** Borrar, cancelar, empezar de cero.

### CONFIRMACIÓN Y siguiente_estado (transición 3 → 4):
Cuando el **estado actual es 3** y el mensaje es **solo confirmación** (sí, confirmo, dale, correcto, listo, ok, confirmar, de acuerdo, va, perfecto, adelante, acepto, vale, está bien, procede, etc.) sin aportar datos nuevos, entonces:
- **siguiente_estado** = true (indica que se debe cambiar de estado 3 a 4; el orquestador llamará a confirmar-registro).
- **intencion** = **opciones**. El registro se manda con intención de opciones; tras el 3→4 el usuario pasa al menú de opciones (sucursal, forma de pago, medio de pago). A partir de ahí las condiciones de "actualizar" serán las de opciones (elegir o modificar sucursal, forma de pago, medio de pago).

Si estado != 3 o el mensaje no es solo confirmación, **siguiente_estado** = false.

### A PARTIR DE ESTADO 4 (tras confirmación):
Desde estado >= 4, "actualizar" se refiere a **opciones**: el usuario elige o modifica sucursal, forma de pago o medio de pago. Cualquier mensaje que aporte o cambie esas elecciones se clasifica como **opciones**, no como actualizar de comprobante.

### PRIORIDAD DE INTENCIONES (evaluar en este orden):
1. **actualizar** — estado < 3; usuario aporta/modifica datos. (Si estado >= 4 y el mensaje fuera de datos, no es actualizar.)
2. **opciones** — estado >= 4; elegir sucursal, forma de pago, medio de pago.
3. **resumen** — pregunta por estado, qué lleva, qué falta.
4. **finalizar** — estado >= 4 y opciones_ok; intención de emitir/procesar.
5. **casual** — solo si estado = 0 (sin registro). **Candado:** desde estado >= 1 no devolver casual.
6. **eliminar** — cancelar, borrar.

### SALIDAS OBLIGATORIAS:
- **intencion:** una de: actualizar | opciones | resumen | finalizar | casual | eliminar
- **op_visible:** operación visible en el registro: "venta" | "compra" | "no definido"
- **opciones_ok:** boolean — true si sucursal, forma de pago y medio de pago ya están elegidos (Estado 2 completo)
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
