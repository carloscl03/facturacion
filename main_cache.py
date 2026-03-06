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

# --- SERVICIO 1: EXTRACCIÓN (MODIFICADO) ---
@app.post("/procesar-extraccion")
async def procesar_extraccion(wa_id: str, mensaje: str):
    # 1. Obtener estado actual
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": 2}
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
        "id_empresa": 2,
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
async def generar_pregunta(wa_id: str):
    # 1. Obtener el estado actual del caché
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": 2}
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

    LA GUÍA ('resumen_y_guia'):
    aquí se almacena los 4 campos que deben enviarse en 'resumen_y_guia'. La intención de esta variable es generar una pregunta contextualizada.
    1. RESUMEN: conforme a la estructura
    2. RETROALIMENTACIÓN: Confirma el último cambio (Ej: "Factura configurada").
    3. DIAGNÓSTICO: Identifica qué falta según la MATRIZ DE PRIORIDAD.
    4. PREGUNTA: Haz la pregunta para llenar el dato que falta.
    
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
@app.post("/clasificar-mensaje")
async def clasificar_mensaje(mensaje: str):
    prompt_router = f"""
    Eres el Director de Orquesta de un sistema ERP contable. Tu misión es clasificar la intención del usuario con precisión quirúrgica.
    
    MENSAJE DEL USUARIO: "{mensaje}"
    
    REGLAS DE CLASIFICACIÓN (JERARQUÍA):
    1. ACTUALIZAR (CLAVE): Se elige si el mensaje contiene:
       - Datos técnicos (RUC, DNI, montos, productos, nombres). o intención de actualizar un campo de un comprobante de pago.
       - Confirmaciones o Negaciones a preguntas previas (Ej: "Sí", "No", "Es correcto", "Ese no es"). 
       - Si el bot preguntó "¿Es este el cliente?" y el usuario dice "Sí", esto es ACTUALIZAR para marcar la validación, NO es finalizar la venta.
       - Registro de productos con cantidad y precios

    2. RESUMEN: El usuario pide ver el estado actual o pregunta qué falta. 
       - Ejemplos: "¿Qué llevo?", "Resumen", "¿Qué falta?".

    3. VENTA / COMPRA: Solo si el usuario manifiesta el deseo de iniciar pero NO da datos. 
       - Ejemplos: "Quiero vender", "Registrar compra".   
    
    4. FINALIZAR: **ÚNICAMENTE** si el usuario confirma el envío final Y todos los datos críticos en 'DATOS EN DB' están completos (Monto, Entidad, Comprobante y Pago). 
       - Ejemplos: "Procesa la factura", "Envíalo ya", "Todo conforme, emite el documento".
       - NOTA: Un simple "Sí" o "Correcto" o "Proceder" o "Exacto" NO es finalizar, es una confirmación de actualización.

    5. CASUAL: Saludos, charla trivial o mensajes sin intención contable.

    6. ELIMINAR: Intención clara de borrar, cancelar, limpiar o "empezar de cero". (Prioridad máxima para evitar basura).

    RESPONDE EXCLUSIVAMENTE EN JSON:
    {{
        "intencion": "venta|compra|actualizar|casual|eliminar|resumen|finalizar",
        "confianza": float,
        "urgencia": "alta|media|baja",
        "necesita_extraccion": bool,
        "campo_detectado": "entidad|monto|comprobante|condicion_pago|ninguno"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model=MODELO_IA,
            messages=[{"role": "system", "content": prompt_router}],
            response_format={"type": "json_object"}
        )
        
        resultado = json.loads(response.choices[0].message.content)
        
        # Lógica de extracción: Solo estos 3 estados requieren pasar por el extractor de datos
        resultado['necesita_extraccion'] = resultado['intencion'] in ['venta', 'compra', 'actualizar']
        
        return resultado

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- SERVICIO 4: ELIMINACIÓN ---
@app.post("/eliminar-operacion")
async def eliminar_operacion(wa_id: str):
    payload = {"codOpe": "ELIMINAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": 2}
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
async def generar_resumen(wa_id: str):
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": 2}
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

    # --- PROMPT DE ESTANDARIZACIÓN (Corrección de Validación de Identidad) ---
    prompt_resumen = f"""
    Eres el Auditor de MaravIA. Tu misión es generar un resumen impecable y dirigir al usuario al siguiente paso REAL.

    DATOS EN DB (JSON):
    {json.dumps(registro, ensure_ascii=False)}

    ### 1. 🚦 REGLAS DE VALIDACIÓN DE IDENTIDAD (CRÍTICO):
    - REGLA DE ORO: Si 'entidad_numero_documento' tiene un valor (aunque sea temporal), el paso de IDENTIFICACIÓN está COMPLETADO.
    - Si 'entidad_id_tipo_documento' es 1 o 6, NO pidas el tipo de documento.
    - Si el documento ya aparece en el resumen entre paréntesis, está PROHIBIDO poner "RUC/DNI" en 'Faltantes Críticos'.

    ### 2. ESTRUCTURA OBLIGATORIA (WHATSAPP):
    ━━━━━━━━━━━━━━━━━━━━
    ✨ *RESUMEN DE {cod_ope.upper()}*
    ━━━━━━━━━━━━━━━━━━━━
    📄 **Comprobante:** {registro.get('comprobante_tipo_nombre', 'Pendiente')}
    👤 **{'Cliente' if cod_ope == 'ventas' else 'Proveedor'}:** {registro.get('entidad_nombre', 'Identificando...')} ({registro.get('entidad_numero_documento', '---')})
    📅 **Fecha:** {registro.get('fecha_emision', 'Hoy')} | 💵 **Moneda:** {registro.get('moneda_nombre', 'Soles')}

    📦 **DETALLE DE PRODUCTOS:**
    (Genera la lista desde productos_json):
    🔹 [cantidad] x [nombre] — {registro.get('moneda_simbolo', 'S/')} [total_item]

    💰 **DESGLOSE ECONÓMICO:**
    ├─ Subtotal: {registro.get('moneda_simbolo', 'S/')} {registro.get('monto_base', '0.00')}
    ├─ IGV (18%): {registro.get('moneda_simbolo', 'S/')} {registro.get('monto_impuesto', '0.00')}
    └─ **TOTAL FINAL: {registro.get('moneda_simbolo', 'S/')} {registro.get('monto_total', '0.00')}**
    ━━━━━━━━━━━━━━━━━━━━
    📍 *Sucursal:* {registro.get('sucursal_nombre', 'Principal')} | 💳 *Pago:* {registro.get('tipo_operacion', 'Contado')}
    ━━━━━━━━━━━━━━━━━━━━

    ### 3. DIAGNÓSTICO INTELIGENTE:
    💡 *Estado:* {'✅ Todo listo.' if not criticos else '⚠️ Datos pendientes.'}

    🎯 **Siguiente paso:** [Instrucción]: Mira los Faltantes Críticos. 
    1. Si ya hay un número de documento arriba, ELIMINA "RUC/DNI" de la lista de faltantes.
    2. Si el único faltante real es el Comprobante, pregunta: "¿Deseas emitir Factura o Boleta?".
    3. Si todo está lleno, pregunta: "¿Deseas finalizar la emisión?".

    PROHIBIDO: No pidas datos que ya se muestran en el resumen superior.
    """

    response = client.chat.completions.create(
        model=MODELO_IA,
        messages=[{"role": "system", "content": prompt_resumen}]
    )
    
    return {"resumen": response.choices[0].message.content}

# --- SERVICIO 6: IDENTIFICADOR (ACTUALIZADO) ---
@app.post("/identificar-entidad")
async def identificar_entidad(wa_id: str, tipo_ope: str, termino: str):
    """
    SERVICIO DE SOLO LECTURA: Busca la entidad por DNI/RUC/Nombre.
    No crea registros nuevos en la base de datos de Maravia.
    """
    if not termino:
        return {"found": False, "mensaje": "No se proporcionó un término de búsqueda."}

    try:
        # 1. Búsqueda selectiva según el flujo (Ventas -> Cliente / Compras -> Proveedor)
        if tipo_ope == "ventas":
            # Usamos GET y empresa_id (según estructura ws_cliente.php)
            params = {"codOpe": "BUSCAR_CLIENTE", "empresa_id": 2, "termino": termino}
            r = requests.get(URL_CLIENTE, params=params, timeout=5)
        else:
            # Usamos POST y id_empresa (según estructura ws_proveedor.php)
            payload = {"codOpe": "BUSCAR_PROVEEDOR", "id_empresa": 2, "nombre_completo": termino}
            r = requests.post(URL_PROVEEDOR, json=payload, timeout=5)

        res_data = r.json()
        
        # 2. Verificación de existencia
        if res_data.get('found'):
            info = res_data.get('data', {})
            
            # --- CONSTRUCCIÓN DE IDENTIDAD (Basado en tus resultados reales) ---
            # Extraemos nombres y apellidos manejando los nulos que vimos en el test
            nombres = (info.get('nombres') or "").strip()
            ap_pat = (info.get('apellido_paterno') or "").strip()
            ap_mat = (info.get('apellido_materno') or "").strip()
            
            # Formateamos el nombre completo
            nombre_persona = f"{nombres} {ap_pat} {ap_mat}".strip()
            nombre_final = info.get('razon_social') or nombre_persona or "Sin nombre identificado"
            
            # Identificación de documento
            doc_num = info.get('numero_documento') or info.get('ruc') or termino
            tipo_doc_id = info.get('id_tipo_documento') or (6 if len(str(doc_num)) == 11 else 1)
            tipo_doc_nombre = "RUC" if tipo_doc_id == 6 else "DNI"

            confirmacion = f"Identidad detectada: {nombre_final} ({tipo_doc_nombre}: {doc_num}). ¿Es correcto?"

            # 3. Guardar en Caché (Para que el bot "recuerde" a quién encontró)
            payload_cache = {
                "codOpe": "ACTUALIZAR_CACHE",
                "ws_whatsapp": wa_id,
                "id_empresa": 2,
                "entidad_nombre": nombre_final,
                "entidad_numero_documento": doc_num,
                "entidad_id_tipo_documento": tipo_doc_id,
                "ultima_pregunta": confirmacion 
            }
            requests.post(URL_API, json=payload_cache, timeout=5)

            return {
                "found": True,
                "mensaje": confirmacion,
                "data_minima": {"nombre": nombre_final, "documento": doc_num}
            }
            
        else:
            # Si no existe, NO REGISTRAMOS. Solo informamos y actualizamos caché con el error.
            mensaje_no_existe = f"No encontré registros para '{termino}'. ¿Deseas intentar con otro número o registrar uno nuevo?"
            
            requests.post(URL_API, json={
                "codOpe": "ACTUALIZAR_CACHE",
                "ws_whatsapp": wa_id,
                "id_empresa": 2,
                "ultima_pregunta": mensaje_no_existe
            }, timeout=5)

            return {"found": False, "mensaje": mensaje_no_existe}

    except Exception as e:
        # En caso de error de conexión o JSON inválido
        return {"found": False, "mensaje": f"Error de conexión con el servidor de datos."}

# --- CONFIGURACIÓN DE URLS ---
URL_VENTA_SUNAT = "https://api.maravia.pe/servicio/ws_ventas.php"
TOKEN = os.getenv("TOKEN_SUNAT")

# --- SERVICIO 7: fINALIZAR Y GENERAR PDF
@app.post("/finalizar-operacion")
async def finalizar_operacion(wa_id: str):
    # 1. Obtener datos del historial (Cache)
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": 2}
    res_db = requests.get(URL_API, params=params_leer)
    data_db = res_db.json().get('data', [])
    
    if not data_db:
        return {"status": "error", "mensaje": "No hay una operación activa para finalizar."}
    
    reg = data_db[0]
    # Normalizamos el tipo de operación
    tipo_ope = str(reg.get('cod_ope', 'VENTAS')).upper()
    
    # 2. CAPTURA DE DATOS NORMALIZADOS (Extraídos por la IA)
    monto_total = reg.get('monto_total')
    monto_base = reg.get('monto_base')
    monto_igv = reg.get('monto_impuesto')
    id_entidad = reg.get('entidad_id_maestro') # ID obtenido del ERP (Servicio 6)
    tipo_comp = reg.get('id_comprobante_tipo')
    moneda_simbolo = reg.get('moneda_simbolo', 'S/')

    # 3. DIAGNÓSTICO ESTRICTO PRE-ENVÍO
    errores = []
    if not monto_total or float(monto_total) <= 0: errores.append("Monto total")
    if not id_entidad: errores.append("Identificación del Cliente/Proveedor (ID)")
    if not tipo_comp: errores.append("Tipo de Comprobante (Boleta/Factura)")

    if errores:
        faltantes = ", ".join(errores)
        return {
            "status": "incompleto",
            "mensaje": f"⚠️ *No se puede finalizar.*\n\nFaltan datos obligatorios: **{faltantes}**. Por favor, proporciónalos para continuar."
        }

    try:
        # --- CASO A: VENTAS (Envío a SUNAT + PDF) ---
        if "VENTA" in tipo_ope:
            payload_venta = {
                "codOpe": "CREAR_VENTA",
                "id_usuario": 3,
                "id_cliente": id_entidad,
                "id_sucursal": reg.get("id_sucursal", 14),
                "id_moneda": reg.get("id_moneda", 1),
                "id_forma_pago": reg.get("id_forma_pago", 9),
                "tipo_venta": reg.get("tipo_operacion", "Contado").capitalize(),
                "fecha_emision": reg.get("fecha_emision", "2026-03-03"),
                "tipo_facturacion": "facturacion_electronica",
                "id_tipo_comprobante": tipo_comp,
                "detalle_items": [{
                    "id_inventario": 7,
                    "cantidad": 1,
                    "precio_unitario": float(monto_total),
                    "valor_subtotal_item": float(monto_base),
                    "valor_igv": float(monto_igv),
                    "valor_total_item": float(monto_total),
                    "id_tipo_producto": 2
                }]
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
            else:
                return {
                    "status": "error",
                    "mensaje": f"❌ Error SUNAT: {res_json.get('message', 'No se pudo generar el PDF.')}"
                }

        # --- CASO B: COMPRAS (Registro Local / Resumen) ---
        else:
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
async def servicio_8_unificado(wa_id: str, mensaje: str):
    # 1. Obtener estado actual (Contexto para la IA)
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": wa_id, "id_empresa": 2}
    res_db = requests.get(URL_API, params=params_leer)
    data_db = res_db.json().get('data', [])
    estado_actual = data_db[0] if data_db else {}
    es_registro_nuevo = len(data_db) == 0

    contexto_operacion = estado_actual.get('cod_ope', 'ventas')
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

    ### 4. REGLAS DE RESPUESTA VISUAL (WHATSAPP)
    - **PROHIBIDO** usar IDs numéricos en el texto. Usa nombres: `comprobante_tipo_nombre`, `sucursal_nombre`, etc.
    - **ESTRUCTURA OBLIGATORIA**:
        ━━━━━━━━━━━━━━━━━━━
        📄 *[comprobante_tipo_nombre]* 
        👤 *[CLIENTE o PROVEEDOR]:* [entidad_nombre]
        🆔 *[DNI o RUC]*: [entidad_numero_documento]
        ━━━━━━━━━━━━━━━━━━━
        📦 *DETALLE DE [VENTA o COMPRA]:*
        (Iterar productos_json: 🔹 Cant. [cantidad] x [nombre] — [moneda_simbolo][total_item])
        💰 *RESUMEN ECONÓMICO:*
        ├─ Subtotal: [moneda_simbolo] [monto_base]
        ├─ IGV (18%): [moneda_simbolo] [monto_impuesto]
        └─ **TOTAL: [moneda_simbolo] [monto_total]**
        ━━━━━━━━━━━━━━━━━━━
        📍 *Sucursal:* [sucursal_nombre] | 💳 *Pago:* [tipo_operacion] | 💵 *Moneda:* [moneda_nombre]
        ━━━━━━━━━━━━━━━━━━━

    LA GUÍA ('resumen_y_guia'):
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
            "resumen_y_guia": str, "requiere_botones": FALSE, "btn1_id": str, "btn1_title": str, "btn2_id": str, "btn2_title": str
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
        "id_empresa": 2,
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)