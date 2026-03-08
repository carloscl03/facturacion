import json
import os
import requests
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
URL_API = "https://api.maravia.pe/servicio/n8n/ws_historial_cache.php"

# Cambio de modelo a gpt-4o-mini
MODELO_IA = "gpt-4o-mini"

# --- URLs ADICIONALES ---
URL_CLIENTE = "https://api.maravia.pe/servicio/n8n/ws_cliente.php"
URL_PROVEEDOR = "https://api.maravia.pe/servicio/n8n_asistente/ws_proveedor.php"

# --- PLANTILLA VISUAL COMPARTIDA (analizador, preguntador, resumen) ---
# Misma estructura y nombres de campos. En preguntador y resumen: mostrar SOLO líneas cuyo campo esté definido (no null, no "", no 0).
PLANTILLA_VISUAL = """
ESTRUCTURA DE SECCIONES (usa estos nombres de campo del registro; cada línea se muestra SOLO si el campo tiene valor definido):

0) TIPO DE OPERACIÓN (primera línea del encabezado; mostrar solo si cod_ope está definido)
   ━━━━━━━━━━━━━━━━━━━
   🛒 *COMPRA*  — mostrar si: cod_ope = "compras"
   📤 *VENTA*   — mostrar si: cod_ope = "ventas"
   ━━━━━━━━━━━━━━━━━━━

1) ENCABEZADO OPERACIÓN
   ━━━━━━━━━━━━━━━━━━━
   📄 *[comprobante_tipo_nombre]*  — mostrar si: id_comprobante_tipo definido
   👤 *[CLIENTE o PROVEEDOR]:* [entidad_nombre]  — mostrar si: entidad_nombre definido
   🆔 *[DNI o RUC]:* [entidad_numero_documento]  — mostrar si: entidad_numero_documento definido
   ━━━━━━━━━━━━━━━━━━━

2) DETALLE Y MONEDAS
   📦 *DETALLE DE [VENTA o COMPRA]:*
   🔹 Cant. [cantidad] x [nombre] — [moneda_simbolo][total_item]  — por cada ítem en productos_json (mostrar sección si productos_json tiene al menos un ítem)
   💰 *RESUMEN ECONÓMICO:*
   ├─ Subtotal: [moneda_simbolo] [monto_base]  — mostrar si: monto_base definido y > 0
   ├─ IGV (18%): [moneda_simbolo] [monto_impuesto]
   └─ *TOTAL: [moneda_simbolo] [monto_total]*  — mostrar si: monto_total definido y > 0
   ━━━━━━━━━━━━━━━━━━━

3) LOGÍSTICA Y PAGO (todos opcionales; incluir línea solo si el campo está definido)
   📍 *Sucursal:* [sucursal_nombre]  — si: id_sucursal o sucursal_nombre
   🏗️ *Centro de costo:* [centro_costo_nombre]  — si: id_centro_costo o centro_costo_nombre
   💳 *Pago:* [tipo_operacion]  — si: tipo_operacion (contado/credito)
   💵 *Moneda:* [moneda_nombre]  — si: id_moneda
   🏦 *Cuenta/Caja:* [caja_banco_nombre] o [forma_pago_nombre]  — si: caja_banco_nombre o id_forma_pago
   📅 *Emisión:* [fecha_emision]  — si: fecha_emision
   🔄 *Crédito:* [plazo_dias] días | *Vencimiento:* [fecha_vencimiento]  — si: tipo_operacion = credito y (plazo_dias o fecha_vencimiento)
   ━━━━━━━━━━━━━━━━━━━

Regla crítica: NO escribas ninguna línea cuya condición "mostrar si" no se cumpla. Si un campo está vacío, null o 0, esa línea NO debe aparecer en la síntesis (irá al diagnóstico).
"""

# --- REGLAS DE NORMALIZACIÓN (analizador, preguntador) — lenguaje natural, nunca IDs ---
REGLAS_NORMALIZACION = """
REGLAS DE NORMALIZACIÓN (OBLIGATORIAS — lenguaje natural, nunca IDs):
En la Síntesis, el Resumen y el Diagnóstico NUNCA uses números ni códigos internos. Siempre traduce a lenguaje natural usando esta tabla:
- id_comprobante_tipo: 1 → "Factura", 2 → "Boleta", 3 → "Recibo". Pregunta p. ej. "¿Deseas emitir Factura o Boleta?" nunca "¿id_comprobante_tipo?"
- id_moneda: 1 → "Soles" (S/), 2 → "Dólares" ($).
- entidad_id_tipo_documento: 1 → "DNI", 6 → "RUC". Pregunta "¿Me das el RUC o DNI del cliente?" no el id.
- tipo_operacion: "contado" → "Contado", "credito" → "Crédito". Pregunta "¿Fue al contado o a crédito?"
- Sucursal, centro de costo, forma de pago, cuenta: usa siempre los nombres (sucursal_nombre, centro_costo_nombre, etc.), nunca id_sucursal ni números.
Las preguntas deben sonar naturales: "¿Cuál es el monto o detalle de los productos?", "¿Cuál es el RUC o nombre del cliente?", "¿Emitimos Factura o Boleta?", "¿En qué sucursal se realizó?", "¿Fue al contado o a crédito?"
"""

# --- SERVICIO 1: EXTRACCIÓN (MODIFICADO) ---
@app.post("/procesar-extraccion")
async def procesar_extraccion(wa_id: str, mensaje: str, id_empresa: int):
    # 1. Obtener estado actual
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": id_empresa}
    res_db = requests.get(URL_API, params=params_leer)
    data_db = res_db.json().get('data', [])
    estado_actual = data_db[0] if data_db else {}
    es_registro_nuevo = len(data_db) == 0

    contexto_operacion = estado_actual.get('cod_ope', 'ventas')
    ultima_pregunta_bot = estado_actual.get('ultima_pregunta', '')

    # --- IA Reforzada para entender Frases de Botones y Productos ---
    prompt_extractor = f"""
    Eres el Agente Contable experto de MaravIA. Tu misión es procesar mensajes de texto que pueden ser extracciones de datos, productos o SELECCIONES DE BOTONES.

    CONTEXTO:
    - OPERACIÓN: {contexto_operacion.upper()}
    - DATOS EN DB: {json.dumps(estado_actual, ensure_ascii=False)}
    - ÚLTIMA GUÍA ENVIADA: "{ultima_pregunta_bot}"
    - MENSAJE RECIBIDO: "{mensaje}"

    REGLAS DE PRODUCTOS (CRÍTICO):
    1. Extrae cada ítem con la estructura: {{"cantidad": float, "nombre": str, "precio_unitario": float, "total_item": float}}.
    2. Si el usuario envía productos nuevos y ya existen otros en "DATOS EN DB", ACUMÚLALOS, a menos que el mensaje sea una corrección clara (ej: "No, solo era 1 coca cola"), en cuyo caso REEMPLAZA la lista.
    3. Si el usuario no menciona el precio, busca si ya existe un precio para ese producto en el historial de la DB o deja 0.0.

    REGLAS DE CÁLCULO:
    1. monto_total = Suma de todos los (cantidad * precio_unitario).
    2. monto_base = monto_total / 1.18.
    3. monto_impuesto = monto_total - monto_base.

    REGLAS DE INTERPRETACIÓN DE BOTONES:
    1. Si el mensaje es una frase de selección (Ej: "Emitir una Factura", "Es un RUC", "El pago es al Contado"):
    - Identifica la intención y actualiza el campo correspondiente.
    - NO intentes extraer productos de estas frases de botones.
    - Equivalencias: FACTURA=1, BOLETA=2, RECIBO=3 | SOLES=1, DÓLARES=2 | RUC=6, DNI=1.

    REGLAS DE NORMALIZACIÓN (ESTRICTAS):
    - id_comprobante_tipo: FACTURA=1, BOLETA=2, RECIBO=3.
    - id_moneda: SOLES=1, DÓLARES=2.
    - tipo_operacion: "contado" o "credito".
    - id_centro_costo: 1 (General).
    - entidad_id_tipo_documento: DNI (8 dígitos) ->id: 1, RUC (11 dígitos) ->id: 6.
    
   REGLAS DE ESTADO (BITÁCORA):
    - Si vas a marcar requiere_identificacion: true, especifica en 'ultima_pregunta' qué dato estás enviando a buscar (ej: "Buscando RUC 2060...").

    REGLAS DE SUCURSAL:
    1. Si el usuario menciona una ubicación, extrae el nombre en 'sucursal_nombre'.
    2. Si no hay mención, mantén el 'id_sucursal' de la DB. Si la DB está vacía, devuelve null.

    RESPONDE ESTRICTAMENTE ESTE JSON:
    {{
        "requiere_identificacion": bool,
        "cod_ope": "ventas" o "compras",
        "entidad_nombre": str, 
        "entidad_id_tipo_documento": int o null,
        "id_comprobante_tipo": int, 
        "monto_total": float, 
        "monto_base": float, 
        "monto_impuesto": float,
        "productos_json": [
            {{
                "cantidad": float,
                "nombre": str,
                "precio_unitario": float,
                "total_item": float
            }}
        ],
        "tipo_operacion": "contado" o "credito", 
        "id_moneda": int,
        "id_sucursal": int o null,
        "id_centro_costo": 1,
        "ultima_pregunta": "Breve resumen de la acción realizada (Ej: 'Se agregaron 2 productos por S/ 45.00')"
    }}
    """

    response = client.chat.completions.create(
        model=MODELO_IA,
        messages=[{"role": "system", "content": prompt_extractor}],
        response_format={"type": "json_object"}
    )
    
    cambios_ia = json.loads(response.choices[0].message.content)
    
    nuevo_contexto = cambios_ia.get('cod_ope') or contexto_operacion

    payload = {
        "codOpe": "INSERTAR_CACHE" if es_registro_nuevo else "ACTUALIZAR_CACHE",
        "ws_whatsapp": wa_id,
        "id_empresa": id_empresa,
        "cod_ope": nuevo_contexto, # Ahora sí recibirá "compras" si la IA lo detecta
        **{k: v for k, v in cambios_ia.items() if k not in ["requiere_identificacion", "cod_ope"] and v is not None}
    }
    
    # 4. Ejecutar la llamada al servidor PHP
    res_post = requests.post(URL_API, json=payload)
    # ------------------------------------------------------------
    
    # En el return de tu función de extracción
    return {
        "status": "sincronizado",
        "requiere_identificacion": cambios_ia.get('requiere_identificacion', False),
        "datos_entidad": {
            # Priorizamos el documento, luego el nombre. Si ambos fallan, va vacío.
            "termino": cambios_ia.get('entidad_numero_documento') or cambios_ia.get('entidad_nombre') or "",
            "tipo_ope": contexto_operacion,
            "tipo_doc": cambios_ia.get('id_comprobante_tipo') # O 6 si es RUC
        },
        "bitacora_ia": cambios_ia.get('ultima_pregunta')
    }

