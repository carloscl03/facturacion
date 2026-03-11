import json

from prompts.plantillas import PLANTILLA_VISUAL


def build_prompt_pregunta(registro: dict) -> str:
    monto_total = registro.get("monto_total", 0)
    entidad_id = registro.get("entidad_id", "")
    tipo_documento = registro.get("tipo_documento", "")

    return f"""
    Eres el Asistente Contable de MaravIA. Interpreta los datos actuales y genera la siguiente pregunta para completar el registro.

    DATOS EN REDIS: {json.dumps(registro, ensure_ascii=False)}
    ÚLTIMA INTERACCIÓN: "{registro.get('ultima_pregunta', '')}"

    ### REGLA ESTRICTA — PREGUNTAS DINÁMICAS:
    Solo pregunta por campos VACÍOS. Si un campo ya tiene valor, NO lo preguntes.
    **NO preguntar por:** sucursal, forma de pago, medio de pago (se gestionan en Estado 2).

    Checklist (solo para decidir qué preguntar):
    - 🔴 BLOQUEANTES:
        * Monto Total: { "OK" if monto_total and float(monto_total) > 0 else "FALTA" }
        * Entidad (identificado): { "OK" if entidad_id else "FALTA (Requiere identificación)" }
        * Tipo Documento: { "OK" if tipo_documento else "FALTA" }
    - 🟡 OBLIGATORIOS:
        * Moneda (PEN/USD): { "OK" if registro.get('moneda') else "FALTA" }
        * Banco: { "OK" if registro.get('banco') else "FALTA" }

    MATRIZ DE PRIORIDAD (primer campo vacío = genera pregunta):
    1. PRODUCTOS: Si monto_total es 0 y productos vacío.
    2. ENTIDAD: Si no hay entidad_nombre ni entidad_id. Si entidad_numero tiene valor, SALTAR (sistema procesando).
    3. TIPO DOCUMENTO: Si tipo_documento es vacío. Preguntar "¿Factura, Boleta o Nota de venta?"
    4. MONEDA: Si moneda es vacío. Preguntar "¿En Soles (PEN) o Dólares (USD)?"
    5. BANCO: Si banco es vacío.
    6. FINALIZACIÓN: Si todo completo, invitar a finalizar.

    ### ESTRUCTURA DEL TEXTO:
    {PLANTILLA_VISUAL}

    LA GUÍA ('resumen_y_guia'):
    (1) SÍNTESIS VISUAL: solo líneas con datos presentes.
    (2) DIAGNÓSTICO: solo campos realmente vacíos.
    (3) PREGUNTA: una sola pregunta concreta para el primer dato faltante.

    ### BOTONES:
    - requiere_botones = TRUE solo como apoyo:
        * Tipo Documento: "Factura" / "Boleta" si tipo_documento vacío.
        * Cierre: "🚀 Finalizar" cuando todo esté completo.
    - requiere_botones = FALSE para procesos de escritura.

    RESPONDE ÚNICAMENTE EN JSON:
    {{
        "resumen_y_guia": "...",
        "requiere_botones": bool,
        "btn1_id": "...", "btn1_title": "...",
        "btn2_id": "...", "btn2_title": "..."
    }}
    """


def build_prompt_preguntador_v2(registro: dict, operacion: str | None) -> str:
    return f"""
    Eres el Asistente Contable de MaravIA. Genera (1) SÍNTESIS VISUAL y (2) DIAGNÓSTICO.

    **REGLA 1 — SOLO CAMPOS VACÍOS:** Si un campo ya tiene valor, NO escribas esa pregunta.
    **REGLA 2 — SIN REPETIR:** Un campo aparece solo en obligatorias o en opcionales, nunca ambas.
    **NO preguntar por:** sucursal, forma de pago, medio de pago (se gestionan en Estado 2).

    DATOS EN REDIS: {json.dumps(registro, ensure_ascii=False)}

    {PLANTILLA_VISUAL}

    ### DATOS OBLIGATORIOS (solo si faltan):
    1. Monto/Detalle: falta si monto_total = 0 y productos vacío.
    2. Cliente (venta) o Proveedor (compra): falta si no hay entidad_nombre ni entidad_id.
    3. Tipo de documento: falta si tipo_documento vacío. Preguntar "¿Factura, Boleta o Nota de venta?"
    4. Moneda: falta si moneda vacío. Preguntar "¿PEN o USD?"
    5. Banco: falta si banco vacío.

    ### DATOS OPCIONALES:
    - fecha_emision, fecha_pago (si aplican)
    (No incluir aquí tipo_documento, moneda, entidad — van en obligatorios.)

    Si operacion ya está definida como "{operacion or 'no definido'}", NO preguntar venta/compra.

    ### SÍNTESIS VISUAL:
    Solo líneas con datos presentes. Los campos ya usan nombres naturales.

    ### DIAGNÓSTICO:
    - preguntas_obligatorias: solo obligatorios vacíos. Si todos están llenos, invitar a finalizar.
    - preguntas_opcionales: solo opcionales vacíos. "" si no hay.

    **listo_para_finalizar:** true si están completos: (1) monto/detalle, (2) entidad, (3) tipo_documento, (4) moneda. false si falta alguno.

    RESPONDE ÚNICAMENTE EN JSON:
    {{
        "sintesis_visual": "Texto SÍNTESIS con \\n",
        "preguntas_obligatorias": "Solo preguntas para campos vacíos con \\n",
        "preguntas_opcionales": "Solo opcionales vacíos con \\n",
        "listo_para_finalizar": false
    }}
    """
