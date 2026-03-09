import os
import requests
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

URL_LEER = "https://api.maravia.pe/servicio/n8n_asistente/ws_informacion_historial.php"
URL_ESCRIBIR = "https://api.maravia.pe/servicio/n8n_asistente/ws_historial.php"

def ejecutar_ciclo_interceptacion(numero_wsp):
    while True:
        # --- PARTE 3 (Contexto): PULL del estado actual de las variables ---
        res_pull = requests.get(URL_LEER, params={'ws_whatsapp': numero_wsp}, timeout=10)
        estado_actual = res_pull.json().get('data', [{}])[0]

        print("\n" + "="*60)
        print(f"📊 INTERCEPTANDO REGISTRO ID: {estado_actual.get('id')} (WSP: {numero_wsp})")
        
        # --- PARTE 2: MENSAJE DEL USUARIO ---
        instruccion_usuario = input("💬 Instrucción de cambio (o 'salir'): ")
        if instruccion_usuario.lower() in ['salir', 'exit']: break

        # --- PARTE 1: INSTRUCCIONES DE RESTRICCIÓN Y COMPORTAMIENTO ---
        prompt_sistema = """
        OBJETIVO: Actuar como un transformador de estados JSON contables.
        
        RESTRICCIONES:
        1. Debes devolver el objeto JSON COMPLETO. No omitas ninguna llave recibida.
        2. Si 'cod_ope' es 'compras', cualquier nombre de entidad (persona o empresa) se asigna a 'nombre_proveedor'.
        3. 'tipo_comprobante' solo acepta: 'Factura', 'Boleta', 'Ticket' o 'Recibo'.
        4. Si el 'monto' cambia, recalcula 'monto_sin_impuesto' (monto/1.18) e 'impuesto' (monto-sin_impuesto).
        5. No inventes campos. Solo modifica valores existentes.
        
        SALIDA: Solo el objeto JSON puro. Sin explicaciones.
        """

        print("🤖 IA procesando transformación...")
        
        # Ensamblaje del prompt con las 3 partes
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"MENSAJE USUARIO: {instruccion_usuario}\n\nESTADO ACTUAL VARIABLES: {json.dumps(estado_actual)}"}
            ],
            response_format={ "type": "json_object" },
            temperature=0
        )
        
        estado_modificado = json.loads(response.choices[0].message.content)

        # --- PUSH: Sincronización al registro ---
        # Inyectamos metadatos de control antes del envío
        estado_modificado.update({
            "ws_whatsapp": numero_wsp,
            "es_registro": "1",
            "empresa_id": estado_actual.get('empresa_id', '2')
        })

        print("💾 Haciendo PUSH al servidor...")
        requests.post(URL_ESCRIBIR, json=estado_modificado, timeout=10)

        # --- PULL DE VERIFICACIÓN (Para mostrar el resultado final) ---
        res_verificacion = requests.get(URL_LEER, params={'ws_whatsapp': numero_wsp}, timeout=10)
        estado_final = res_verificacion.json().get('data', [{}])[0]

        print("\n✅ ESTADO SINCRONIZADO EN LA BASE DE DATOS:")
        print(f"{'CAMPO':<25} | {'VALOR FINAL':<35}")
        print("-" * 65)
        for k in sorted(estado_final.keys()):
            val_ant = str(estado_actual.get(k))
            val_new = str(estado_final.get(k))
            icon = "✨ " if val_ant != val_new else "  "
            print(f"{icon}{k:<23} | {val_new:<35}")

if __name__ == "__main__":
    WSP_PRUEBA = "51994748961"
    ejecutar_ciclo_interceptacion(WSP_PRUEBA)