# --- SERVICIO 2: PREGUNTADOR (VERSIÓN OPTIMIZADA) ---
@app.post("/generar-pregunta")
async def generar_pregunta(wa_id: str, id_empresa: int):
    # 1. Obtener el estado actual del caché
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": id_empresa}
    res_db = requests.get(URL_API, params=params_leer)
    data_db = res_db.json().get('data', [])
    registro = data_db[0] if data_db else {}

    # Caso inicial: Registro vacío
    if not registro:
        return {
            "pregunta_casual": "¡Hola! Soy MaravIA. Para empezar con el registro, selecciona el tipo de operación:",
            "requiere_botones": True,
            "btn1_id": "ventas", "btn1_title": "Es una Venta",
            "btn2_id": "compras", "btn2_title": "Es una Compra"
        }

    # 2. Prompt con interpretación de Normalización y Resumen
    prompt_pregunta = f"""
    Eres el Asistente Contable de MaravIA. Tu misión es interpretar los datos actuales del registro y y EMPUJAR el registro al siguiente paso faltante.

    DATOS EN DB (Normalizados): {json.dumps(registro, ensure_ascii=False)}
    ÚLTIMA BITÁCORA: "{registro.get('ultima_pregunta', '')}"

    ### 1. INSTRUCCIONES DE INTERPRETACIÓN (IDs de Sistema):
    - id_comprobante_tipo: 1=Factura, 2=Boleta, 3=Recibo.
    - id_moneda: 1=Soles (S/), 2=Dólares ($).
    - tipo_operacion: "contado" o "credito".
    - entidad_id_tipo_documento: 1=DNI, 6=RUC.

    ---
    ### 2. 🚦 MONITOREO DE INTEGRIDAD (Checklist Interno)
    Usa este diagnóstico para decidir qué preguntar:
    - 🔴 BLOQUEANTES: 
        * Monto Total: { "OK" if registro.get('monto_total') and float(registro.get('monto_total')) > 0 else "FALTA" }
        * Entidad (ID Maestro): { "OK" if registro.get('entidad_id_maestro') else "FALTA (Requiere identificación)" }
        * Tipo Comprobante: { "OK" if registro.get('id_comprobante_tipo') else "FALTA" }
    - 🟡 OPCIONALES:
        * Sucursal: { "OK" if registro.get('id_sucursal') else "Pendiente (Default: 14)" }
        * Pago: { "OK" if registro.get('tipo_operacion') else "Pendiente (Default: Contado)" }

    MATRIZ DE PRIORIDAD (Sigue este orden y DETENTE en el primer campo que sea NULL o 0):
    1. PRODUCTOS: Si 'monto_total' es 0 o 'productos_json' está vacío.
    2. ENTIDAD: Regla de Salto: Si entidad_numero_documento tiene valor Y entidad_id_tipo_documento es (1 o 6), SÁLTALO. No vuelvas a preguntar aunque entidad_id_maestro sea null (el sistema lo está procesando).
    3. COMPROBANTE: Si 'id_comprobante_tipo' es NULL, 0 o NO EXISTE. 
    -> REGLA: Si ya existe un valor (1, 2 o 3), SALTA este paso inmediatamente.
    4. PAGO: Si 'tipo_operacion' no está definido como "contado" o "credito".
    5. FINALIZACIÓN: Si todo está lleno, genera el resumen final y pregunta por la emisión.

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
    El texto debe contener SIEMPRE: (1) SÍNTESIS VISUAL (resumen con la estructura de arriba, solo datos existentes), (2) DIAGNÓSTICO (qué falta según MATRIZ DE PRIORIDAD), (3) RETROALIMENTACIÓN del último cambio si aplica, (4) PREGUNTA concreta para el siguiente dato. No omitas síntesis ni diagnóstico.
    
    ### 6. LÓGICA DE INTERACCIÓN Y BOTONES (PRIORIDAD PREGUNTA):
    # REGLA DE ORO: La prioridad absoluta es generar una PREGUNTA clara y directa en 'resumen_y_guia'.
    
    1. PRIORIDAD CONVERSACIONAL: Siempre busca obtener el dato mediante una pregunta abierta primero. 
    2. USO DE BOTONES (SECUNDARIO): El flag 'requiere_botones' solo se activará como un APOYO opcional, nunca como sustituto de la instrucción verbal.
    
    - requiere_botones = TRUE **ÚNICAMENTE** como apoyo en estos casos específicos:
        * Identificación: Ofrecer "Usar RUC" o "Usar DNI" DESPUÉS de haber preguntado por los datos.
        * Tipo Documento: Ofrecer "Emitir Factura" o "Emitir Boleta" solo si 'id_comprobante_tipo' es NULL.
        * Método de Pago: Ofrecer "Pago al Contado" o "Pago al Crédito" solo si 'tipo_operacion' es NULL.
        * Cierre: Ofrecer "🚀 Finalizar y Emitir" solo cuando los 3 bloqueantes estén en OK.

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

    response = client.chat.completions.create(
        model=MODELO_IA,
        messages=[{"role": "system", "content": prompt_pregunta}],
        response_format={"type": "json_object"}
    )
    
    resultado = json.loads(response.choices[0].message.content)
    
    return {
        "pregunta_casual": resultado["resumen_y_guia"],
        "requiere_botones": resultado["requiere_botones"],
        "btn1_id": resultado.get("btn1_id", ""),
        "btn1_title": resultado.get("btn1_title", ""),
        "btn2_id": resultado.get("btn2_id", ""),
        "btn2_title": resultado.get("btn2_title", "")
    }

# --- SERVICIO 3: CLASIFICADOR (OPTIMIZADO) ---
# Flujo del sistema: CONFIRMACION → registrador, luego preguntador | RESUMEN → generar-resumen | FINALIZAR → finalizar-operacion | INFORMACION → agente no implementado
@app.post("/clasificar-mensaje")
async def clasificar_mensaje(mensaje: str, wa_id: str = None, id_empresa: int = None):
    """
    Clasifica la intención del mensaje. Si se envían wa_id e id_empresa y existe registro en cache,
    se lee ultima_pregunta (retroalimentación o estado, ej. "IDENTIFICACION PENDIENTE") para mejorar el enrutado.
    """
    ultima_pregunta = ""
    if wa_id is not None and id_empresa is not None:
        try:
            params = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": str(wa_id), "id_empresa": int(id_empresa)}
            res = requests.get(URL_API, params=params)
            data = res.json().get("data", [])
            if data:
                registro = data[0]
                ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
        except Exception:
            pass

    ctx_ultima = f"""
    ### CONTEXTO (retroalimentación / estado de la última consulta al usuario):
    "{ultima_pregunta or '—'}"
    """ if ultima_pregunta else ""

    prompt_router = f"""
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
    
    try:
        response = client.chat.completions.create(
            model=MODELO_IA,
            messages=[{"role": "system", "content": prompt_router}],
            response_format={"type": "json_object"}
        )
        
        resultado = json.loads(response.choices[0].message.content)
        
        # Necesita extracción/analizador solo cuando la intención es actualizar (venta/compra ya no son intenciones)
        intencion = resultado.get("intencion", "")
        resultado['necesita_extraccion'] = intencion == "actualizar"
        
        # Mapear destino si la IA no lo devolvió (sin venta/compra)
        if "destino" not in resultado or not resultado["destino"]:
            mapeo = {
                "actualizar": "analizador",
                "confirmacion": "registrador",
                "resumen": "generar-resumen",
                "finalizar": "finalizar-operacion",
                "eliminar": "eliminar-operacion",
                "informacion": "informador",
                "casual": "casual"
            }
            resultado["destino"] = mapeo.get(intencion, "analizador")
        
        return resultado

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- SERVICIO 3B: INFORMADOR (guía de llenado con retroalimentación del estado del registro) ---
@app.post("/informador")
async def servicio_informador(mensaje: str, wa_id: str = None, id_empresa: int = None):
    """
    Responde preguntas de ayuda sobre cómo llenar datos en el flujo contable.
    Si se envían wa_id e id_empresa, se consulta el estado actual del registro (cache) y se inserta en el prompt para dar guía contextual.
    """
    estado_registro = ""
    if wa_id is not None and id_empresa is not None:
        try:
            params = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": str(wa_id), "id_empresa": id_empresa}
            res = requests.get(URL_API, params=params)
            data = res.json().get("data", [])
            if data:
                registro = data[0]
                estado_registro = json.dumps(registro, ensure_ascii=False, indent=0)
            else:
                estado_registro = "(No hay registro activo; el usuario puede estar por iniciar una operación.)"
        except Exception:
            estado_registro = "(No se pudo leer el estado actual del registro.)"
    else:
        estado_registro = "(No se proporcionó wa_id/id_empresa; no hay contexto de registro.)"

    prompt_info = f"""
    Eres el Agente de Información de MaravIA. El usuario tiene dudas sobre cómo registrar datos en el sistema. Responde de forma breve y clara, con guías de llenado. Usa el estado actual del registro (si existe) para dar una respuesta contextual: indica qué ya tiene y qué le falta.

    ### ESTADO ACTUAL DEL REGISTRO (retroalimentación para el prompt):
    {estado_registro}

    ### MENSAJE DEL USUARIO:
    "{mensaje}"

    ### GUÍA DE LLENADO (usa lo que aplique a la duda y al estado actual):
    - **ENTIDAD (Cliente/Proveedor):** RUC (11 dígitos), DNI (8 dígitos) o nombre/razón social. El sistema buscará en la base; si no está, puede indicar los datos para anotarlos sin identificar.
    - **PRODUCTOS:** Cantidad, nombre y precio. Ejemplo: "2 laptops a 1500 soles".
    - **COMPROBANTES:** Factura (RUC), Boleta (DNI), Recibo, Nota de Venta.
    - **MONEDA:** "En soles" o "en dólares" (S/ o $).
    - **PAGO:** "Contado" o "crédito". Si es crédito, cuotas o días.
    - **SUCURSAL / CENTRO DE COSTO / FORMA DE PAGO / CAJA-BANCO:** Nombres descriptivos.

    Responde en un solo bloque de texto, amigable para WhatsApp (saltos de línea, sin IDs numéricos). Si hay registro activo, menciona brevemente qué lleva y qué le falta; si no hay registro, ofrece un resumen de qué puede indicar en cada paso.
    """
    try:
        response = client.chat.completions.create(
            model=MODELO_IA,
            messages=[{"role": "system", "content": prompt_info}]
        )
        texto = (response.choices[0].message.content or "").strip()
        return {
            "status": "ok",
            "destino": "informador",
            "whatsapp_output": {"texto": texto or "Puedes indicarme, por ejemplo: cliente con RUC o DNI, productos con cantidad y precio, tipo de comprobante (Factura/Boleta) y si el pago es al contado o crédito."}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- SERVICIO 4: ELIMINACIÓN ---
@app.post("/eliminar-operacion")
async def eliminar_operacion(wa_id: str, id_empresa: int):
    payload = {"codOpe": "ELIMINAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": id_empresa}
    try:
        res = requests.post(URL_API, json=payload)
        resultado = res.json()
        if resultado.get('success'):
            return {
                "status": "borrado",
                "mensaje_usuario": "Entendido. He cancelado la operación y limpiado el borrador. ¿Deseas iniciar un registro nuevo?"
            }
        else:
            return {"status": "error", "mensaje": "No encontré ninguna operación activa para borrar."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- SERVICIO 5: RESUMEN ---
@app.get("/generar-resumen")
async def generar_resumen(wa_id: str, id_empresa: int):
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": id_empresa}
    res_db = requests.get(URL_API, params=params_leer)
    data = res_db.json().get('data', [])
    
    if not data:
        return {"resumen": "No tienes ninguna operación activa en este momento."}
    
    registro = data[0]
    cod_ope = registro.get('cod_ope', 'ventas')

    # --- LÓGICA DE AUDITORÍA (Pre-calculada para la IA) ---
    criticos = []
    if not registro.get('monto_total') or float(registro.get('monto_total', 0)) <= 0:
        criticos.append("Detalle de Productos/Montos")
    if not registro.get('entidad_id_maestro'):
        criticos.append("RUC/DNI del Cliente" if cod_ope == "ventas" else "RUC del Proveedor")
    if not registro.get('id_comprobante_tipo'):
        criticos.append("Tipo de Comprobante (Factura/Boleta)")

    opcionales = []
    if not registro.get('tipo_operacion'):
        opcionales.append("Método de Pago (Contado/Crédito)")
    if not registro.get('id_sucursal'):
        opcionales.append("Sucursal")

    txt_criticos = " | ".join(criticos) if criticos else "Ninguno"
    txt_opcionales = " | ".join(opcionales) if opcionales else "Ninguno"

    # --- PROMPT: misma plantilla que preguntador/analizador; solo datos definidos; diagnóstico con jerarquía ---
    prompt_resumen = f"""
    Eres el Auditor de MaravIA. Genera un resumen que use la PLANTILLA VISUAL compartida. Muestra ÚNICAMENTE las líneas para las que el dato exista en el registro (no null, no vacío, no 0). Lo que no muestres irá al diagnóstico.

    DATOS EN DB (JSON):
    {json.dumps(registro, ensure_ascii=False)}

    {PLANTILLA_VISUAL}

    ### JERARQUÍA PARA EL DIAGNÓSTICO (misma que preguntador y finalizar):
    **Indispensables** (los 3 deben estar completos): 1) Monto/Detalle (monto_total > 0 o productos_json con ítems), 2) Cliente/Proveedor (entidad + documento o cliente_id/entidad_id_maestro/proveedor_id), 3) Tipo comprobante (id_comprobante_tipo definido).
    **Opcionales:** tipo_operacion, forma_pago, sucursal, centro_costo, caja_banco, fecha_emision, etc.

    ### INSTRUCCIONES:
    - Resumen: Sigue la plantilla línea a línea; incluye SOLO las líneas cuyo "mostrar si" se cumpla con DATOS EN DB. No inventes valores.
    - Usa nombres (Factura, Soles, Cliente/Proveedor), nunca IDs numéricos.
    - Diagnóstico: Lista primero los indispensables que falten (1, 2, 3), luego opcionales. **Solo escribe "✅ Listo para confirmar y emitir" si los 3 indispensables están completos.** Si falta monto/detalle, cliente/proveedor o tipo comprobante, dilo en el diagnóstico; no digas que está listo.
    - Si entidad_numero_documento tiene valor, no cuentes "RUC/DNI" como faltante de identificación.
    """

    response = client.chat.completions.create(
        model=MODELO_IA,
        messages=[{"role": "system", "content": prompt_resumen}]
    )
    
    return {"resumen": response.choices[0].message.content}

# --- SERVICIO 6: IDENTIFICADOR (actualiza metadata_ia.dato_identificado y ultima_pregunta = "IDENTIFICACION PENDIENTE") ---
def _sin_nulos(d):
    """Devuelve un dict solo con claves cuyo valor no es None, vacío ni 'null'."""
    if not isinstance(d, dict):
        return d
    return {k: v for k, v in d.items() if v is not None and v != "" and v != "null" and (not isinstance(v, str) or v.strip())}

@app.post("/identificar-entidad")
async def identificar_entidad(wa_id: str, tipo_ope: str, termino: str, id_empresa: int):
    try:
        data_cli = None
        data_prov = None
        
        # 1. BÚSQUEDA (Mantenemos la lógica dual)
        r_c = requests.get(URL_CLIENTE, params={"codOpe": "BUSCAR_CLIENTE", "empresa_id": id_empresa, "termino": termino}).json()
        if r_c.get('found'): data_cli = r_c['data']

        r_p = requests.post(URL_PROVEEDOR, json={"codOpe": "BUSCAR_PROVEEDOR", "id_empresa": id_empresa, "nombre_completo": termino}).json()
        if r_p.get('found'): data_prov = r_p['data']

        if not data_cli and not data_prov:
            # No identificado en base: invitar a llenar el campo sin identificar (nombre + documento) para poder registrar al finalizar
            rol = "cliente" if (tipo_ope or "").lower() == "ventas" else "proveedor"
            return {
                "identificado": False,
                "mensaje": (
                    f"❌ No encontré ese RUC/DNI o nombre en la base de {rol}es.\n\n"
                    f"Puedes *llenar el campo sin identificar*: indícame el **nombre o razón social** y el **número de documento** (RUC o DNI) "
                    f"y lo anotaré para continuar. Al finalizar la operación podré registrarlo si es necesario.\n\n"
                    f"Ejemplo: «Razón Social SAC, RUC 20123456789» o «Juan Pérez, DNI 12345678»."
                ),
                "sugiere_llenar_sin_identificar": True,
            }

        # 2. CONSOLIDACIÓN DE DATOS (Prioridad Proveedor si es compra, Cliente si es venta)
        base = data_prov if (tipo_ope == "compras" and data_prov) else (data_cli if data_cli else data_prov)
        
        # 3. EXTRACCIÓN DE CAMPOS (Con manejo de vacíos para mensaje usuario)
        def clean(val): return str(val).strip() if val and str(val).strip() not in ["None", "null", ""] else "_No registrado_"

        nombre_entidad = clean(base.get('razon_social') or base.get('nombre_completo'))
        doc_identidad = clean(base.get('ruc') or base.get('numero_documento'))
        tipo_doc_txt  = clean(base.get('tipo_documento_nombre') or ("RUC" if len(str(doc_identidad).replace("_No registrado_", "")) == 11 else "DNI"))
        correo_ent    = clean(base.get('correo'))
        telf_ent      = clean(base.get('telefono'))
        dir_ent       = clean(base.get('direccion'))
        comercial     = clean(base.get('nombre_comercial'))
        
        # Determinación de Rol
        roles = []
        if data_cli: roles.append("Cliente")
        if data_prov: roles.append("Proveedor")
        rol_txt = " / ".join(roles)

        # 4. MENSAJE VISUAL PARA EL USUARIO (WhatsApp)
        mensaje_bot = (
            f"✅ *FICHA DE IDENTIDAD LOCALIZADA*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Nombre/Razón:* {nombre_entidad}\n"
            f"🏪 *N. Comercial:* {comercial}\n"
            f"🆔 *{tipo_doc_txt}:* {doc_identidad}\n"
            f"💼 *Rol:* {rol_txt}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📧 *Correo:* {correo_ent}\n"
            f"📞 *Teléfono:* {telf_ent}\n"
            f"📍 *Dirección:* {dir_ent}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"¿Los datos son correctos para continuar con la operación de *{tipo_ope.upper()}*?"
        )

        # 5. IDs y datos técnicos — mismos nombres que el analizador/registro (nombres e IDs permitidos)
        tipo_ope_norm = (tipo_ope or "").lower().strip()
        p_id = (data_cli or data_prov).get('persona_id')
        c_id = data_cli.get('cliente_id') if data_cli else None
        pr_id = data_prov.get('proveedor_id') if data_prov else None
        # entidad_id_maestro: lo usa finalizar y generar-pregunta (ventas → cliente_id, compras → proveedor_id)
        entidad_id_maestro = (c_id if tipo_ope_norm == "ventas" else None) or (pr_id if tipo_ope_norm == "compras" else None) or p_id

        doc_raw = base.get('ruc') or base.get('numero_documento') or ""
        entidad_id_tipo_documento = 6 if len(str(doc_raw).strip()) == 11 else 1  # RUC=6, DNI=1
        nombre_entidad_limpio = (base.get('razon_social') or base.get('nombre_completo') or "").strip() or None
        doc_limpio = (doc_raw and str(doc_raw).strip()) or None
        if nombre_entidad_limpio is None and nombre_entidad != "_No registrado_":
            nombre_entidad_limpio = nombre_entidad
        if doc_limpio is None and doc_identidad != "_No registrado_":
            doc_limpio = doc_identidad

        # 6. Propuesta de identidad con los mismos nombres que el analizador/registro (solo no nulos)
        propuesta_identidad = _sin_nulos({
            "cod_ope": tipo_ope_norm or None,
            "entidad_nombre": nombre_entidad_limpio,
            "entidad_numero_documento": doc_limpio,
            "entidad_id_tipo_documento": entidad_id_tipo_documento,
            "entidad_id_maestro": entidad_id_maestro,
            "persona_id": p_id,
            "cliente_id": c_id,
            "proveedor_id": pr_id,
        })

        # 7. Obtener cache actual y metadata_ia (estructura { dato_registrado, dato_identificado })
        params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": id_empresa}
        res_cache = requests.get(URL_API, params=params_leer)
        data_cache = res_cache.json().get("data", [])
        registro_actual = data_cache[0] if data_cache else {}
        raw_metadata = registro_actual.get("metadata_ia") or "{}"
        try:
            metadata_ia = json.loads(raw_metadata) if raw_metadata.strip() else {}
        except Exception:
            metadata_ia = {}
        dato_registrado = metadata_ia.get("dato_registrado") or {}
        # Si no hay metadata_ia previa (cache antiguo), reconstruir dato_registrado desde campos planos
        if not dato_registrado and registro_actual:
            prod = registro_actual.get("productos_json")
            if isinstance(prod, str):
                try:
                    prod = json.loads(prod) if (prod or "").strip() else []
                except Exception:
                    prod = []
            dato_registrado = _sin_nulos({
                "cod_ope": registro_actual.get("cod_ope"),
                "entidad_nombre": registro_actual.get("entidad_nombre"),
                "entidad_numero_documento": registro_actual.get("entidad_numero_documento"),
                "entidad_id_tipo_documento": registro_actual.get("entidad_id_tipo_documento"),
                "id_moneda": registro_actual.get("id_moneda"),
                "id_comprobante_tipo": registro_actual.get("id_comprobante_tipo"),
                "tipo_operacion": registro_actual.get("tipo_operacion"),
                "monto_total": registro_actual.get("monto_total"),
                "monto_base": registro_actual.get("monto_base"),
                "monto_impuesto": registro_actual.get("monto_impuesto"),
                "productos_json": prod,
            })
        metadata_ia["dato_identificado"] = _sin_nulos(propuesta_identidad)
        metadata_ia["dato_registrado"] = dato_registrado

        # 8. ACTUALIZAR CACHÉ: metadata_ia, ultima_pregunta y campos planos de identidad (para resumen/finalizar)
        payload_cache = {
            "codOpe": "ACTUALIZAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_empresa": id_empresa,
            "metadata_ia": json.dumps(metadata_ia, ensure_ascii=False),
            "ultima_pregunta": "IDENTIFICACION PENDIENTE",
        }
        for key in ("cod_ope", "entidad_nombre", "entidad_numero_documento", "entidad_id_tipo_documento",
                    "entidad_id_maestro", "persona_id", "cliente_id", "proveedor_id"):
            val = propuesta_identidad.get(key)
            if val is not None and val != "" and (not isinstance(val, str) or val.strip()):
                payload_cache[key] = val
        requests.post(URL_API, json=payload_cache)

        return {
            "identificado": True,
            "mensaje": mensaje_bot,
            "ids": {"p_id": p_id, "c_id": c_id, "pr_id": pr_id},
            "metadata_ia": metadata_ia,
        }

    except Exception as e:
        return {"identificado": False, "mensaje": f"💥 Error técnico: {str(e)}"}

# --- CONFIGURACIÓN DE URLS ---
URL_VENTA_SUNAT = "https://api.maravia.pe/servicio/ws_ventas.php"
TOKEN = os.getenv("TOKEN_SUNAT")


def _registrar_cliente(reg: dict, id_empresa: int) -> dict:
    """
    REGISTRAR_CLIENTE vía ws_cliente.php.
    Persona Natural (tipo_persona=1): nombres, apellido_paterno, id_tipo_documento, numero_documento.
    Persona Juridica (tipo_persona=2): razon_social, id_tipo_documento, ruc.
    Opcionales: telefono, correo, direccion, etc.
    Retorna: {success, message, cliente_id, persona_id, data} -> se usa cliente_id para CREAR_VENTA.
    """
    id_tipo = reg.get("entidad_id_tipo_documento") or (6 if len(str(reg.get("entidad_numero_documento") or "").strip()) == 11 else 1)
    numero_doc = (reg.get("entidad_numero_documento") or "").strip()
    nombre = (reg.get("entidad_nombre") or "").strip() or "Sin nombre"
    es_ruc = id_tipo == 6
    payload = {"codOpe": "REGISTRAR_CLIENTE", "empresa_id": id_empresa}
    if es_ruc:
        payload["tipo_persona"] = 2
        payload["razon_social"] = nombre
        payload["id_tipo_documento"] = id_tipo
        payload["ruc"] = numero_doc
    else:
        payload["tipo_persona"] = 1
        payload["nombres"] = nombre
        payload["apellido_paterno"] = "."
        payload["id_tipo_documento"] = id_tipo
        payload["numero_documento"] = numero_doc
    for k in ("telefono", "correo", "direccion", "nombre_comercial", "representante_legal"):
        if reg.get(k):
            payload[k] = reg[k]
    try:
        r = requests.post(URL_CLIENTE, json=payload, timeout=15)
        return r.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


def _actualizar_cliente(cliente_id: int, reg: dict, id_empresa: int) -> dict:
    """
    ACTUALIZAR_CLIENTE. Requerido: cliente_id. Actualizables: nombres, apellido_paterno, id_tipo_documento,
    numero_documento, telefono, correo, direccion, razon_social, ruc, etc.
    """
    payload = {"codOpe": "ACTUALIZAR_CLIENTE", "cliente_id": cliente_id, "empresa_id": id_empresa}
    for k in ("nombres", "apellido_paterno", "apellido_materno", "id_tipo_documento", "numero_documento",
              "telefono", "correo", "direccion", "razon_social", "nombre_comercial", "ruc", "representante_legal"):
        if reg.get(k) is not None and reg.get(k) != "":
            payload[k] = reg[k]
    if reg.get("entidad_nombre") and "nombres" not in payload and "razon_social" not in payload:
        payload["razon_social"] = reg["entidad_nombre"]
    if reg.get("entidad_numero_documento"):
        payload.setdefault("numero_documento", reg["entidad_numero_documento"])
        payload.setdefault("ruc", reg["entidad_numero_documento"])
    try:
        r = requests.post(URL_CLIENTE, json=payload, timeout=15)
        return r.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


# --- SERVICIO 7: FINALIZAR Y GENERAR PDF (campos como test_pdf_sunat; registrar cliente si no existe) ---
@app.post("/finalizar-operacion")
async def finalizar_operacion(wa_id: str, id_empresa: int):
    # 1. Obtener datos del historial (Cache)
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": id_empresa}
    res_db = requests.get(URL_API, params=params_leer)
    data_db = res_db.json().get('data', [])
    
    if not data_db:
        return {"status": "error", "mensaje": "No hay una operación activa para finalizar."}
    
    reg = data_db[0]
    tipo_ope = str(reg.get('cod_ope', 'VENTAS')).upper()
    
    # 2. Datos indispensables (alineados a test_pdf_sunat y CREAR_VENTA)
    monto_total = reg.get('monto_total')
    monto_base = reg.get('monto_base')
    monto_igv = reg.get('monto_impuesto')
    tipo_comp = reg.get('id_comprobante_tipo')
    moneda_simbolo = reg.get('moneda_simbolo', 'S/')
    # id_cliente: obligatorio para ventas; puede venir de identificador o registrarse ahora
    id_cliente = reg.get('cliente_id') or reg.get('entidad_id_maestro')

    # 3. Validación mínima
    errores = []
    if not monto_total or float(monto_total) <= 0:
        errores.append("Monto total")
    if not tipo_comp:
        errores.append("Tipo de Comprobante (Boleta/Factura)")
    if "VENTA" in tipo_ope and not id_cliente:
        # Si no hay cliente registrado pero tenemos datos para registrarlo
        if (reg.get('entidad_nombre') or "").strip() and (reg.get('entidad_numero_documento') or "").strip():
            pass  # Se registrará más abajo
        else:
            errores.append("Cliente (RUC/DNI y nombre) para facturar")
    if errores and not ("VENTA" in tipo_ope and (reg.get('entidad_nombre') and reg.get('entidad_numero_documento'))):
        return {
            "status": "incompleto",
            "mensaje": f"⚠️ *No se puede finalizar.*\n\nFaltan: **{', '.join(errores)}**."
        }

    try:
        # --- VENTAS: apartado actualizar y/o registrar cliente (id_cliente obligatorio para CREAR_VENTA) ---
        if "VENTA" in tipo_ope:
            # Registrar cliente: si no hay id_cliente pero sí nombre + documento, REGISTRAR_CLIENTE
            if not id_cliente and (reg.get('entidad_nombre') or "").strip() and (reg.get('entidad_numero_documento') or "").strip():
                resp_cli = _registrar_cliente(reg, id_empresa)
                if resp_cli.get("success") and resp_cli.get("cliente_id"):
                    id_cliente = resp_cli["cliente_id"]
                else:
                    return {
                        "status": "error",
                        "mensaje": f"❌ No se pudo registrar el cliente: {resp_cli.get('message', 'Error desconocido')}."
                    }
            # Actualizar cliente: si ya hay id_cliente y el cache tiene datos (nombre, doc, teléfono, etc.), ACTUALIZAR_CLIENTE
            if id_cliente and (reg.get('entidad_nombre') or reg.get('entidad_numero_documento')):
                resp_act = _actualizar_cliente(id_cliente, reg, id_empresa)
                if not resp_act.get("success"):
                    pass  # No bloqueamos la venta; solo no se actualizó la ficha del cliente
            if not id_cliente:
                return {"status": "incompleto", "mensaje": "⚠️ Falta el cliente (RUC/DNI y nombre). Indica los datos para registrarlo o búscalos en la base."}

            # Detalle: mismo formato que test_pdf_sunat (indispensables para CREAR_VENTA)
            productos = []
            try:
                pj = reg.get("productos_json")
                if isinstance(pj, str):
                    productos = json.loads(pj) if pj.strip() else []
                elif isinstance(pj, list):
                    productos = pj
            except Exception:
                productos = []
            if not productos:
                mt = float(monto_total)
                mb = float(monto_base or mt / 1.18)
                mi = float(monto_igv or mt - mb)
                detalle_items = [{
                    "id_inventario": reg.get("id_inventario", 7),
                    "cantidad": 1,
                    "precio_unitario": mt,
                    "valor_subtotal_item": round(mb, 2),
                    "valor_igv": round(mi, 2),
                    "valor_total_item": mt,
                    "id_tipo_producto": 2
                }]
            else:
                detalle_items = []
                for p in productos:
                    qty = float(p.get("cantidad", 1))
                    pu = float(p.get("precio_unitario") or p.get("precio", 0))
                    total_item = float(p.get("total_item", qty * pu))
                    subtotal = total_item / 1.18
                    igv = total_item - subtotal
                    detalle_items.append({
                        "id_inventario": reg.get("id_inventario", 7),
                        "cantidad": qty,
                        "precio_unitario": pu,
                        "valor_subtotal_item": round(subtotal, 2),
                        "valor_igv": round(igv, 2),
                        "valor_total_item": round(total_item, 2),
                        "id_tipo_producto": 2
                    })

            payload_venta = {
                "codOpe": "CREAR_VENTA",
                "id_usuario": reg.get("id_usuario", 3),
                "id_cliente": id_cliente,
                "id_sucursal": reg.get("id_sucursal", 14),
                "id_moneda": reg.get("id_moneda", 1),
                "id_forma_pago": reg.get("id_forma_pago", 9),
                "tipo_venta": (reg.get("tipo_operacion") or "Contado").capitalize(),
                "fecha_emision": reg.get("fecha_emision") or "2026-03-03",
                "tipo_facturacion": "facturacion_electronica",
                "id_tipo_comprobante": tipo_comp,
                "detalle_items": detalle_items
            }

            headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
            res_sunat = requests.post(URL_VENTA_SUNAT, json=payload_venta, headers=headers)
            res_json = res_sunat.json()

            url_pdf = res_json.get('data', {}).get('url_pdf')

            if url_pdf:
                return {
                    "status": "finalizado",
                    "mensaje_completo": (
                        f"✨ *¡VENTA REGISTRADA EN SUNAT!*\n\n"
                        f"👤 *Cliente:* {reg.get('entidad_nombre')}\n"
                        f"💰 *Total:* {moneda_simbolo} {monto_total}\n"
                        f"📄 *Documento:* {reg.get('comprobante_serie', 'F001')}-{reg.get('comprobante_numero', '000')}\n\n"
                        f"🔗 *Descargar Comprobante:* {url_pdf}"
                    )
                }
            return {
                "status": "error",
                "mensaje": f"❌ Error SUNAT: {res_json.get('message', 'No se pudo generar el PDF.')}"
            }

        # --- COMPRAS (registro local / resumen) ---
        return {
            "status": "finalizado",
            "mensaje_completo": (
                f"✅ *COMPRA REGISTRADA EXITOSAMENTE*\n\n"
                f"🏢 *Proveedor:* {reg.get('entidad_nombre')}\n"
                f"💰 *Monto:* {moneda_simbolo} {monto_total}\n"
                f"📝 *Estado:* Guardado en el historial de {tipo_ope.lower()}."
            )
        }

    except Exception as e:
        return {"status": "error", "mensaje": f"Hubo un fallo técnico: {str(e)}"}

# --- SERVICIO 8: CEREBRO UNIFICADO (S1 + S2) ---
@app.post("/unificado")
async def servicio_8_unificado(wa_id: str, mensaje: str, id_empresa: int):


    # 1. Obtener estado actual (Contexto para la IA)
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": id_empresa}
    res_db = requests.get(URL_API, params=params_leer)
    data_db = res_db.json().get('data', [])
    estado_actual = data_db[0] if data_db else {}
    es_registro_nuevo = len(data_db) == 0

    contexto_operacion = estado_actual.get('cod_ope', 'compras')
    ultima_pregunta_bot = estado_actual.get('ultima_pregunta', '')

    prompt_unico = f"""
    Eres el Cerebro Contable de MaravIA. Tu misión es procesar el mensaje para actualizar la DB y generar la respuesta visual.

    ### 1. CONTEXTO
    - OPERACIÓN ACTUAL: {contexto_operacion.upper()}
    - DATOS EN DB: {json.dumps(estado_actual, ensure_ascii=False)}
    - ÚLTIMA GUÍA ENVIADA: "{ultima_pregunta_bot}"
    - MENSAJE RECIBIDO: "{mensaje}"

    ### 2. REGLAS DE EXTRACCIÓN Y NORMALIZACIÓN (DB)
    - **CAMBIO DE FLUJO**: Si el usuario pide cambiar (ej: "es una compra", "cambia a venta"), actualiza 'cod_ope'.
    - **PRODUCTOS (CRÍTICO)**: 
        1. Estructura: {{"cantidad": float, "nombre": str, "precio_unitario": float, "total_item": float}}.
        2. ACUMULA si hay nuevos productos, REEMPLAZA solo si el usuario corrige (ej: "No, solo era...").
        3. Si no hay precio, usa el histórico de la DB o 0.0.
    - **CÁLCULOS**: monto_total = Σ(total_item). monto_base = total / 1.18. monto_impuesto = total - base.
    - **IDENTIFICACIÓN**: 
        1. DNI (8 dígitos) -> id: 1. RUC (11 dígitos) -> id: 6.
        2. Si recibes un número, guárdalo en 'entidad_numero_documento' y pon 'requiere_identificacion': true.
    - **NORMALIZACIÓN ESTRICTA**:
        * id_comprobante_tipo: FACTURA=1, BOLETA=2, RECIBO=3.
        * id_moneda: SOLES=1, DÓLARES=2.
        * tipo_operacion: "contado" o "credito".
        * id_centro_costo: 1 (General).
        * sucursal_nombre: Extraer ubicación si se menciona, si no, mantener la de DB.

    ### 3. MATRIZ DE PRIORIDAD (DIAGNÓSTICO)
    Sigue este orden y DETENTE en el primer campo faltante para la PREGUNTA:
    1. **PRODUCTOS**: Si 'monto_total' es 0.
    2. **ENTIDAD (Regla de Salto)**: Si 'entidad_numero_documento' tiene valor Y 'entidad_id_tipo_documento' es (1 o 6), SÁLTALO inmediatamente aunque no haya nombre (está en proceso).
    3. **COMPROBANTE**: Si 'id_comprobante_tipo' es NULL o 0. Si ya tiene valor, SALTA.
    4. **PAGO**: Si 'tipo_operacion' no es "contado" o "credito".
    5. **FINALIZACIÓN**: Todo OK.

    ### 4. REGLAS DE RESPUESTA VISUAL (WHATSAPP) — solo datos definidos
    - Incluye en 'resumen_y_guia' ÚNICAMENTE las líneas para las que el dato exista en datos_db (no null, no vacío, no 0). Si un campo no está definido, no escribas esa línea.
    - Estructura (misma plantilla que preguntador/resumen): 📄 comprobante | 👤 Cliente/Proveedor + 🆔 DNI/RUC | 📦 Detalle (productos) | 💰 Subtotal, IGV, TOTAL | 📍 Sucursal, 💳 Pago, 💵 Moneda. Sin IDs numéricos; usa nombres.

    ### 

    LA GUÍA ('resumen_y_guia') unificado en un str:
    aquí se almacena los 4 campos que deben enviarse en 'resumen_y_guia'. La intención de esta variable es generar una pregunta contextualizada.
    1. RESUMEN: conforme a la estructura de RESPUESTA VISUAL
    2. RETROALIMENTACIÓN: Confirma el último cambio (Ej: "Factura configurada").
    3. DIAGNÓSTICO: Identifica qué falta según la MATRIZ DE PRIORIDAD.
    4. PREGUNTA: Haz la pregunta para llenar el dato que falta.

    RESPONDE ESTRICTAMENTE EN ESTE FORMATO JSON:
    {{
        "datos_db": {{
            "cod_ope": "ventas" o "compras",
            "entidad_nombre": str, 
            "entidad_id_tipo_documento": int o null,
            "id_comprobante_tipo": int, 
            "monto_total": float, 
            "monto_base": float, 
            "monto_impuesto": float,
            "productos_json": [
                {{
                    "cantidad": float,
                    "nombre": str,
                    "precio_unitario": float,
                    "total_item": float
                }}
            ],
            "tipo_operacion": "contado" o "credito", 
            "id_moneda": int,
            "id_sucursal": int o null,
            "id_centro_costo": 1,
            "ultima_pregunta": "Breve resumen de la acción realizada (Ej: 'Se agregaron 2 productos por S/ 45.00')"
        }},
        "respuesta_usuario": {{
            "resumen_y_guia": str, "requiere_botones": bool, "btn1_id": str, "btn1_title": str, "btn2_id": str, "btn2_title": str
        }}
    }}
    """

    # 2. Llamada única a la IA
    response = client.chat.completions.create(
        model=MODELO_IA,
        messages=[{"role": "system", "content": prompt_unico}],
        response_format={"type": "json_object"}
    )
    
    output = json.loads(response.choices[0].message.content)
    cambios_db = output["datos_db"]
    guiado = output["respuesta_usuario"]

    # 3. Escritura en DB
    payload = {
        "codOpe": "INSERTAR_CACHE" if es_registro_nuevo else "ACTUALIZAR_CACHE",
        "ws_whatsapp": wa_id,
        "id_empresa": id_empresa,
        **{k: v for k, v in cambios_db.items() if v is not None}
    }
    requests.post(URL_API, json=payload)

    # 4. Retorno unificado para el bot
    return {
        "status": "sincronizado",
        "requiere_identificacion": cambios_db.get('requiere_identificacion', False),
        "datos_entidad": {
            "termino": cambios_db.get('entidad_numero_documento') or cambios_db.get('entidad_nombre') or "",
            "tipo_ope": cambios_db.get('cod_ope'),
            "tipo_doc": cambios_db.get('entidad_id_tipo_documento')
        },
        "whatsapp_output": {
            "texto": guiado["resumen_y_guia"],
            "botones": {
                "activar": guiado["requiere_botones"],
                "b1": {"id": guiado.get("btn1_id"), "title": guiado.get("btn1_title")},
                "b2": {"id": guiado.get("btn2_id"), "title": guiado.get("btn2_title")}
            }
        }
    }

@app.post("/analizador")
async def servicio_analizador(wa_id: str, mensaje: str, id_empresa: int):
    # 1. Obtener estado actual
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": str(wa_id), "id_empresa": id_empresa}
    res_db = requests.get(URL_API, params=params_leer)
    data_db = res_db.json().get('data', [])
    estado_actual = data_db[0] if data_db else {}
    # Si ya existe fila en la tabla (data_db tiene al menos un registro), siempre ACTUALIZAR para no duplicar
    es_registro_nuevo = len(data_db) == 0

    # Definición de contexto: NO asumir venta/compra ni tipo comprobante/moneda/pago si el usuario no lo indicó
    # Solo usar "compras"/"ventas" cuando el mensaje lo diga o ya exista en el registro
    contexto_previo = None
    if estado_actual and (estado_actual.get("cod_ope") or "").strip():
        contexto_previo = (estado_actual.get("cod_ope") or "").strip().lower()
    if not contexto_previo and any(x in mensaje.lower() for x in ["compr", "gasto"]):
        contexto_previo = "compras"
    if not contexto_previo and any(x in mensaje.lower() for x in ["vent", "venta", "vender", "vendiendo"]):
        contexto_previo = "ventas"

    ultima_pregunta_enviada = estado_actual.get("ultima_pregunta") or ""
    if len(ultima_pregunta_enviada) > 800:
        ultima_pregunta_enviada = ultima_pregunta_enviada[:800] + "..."

    # 2. PROMPT (retroalimentación de última pregunta + tercer bloque requiere_identificacion)
    prompt_analisis = f"""
    Eres el Analizador Experto de MaravIA. Tu misión es extraer datos contables y generar un resumen visual humano y profesional.

    ### RETROALIMENTACIÓN — ÚLTIMA PREGUNTA O MENSAJE ENVIADO AL USUARIO:
    (Úsala para interpretar si el mensaje actual es una corrección, respuesta o cambio respecto a lo que se le mostró.)
    "{ultima_pregunta_enviada or 'Ninguna aún.'}"

    ### REGLAS DE EXTRACCIÓN TÉCNICA:
    - cod_ope: solo "ventas" o "compras" si el usuario lo dice o ya está en el registro; si no está definido, deja null (no asumir).
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

    ### REGLAS PARA EL RESUMEN VISUAL (resumen_visual) — solo lo extraído en ESTE mensaje:
    {PLANTILLA_VISUAL}

    {REGLAS_NORMALIZACION}

    **Regla crítica del analizador:** El resumen_visual debe mostrar ÚNICAMENTE los apartados para los que hay dato en tu propuesta_cache (lo que extrajiste de este mensaje). Si el usuario solo registró productos, despliega solo el detalle de productos (y monto/total si aplica); NO muestres encabezado compra/venta (🛒/📤), ni comprobante, ni cliente/proveedor, ni moneda/pago si están vacíos en la propuesta. Los apartados sin dato en esta extracción no se despliegan aquí (el preguntador sí los mostrará después si ya están en el registro).
    **Caso solo compra/venta:** Si la propuesta solo tiene cod_ope (compras o ventas) y el resto vacío, el resumen_visual debe ser SOLO: línea 🛒 *COMPRA* o 📤 *VENTA* + una pregunta de confirmación ("¿Es correcto que deseas registrar una compra/venta? Indica los datos cuando quieras."). NO escribas "Aún no hay datos capturados" ni listes lo que falta (cliente, comprobante, productos); solo confirmación de intención.
    Para cada línea, comprueba en tu propuesta_cache si el campo indicado en "mostrar si" tiene valor (no null, no vacío, no 0). Si no lo extrajiste, no escribas esa línea. Aplica las reglas de normalización: nunca IDs; usa solo lenguaje natural. Tras el mensaje de entendimiento, el resumen debe terminar con una pregunta de confirmación natural.

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
        "resumen_visual": "Ejemplo (incluir primero 🛒 COMPRA o 📤 VENTA si cod_ope está definido):\\n🛒 *COMPRA*\\n━━━\\n¿Es correcto? Indica los datos cuando quieras. O: 📄 Factura... 👤 Cliente... 💰 Total... ¿Todo correcto?",
        "requiere_identificacion": {{
            "activo": false,
            "termino": "",
            "tipo_ope": "ventas o compras",
            "mensaje": "Texto breve para el usuario al buscar (solo si activo true)"
        }}
    }}
    """

    response = client.chat.completions.create(
        model=MODELO_IA,
        messages=[{"role": "system", "content": prompt_analisis}],
        response_format={"type": "json_object"}
    )

    try:
        output_ia = json.loads(response.choices[0].message.content)
        propuesta = output_ia.get("propuesta_cache", {})
        mensaje_entendimiento = (output_ia.get("mensaje_entendimiento") or "").strip()
        resumen_visual = output_ia.get("resumen_visual", "")
        if mensaje_entendimiento:
            resumen_visual = f"{mensaje_entendimiento}\n\n{resumen_visual}".strip()
        req_id = output_ia.get("requiere_identificacion") or {}
        requiere_identificacion = {
            "activo": bool(req_id.get("activo")),
            "termino": (req_id.get("termino") or "").strip(),
            "tipo_ope": req_id.get("tipo_ope") or contexto_previo,
            "mensaje": (req_id.get("mensaje") or "").strip()
        }
        if requiere_identificacion["activo"] and not requiere_identificacion["termino"]:
            requiere_identificacion["activo"] = False

        # --- PREPARACIÓN PARA LA DB ---

        # 1. productos_json: Se envía como String JSON (Requisito PHP)
        productos_str = json.dumps(propuesta.get("productos_json", []), ensure_ascii=False)

        # Función auxiliar para decidir qué valor usar
        def obtener_valor(campo, default=None):
            nuevo = propuesta.get(campo)
            viejo = estado_actual.get(campo)
            
            # Si la IA envía un valor válido (no nulo, no vacío, no 0), lo usamos
            if nuevo not in [None, "", 0, "null"]:
                return nuevo
            # Si no, mantenemos el valor que ya estaba en la DB
            return viejo if viejo not in [None, "", 0, "null"] else default

        def es_valor_no_nulo(v):
            """True si el valor debe incluirse en el payload (solo registrar datos no nulos)."""
            if v is None:
                return False
            if isinstance(v, str) and v.strip() == "":
                return False
            if v == "null":
                return False
            return True

        # Construir payload solo con datos no nulos (evitar sobrescribir con vacíos)
        payload_base = {
            "codOpe": "INSERTAR_CACHE" if es_registro_nuevo else "ACTUALIZAR_CACHE",
            "ws_whatsapp": str(wa_id),
            "id_empresa": int(id_empresa),
            "cod_ope": obtener_valor("cod_ope", contexto_previo),
            "entidad_nombre": obtener_valor("entidad_nombre", ""),
            "entidad_numero_documento": obtener_valor("entidad_numero_documento", ""),
            "entidad_id_tipo_documento": propuesta.get("entidad_id_tipo_documento") or estado_actual.get("entidad_id_tipo_documento"),
            "id_moneda": obtener_valor("id_moneda", None),
            "id_comprobante_tipo": obtener_valor("id_comprobante_tipo", None),
            "tipo_operacion": obtener_valor("tipo_operacion", None),
            "monto_total": float(propuesta.get("monto_total") or estado_actual.get("monto_total") or 0),
            "monto_base": float(propuesta.get("monto_base") or estado_actual.get("monto_base") or 0),
            "monto_impuesto": float(propuesta.get("monto_impuesto") or estado_actual.get("monto_impuesto") or 0),
            "productos_json": productos_str,
            "paso_actual": 2,
            "is_ready": 0
        }
        payload_db = {k: v for k, v in payload_base.items() if es_valor_no_nulo(v)}

        # 2. metadata_ia: fusionar dato_registrado previo con lo nuevo (cambio compra↔venta y demás no deben perder datos)
        try:
            metadata_prev = json.loads(estado_actual.get("metadata_ia") or "{}")
            dato_identificado_existente = metadata_prev.get("dato_identificado") or {}
            dato_registrado_prev = metadata_prev.get("dato_registrado") or {}
        except Exception:
            dato_identificado_existente = {}
            dato_registrado_prev = {}
        # Productos: si la IA no envió ítems en esta extracción, no sobrescribir (se conserva lo previo en la fusión)
        productos_propuesta = propuesta.get("productos_json") or []
        tiene_productos_nuevos = isinstance(productos_propuesta, list) and len(productos_propuesta) > 0
        nuevo_parcial = _sin_nulos({
            "cod_ope": payload_base.get("cod_ope"),
            "entidad_nombre": payload_base.get("entidad_nombre"),
            "entidad_numero_documento": payload_base.get("entidad_numero_documento"),
            "entidad_id_tipo_documento": payload_base.get("entidad_id_tipo_documento"),
            "id_moneda": payload_base.get("id_moneda"),
            "id_comprobante_tipo": payload_base.get("id_comprobante_tipo"),
            "tipo_operacion": payload_base.get("tipo_operacion"),
            "monto_total": payload_base.get("monto_total"),
            "monto_base": payload_base.get("monto_base"),
            "monto_impuesto": payload_base.get("monto_impuesto"),
            **({"productos_json": productos_propuesta} if tiene_productos_nuevos else {}),
        })
        # Fusión: lo previo + lo nuevo (lo nuevo sobrescribe). Así "es una venta" actualiza cod_ope sin borrar productos/resto
        dato_registrado = _sin_nulos({**dato_registrado_prev, **nuevo_parcial})
        metadata_ia = {"dato_registrado": dato_registrado, "dato_identificado": dato_identificado_existente}
        payload_db["metadata_ia"] = json.dumps(metadata_ia, ensure_ascii=False)

        # 3. ultima_pregunta: solo retroalimentación de la última consulta (no JSON técnico)
        retroalimentacion = (mensaje_entendimiento or "Propuesta actualizada. Revisa el resumen arriba.").strip()
        payload_db["ultima_pregunta"] = retroalimentacion

        # Siempre incluir campos obligatorios del API (y cod_ope cuando exista, para que el cache quede actualizado)
        payload_db["codOpe"] = payload_base["codOpe"]
        payload_db["ws_whatsapp"] = payload_base["ws_whatsapp"]
        payload_db["id_empresa"] = payload_base["id_empresa"]
        payload_db["paso_actual"] = 2
        payload_db["is_ready"] = 0
        if payload_base.get("cod_ope") and str(payload_base.get("cod_ope")).strip():
            payload_db["cod_ope"] = str(payload_base["cod_ope"]).strip().lower()

        # 4. EJECUCIÓN
        headers = {'Content-Type': 'application/json'}
        res_post = requests.post(URL_API, data=json.dumps(payload_db, ensure_ascii=False).encode('utf-8'), headers=headers)
        
        # 5. Respuesta: texto para WhatsApp + bloque para el bot de identidad (termino, tipo_ope, mensaje)
        out = {
            "status": "analizado_y_guardado",
            "db_res": res_post.json(),
            "whatsapp_output": {"texto": resumen_visual},
            "requiere_identificacion": requiere_identificacion
        }
        if requiere_identificacion["activo"]:
            out["datos_entidad"] = {
                "termino": requiere_identificacion["termino"],
                "tipo_ope": requiere_identificacion["tipo_ope"],
                "mensaje": requiere_identificacion["mensaje"] or f"Buscando '{requiere_identificacion['termino']}' en {'clientes' if requiere_identificacion['tipo_ope'] == 'ventas' else 'proveedores'}..."
            }
        return out

    except Exception as e:
        return {"status": "error", "detalle": str(e)}
    
@app.post("/registrador")
async def servicio_registrador(wa_id: str, id_empresa: int):
    """
    Se dispara cuando el usuario confirma con un "Sí" claro.
    Lee metadata_ia ({ dato_registrado, dato_identificado }), fusiona ambos y esparce en la DB.
    dato_identificado suele estar vacío salvo que haya corrido el agente de identificar.
    """
    try:
        # 1. Obtener registro actual y metadata_ia
        params_leer = {
            "codOpe": "CONSULTAR_CACHE",
            "ws_whatsapp": str(wa_id),
            "id_empresa": id_empresa
        }
        res_check = requests.get(URL_API, params=params_leer)
        data_db = res_check.json().get('data', [])

        if not data_db:
            return {"status": "error", "mensaje": "No hay una propuesta pendiente para confirmar."}

        registro_pendiente = data_db[0]

        # 2. Extraer metadata_ia: { dato_registrado: {...}, dato_identificado: {...} }
        try:
            raw_metadata = registro_pendiente.get("metadata_ia", "{}")
            metadata_ia = json.loads(raw_metadata) if (raw_metadata or "").strip() else {}
        except Exception:
            return {"status": "error", "mensaje": "El formato de metadata_ia es inválido."}

        dato_registrado = metadata_ia.get("dato_registrado") or {}
        dato_identificado = metadata_ia.get("dato_identificado") or {}
        # Fusionar: dato_identificado sobrescribe donde aplique (ej. cliente_id, entidad_id_maestro)
        payload_analizado = {**dato_registrado, **dato_identificado}
        # Compatibilidad: si no hay metadata_ia (cache antiguo), usar campos planos del registro
        if not payload_analizado and registro_pendiente:
            prod = registro_pendiente.get("productos_json")
            if isinstance(prod, str):
                try:
                    prod = json.loads(prod) if (prod or "").strip() else []
                except Exception:
                    prod = []
            payload_analizado = {
                "cod_ope": registro_pendiente.get("cod_ope"),
                "entidad_nombre": registro_pendiente.get("entidad_nombre"),
                "entidad_numero_documento": registro_pendiente.get("entidad_numero_documento"),
                "entidad_id_tipo_documento": registro_pendiente.get("entidad_id_tipo_documento"),
                "id_moneda": registro_pendiente.get("id_moneda"),
                "id_comprobante_tipo": registro_pendiente.get("id_comprobante_tipo"),
                "tipo_operacion": registro_pendiente.get("tipo_operacion"),
                "monto_total": registro_pendiente.get("monto_total"),
                "monto_base": registro_pendiente.get("monto_base"),
                "monto_impuesto": registro_pendiente.get("monto_impuesto"),
                "productos_json": prod,
                "persona_id": registro_pendiente.get("persona_id"),
                "cliente_id": registro_pendiente.get("cliente_id"),
                "proveedor_id": registro_pendiente.get("proveedor_id"),
                "entidad_id_maestro": registro_pendiente.get("entidad_id_maestro"),
            }
            payload_analizado = {k: v for k, v in payload_analizado.items() if v is not None and v != ""}

        # 3. Construir payload para ACTUALIZAR_CACHE (valores del registro como fallback)
        productos = payload_analizado.get("productos_json", [])
        productos_str = json.dumps(productos, ensure_ascii=False) if isinstance(productos, list) else (productos or "[]")
        base_db = {
            "codOpe": "ACTUALIZAR_CACHE",
            "ws_whatsapp": str(wa_id),
            "id_empresa": int(id_empresa),
            "cod_ope": payload_analizado.get("cod_ope", registro_pendiente.get("cod_ope")),
            "entidad_nombre": payload_analizado.get("entidad_nombre", ""),
            "entidad_numero_documento": payload_analizado.get("entidad_numero_documento", ""),
            "entidad_id_tipo_documento": payload_analizado.get("entidad_id_tipo_documento"),
            "id_moneda": payload_analizado.get("id_moneda", 1),
            "id_comprobante_tipo": payload_analizado.get("id_comprobante_tipo", 2),
            "tipo_operacion": payload_analizado.get("tipo_operacion", "contado"),
            "monto_total": float(payload_analizado.get("monto_total", 0)),
            "monto_base": float(payload_analizado.get("monto_base", 0)),
            "monto_impuesto": float(payload_analizado.get("monto_impuesto", 0)),
            "productos_json": productos_str,
            "paso_actual": 3,
            "is_ready": 1,
            "ultima_pregunta": "CONFIRMADO",
        }
        for key in ("persona_id", "cliente_id", "proveedor_id", "entidad_id_maestro"):
            if payload_analizado.get(key) is not None:
                base_db[key] = payload_analizado[key]
        payload_db = base_db

        # Limpiar metadata_ia tras confirmar (opcional: dejar vacío para siguiente flujo)
        payload_db["metadata_ia"] = json.dumps({"dato_registrado": {}, "dato_identificado": {}}, ensure_ascii=False)

        # 4. ESCRITURA FINAL
        headers = {'Content-Type': 'application/json'}
        res_escritura = requests.post(
            URL_API, 
            data=json.dumps(payload_db, ensure_ascii=False).encode('utf-8'), 
            headers=headers
        )
        
        res_json = res_escritura.json()

        if res_json.get("success"):
            return {
                "status": "exito",
                "mensaje": "✅ ¡Excelente! He registrado la operación correctamente.",
                "db_res": res_json
            }
        else:
            return {"status": "error", "detalle": res_json.get("error", "Error desconocido en DB")}

    except Exception as e:
        return {"status": "error", "mensaje": str(e)}

@app.post("/iniciar-flujo")
async def iniciar_flujo(wa_id: str, id_empresa: int, tipo: str):
    """
    Crea un registro inicial en el caché de PHP para comenzar el flujo de N8N.
    """
    
    # 1. NORMALIZACIÓN DE INTENCIÓN: 
    # El PHP valida estrictamente in_array($data['cod_ope'], ['ventas', 'compras'])
    tipo_lower = tipo.lower()
    if "compr" in tipo_lower:
        intencion = "compras"
    elif "vent" in tipo_lower:
        intencion = "ventas"
    else:
        # Si no es ninguno, el PHP lanzará una excepción 400
        raise HTTPException(status_code=400, detail="El tipo debe ser relacionado a compras o ventas")

    # 2. CONSTRUCCIÓN DEL PAYLOAD:
    # Según el PHP, para INSERTAR_CACHE los campos requeridos son:
    # codOpe, ws_whatsapp, id_empresa y cod_ope
    payload_minimo = {
        "codOpe": "INSERTAR_CACHE",
        "ws_whatsapp": str(wa_id),
        "id_empresa": int(id_empresa),
        "cod_ope": intencion,  # "compras" o "ventas"
        "is_ready": 0,         # Iniciamos como no listo
        "paso_actual": 0
    }

    try:
        # Enviamos como JSON (el PHP usa file_get_contents('php://input'))
        res = requests.post(URL_API, json=payload_minimo, timeout=10)
        
        # El PHP devuelve un 400 si hay error de validación (Exception)
        if res.status_code != 200:
            print(f"Error del Servidor PHP ({res.status_code}): {res.text}")
            return {
                "success": False, 
                "status_code": res.status_code,
                "error": res.json().get("error", "Error desconocido en el backend")
            }
        
        return res.json()

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/preguntador")
async def servicio_preguntador(wa_id: str, id_empresa: int):
    # 1. Obtener el estado actual del caché
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": id_empresa}
    res_db = requests.get(URL_API, params=params_leer)
    data_db = res_db.json().get('data', [])
    registro = data_db[0] if data_db else {}

    if not registro:
        return {"pregunta": "¡Hola! Soy MaravIA. 🤖 ¿Qué operación deseas registrar hoy? Puedes enviarme una foto de un comprobante o decirme, por ejemplo: 'Venta de 2 laptops a Inversiones Sur'."}

    cod_ope = (registro.get("cod_ope") or "").strip().lower() or None

    # 2. PROMPT: plantilla detallada compartida con analizador/resumen; SOLO datos definidos; jerarquía en diagnóstico
    prompt_pregunta = f"""
    Eres el Asistente Contable de MaravIA. Genera dos bloques: (1) SÍNTESIS VISUAL y (2) DIAGNÓSTICO. Usa la PLANTILLA VISUAL compartida. **A diferencia del analizador, aquí sí despliegas todo lo que YA está registrado en DATOS EN DB:** si cod_ope está definido muestra 🛒 COMPRA o 📤 VENTA; si hay comprobante, cliente/proveedor, productos, montos, etc., muéstralos. Incluye en la Síntesis cada línea para la que el dato exista en DATOS EN DB (no null, no vacío, no 0); si un campo está vacío, esa línea NO debe aparecer.

    DATOS ACTUALES EN DB: {json.dumps(registro, ensure_ascii=False)}

    {PLANTILLA_VISUAL}

    {REGLAS_NORMALIZACION}

    ### JERARQUÍA PARA EL DIAGNÓSTICO (solo lo que REALMENTE falta en DATOS EN DB):
    **Regla crítica:** Antes de listar un ítem como "falta", comprueba en DATOS EN DB que ese campo esté vacío (null, "", 0 o ausente). Si el campo YA tiene valor, NO lo incluyas en el diagnóstico.
    **Los 3 indispensables para poder registrar** (todos deben estar completos; si falta uno, NO digas que no falta nada):
    1. Monto/Detalle: FALTA si monto_total no existe o es 0 Y productos_json está vacío o sin ítems.
    2. Cliente (ventas) o Proveedor (compras): FALTA si no hay (entidad_nombre + entidad_numero_documento) ni cliente_id/entidad_id_maestro (ventas) ni proveedor_id (compras).
    3. Tipo de comprobante: FALTA si id_comprobante_tipo no existe o es 0.
    **Solo escribe "✅ No falta ningún dato indispensable" si y solo si los TRES están completos.** Si falta monto/detalle, cliente/proveedor o tipo de comprobante, debes listarlos como faltantes; nunca afirmes que se puede confirmar si falta alguno.
    **Opcionales** (solo si faltan): tipo_operacion, forma de pago, sucursal, centro de costo, cuenta/caja, fechas.
    **Regla obligatoria:** Si cod_ope YA tiene valor ("compras" o "ventas"), NUNCA incluyas en el diagnóstico "¿Es una venta o una compra?". Solo si cod_ope está vacío, el primer ítem del diagnóstico es "¿Es una venta o una compra?".

    ### SECCIÓN 1 — SÍNTESIS VISUAL:
    Construye el texto siguiendo la plantilla. Para cada línea, comprueba en DATOS EN DB si el campo indicado en "mostrar si" tiene valor (no null, no "", no 0). Si no tiene valor, **no escribas esa línea**. Si no queda ninguna línea por mostrar, escribe: "Aún no hay datos capturados."
    Aplica las REGLAS DE NORMALIZACIÓN: en el texto usa solo "Factura", "Boleta", "Soles", "Dólares", "DNI", "RUC", "Contado", "Crédito" y nombres de sucursal/forma de pago; NUNCA escribas 1, 2, 6, 14 ni ningún ID. cod_ope = "{cod_ope or 'no definido'}" (usa "Cliente" si ventas, "Proveedor" si compras; si no hay cod_ope, no inventes).

    ### SECCIÓN 2 — DIAGNÓSTICO (dinámico: solo campos sin valor):
    Incluye en el diagnóstico ÚNICAMENTE los campos que en DATOS EN DB están vacíos/null/0. Si cod_ope = "compras" o "ventas", NO preguntes "¿Es una venta o una compra?". No preguntes por Factura/Boleta si id_comprobante_tipo ya tiene valor. No preguntes por monto si monto_total > 0 o hay productos. No preguntes por cliente si ya hay entidad_nombre y entidad_numero_documento o cliente_id. Redacta en lenguaje natural. **Solo escribe "✅ No falta ningún dato indispensable; puedes confirmar para registrar." cuando los 3 indispensables estén completos (monto o productos + cliente/proveedor + tipo comprobante). Si falta alguno, lista los que faltan y no digas que puede confirmar.**

    RESPONDE ÚNICAMENTE EN JSON:
    {{
        "sintesis_visual": "Texto SÍNTESIS (solo líneas con dato definido) con \\n",
        "diagnostico": "Texto DIAGNÓSTICO (jerarquía indispensable → opcional) con \\n"
    }}
    """

    response = client.chat.completions.create(
        model=MODELO_IA,
        messages=[{"role": "system", "content": prompt_pregunta}],
        response_format={"type": "json_object"}
    )
    
    resultado = json.loads(response.choices[0].message.content)
    sintesis = resultado.get("sintesis_visual", "").strip()
    diagnostico = resultado.get("diagnostico", "").strip()
    # Obligar despliegue de ambas secciones; si la IA omitió una, la marcamos
    if not sintesis:
        sintesis = "Aún no hay datos capturados."
    if not diagnostico:
        diagnostico = "Revisa los datos arriba y dime qué falta o si confirmas."
    texto_final = f"{sintesis}\n\n{diagnostico}"

    return {
        "status": "ok",
        "whatsapp_output": {
            "texto": texto_final,
            "sintesis_visual": sintesis,
            "diagnostico": diagnostico
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)