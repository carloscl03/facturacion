import os
import requests
import json
from fastapi import FastAPI, Query, HTTPException, Body
from openai import OpenAI
from dotenv import load_dotenv
import uvicorn

# Cargar las llaves del archivo .env
load_dotenv()

app = FastAPI(title="MaravIA - Motor de Ejecución (Prompt desde n8n)")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# URLs constantes de tu infraestructura
URL_LEER = "https://api.maravia.pe/servicio/n8n_asistente/ws_informacion_historial.php"
URL_ESCRIBIR = "https://api.maravia.pe/servicio/n8n_asistente/ws_historial.php"

# --- SERVICIO 1: ANALIZADOR (Lectura y Respuesta Amable) ---
@app.get("/analizar-historial")
async def analizar_historial(
    ws_whatsapp: str = Query(..., description="Número de WhatsApp"),
    user_prompt: str = Query(..., description="Instrucción enviada desde n8n")
):
    try:
        response_api = requests.get(URL_LEER, params={'ws_whatsapp': ws_whatsapp}, timeout=10)
        data_json = response_api.json()
        historial_data = data_json.get('data', [])[0] if data_json.get('data') else {}
        
        chat_completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres el asistente de MaravIA. Responde amablemente analizando el JSON proporcionado."},
                {"role": "user", "content": f"DATA: {historial_data}\nINSTRUCCIÓN: {user_prompt}"}
            ]
        )
        return {"status": "success", "respuesta_ia": chat_completion.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- SERVICIO 2: ACTUALIZADOR CON VERIFICACIÓN ---
@app.post("/actualizar-registro")
@app.post("/actualizar-y-verificar")
async def actualizar_y_verificar(
    ws_whatsapp: str = Body(..., embed=True),
    prompt_user: str = Body(..., embed=True)
):
    try:
        # --- PARTE 1: PULL INICIAL (Estado actual de las variables) ---
        res_pull = requests.get(URL_LEER, params={'ws_whatsapp': ws_whatsapp}, timeout=10)
        res_pull.raise_for_status()
        data_lectura = res_pull.json()
        
        # Extraemos el registro base o inicializamos si no existe
        registro_base = data_lectura.get('data', [{}])[0] if data_lectura.get('data') else {}
        if not registro_base:
            registro_base = {"ws_whatsapp": ws_whatsapp, "empresa_id": "2", "cod_ope": "compras"}

        # --- PARTE 2: PROCESAMIENTO CON IA (Arquitectura de 3 Capas) ---
        # 1. Comportamiento y Restricciones | 2. Mensaje Usuario | 3. Estado Actual
        prompt_sistema = """
  ### ROL: EDITOR TÉCNICO DE ESTADOS CONTABLES (MARAVIA ERP)

### OBJETIVO:
Transformar un JSON (Estado Actual) en un nuevo JSON (Estado Modificado) basado en una 'Instrucción de Usuario'. El resultado debe cumplir estrictamente con las reglas de negocio contables de Perú y la lógica de los Agentes de Compras y Ventas.

### REGLAS DE IDENTIFICACIÓN DE FLUJO (ANALOGÍA):
1. Si 'cod_ope' == 'compras':
   - Entidad: El nombre va en 'nombre_proveedor' y el documento en 'documento_proveedor'.
   - Campos Clave: Requiere 'centro_costo', 'nro_documento' (formato SUNAT) y 'concepto'.
2. Si 'cod_ope' == 'ventas':
   - Entidad: El nombre va en 'nombre_cliente' y el documento en 'documento_cliente'.
   - Campos Clave: Requiere 'producto' (en 'productos_json'), 'sucursal' y 'banco_caja'.

### REGLAS DE COMPORTAMIENTO Y MÁQUINA DE ESTADOS:
1. LÓGICA DE CRÉDITO: Si 'tipo_compra' o 'tipo_venta' se establece como 'credito', los campos 'dias_credito' y 'nro_cuotas' se vuelven OBLIGATORIOS.
2. LÓGICA DE CONTADO: Si el tipo es 'contado' Y existe una 'fecha_pago', el campo 'banco_caja' es OBLIGATORIO.
3. VALIDACIÓN DE DOCUMENTOS:
   - Factura: Requiere RUC (11 dígitos).
   - Boleta: Requiere DNI (8 dígitos) o Carnet de Extranjería (hasta 12).
   - Tipos Permitidos: 'factura', 'boleta', 'nota_de_venta'.

### MOTOR DE CÁLCULO MATEMÁTICO (IGV 18%):
- Si el usuario indica un MONTO TOTAL:
    * 'monto_total' = Valor total recibido.
    * 'monto_sin_igv' (o 'monto_sin_impuesto') = monto_total / 1.18
    * 'igv' (o 'impuesto') = monto_total - monto_sin_igv
- Si el usuario indica un MONTO SIN IGV, calcula el total sumando el 18%.
- SIEMPRE garantiza la coherencia matemática entre los tres campos.

### NORMALIZACIÓN Y RESTRICCIONES:
1. FORMATO DE SALIDA: Devuelve el objeto JSON COMPLETO con todas las llaves originales. No omitas ningún campo del estado actual.
2. FECHAS: Convertir cualquier fecha mencionada a formato ISO (YYYY-MM-DD).
3. ENUMS: Normalizar valores a minúsculas y términos técnicos (ej: 'Cta Corriente' -> 'transferencia', 'Crédito' -> 'credito').
4. NO INVENTAR: No agregues llaves que no existan en el JSON de entrada.
5. SALIDA EXCLUSIVA: Responde ÚNICAMENTE con el objeto JSON puro. Prohibido incluir explicaciones, saludos o texto adicional.

PON ESPECIAL CUIDADO A LLENAR EL NOMBRE MÁS ADECUADO EN EL ESPACIO MÁS SIMILAR CON REFERENCIA A LO INDICADO EN LA INSTRUCCIÓN USUARIO Y EL NOMBRE DE LA VARIABLE MÁS PARECIDA.
si algún campo no aplica se llenará con no aplica o con datos vacios como 0 para proseguir con e flujo de llenado
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {
                    "role": "user", 
                    "content": f"INSTRUCCIÓN DE USUARIO: {prompt_user}\n\nESTADO ACTUAL DE VARIABLES (PULL): {json.dumps(registro_base)}"
                }
            ],
            response_format={ "type": "json_object" },
            temperature=0
        )
        
        estado_modificado = json.loads(response.choices[0].message.content)

        # --- PARTE 3: PUSH (Sincronización al Registro) ---
        # Aseguramos metadatos críticos para la persistencia antes de enviar
        estado_modificado.update({
            "ws_whatsapp": ws_whatsapp,
            "empresa_id": registro_base.get("empresa_id", "2"),
            "cod_ope": registro_base.get("cod_ope", "compras"),
            "es_registro": "1" # Forzamos impacto en la tabla SQL
        })

        res_escritura = requests.post(URL_ESCRIBIR, json=estado_modificado, timeout=10)
        res_escritura.raise_for_status()
        resp_php = res_escritura.json()

        # --- PARTE 4: PULL FINAL (Verificación de la verdad en DB) ---
        res_verificacion = requests.get(URL_LEER, params={'ws_whatsapp': ws_whatsapp}, timeout=10)
        datos_finales = res_verificacion.json().get('data', [{}])[0]

        # --- RESPUESTA UNIFICADA ---
        return {
            "status": "success",
            "auditoria": {
                "antes": registro_base,
                "despues": datos_finales
            },
            "cambios_detectados": {
                k: f"{registro_base.get(k)} ➡️ {datos_finales.get(k)}" 
                for k in datos_finales 
                if str(registro_base.get(k)) != str(datos_finales.get(k))
            },
            "api_response": {
                "next_question": resp_php.get("next_question"),
                "id_registro": resp_php.get("id")
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en sincronización: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)