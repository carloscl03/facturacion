import requests
import json
import time

URL_LOCAL = "http://localhost:3000/chat"
WA_ID = "51999999999"

def realizar_test_paso_a_paso():
    # Simulamos una conversación de 3 pasos
    conversacion = [
        "Hola, soy de la empresa Maravía SAC y quiero hacer un pedido.",
        "Mi RUC es 20601234567.",
        "Quiero 10 repuestos de motor y 5 aceites sintéticos."
    ]

    print(f"🚀 Iniciando Test de Doble Servicio para: {WA_ID}\n")

    for i, mensaje in enumerate(conversacion, 1):
        print(f"--- PASO {i}: Usuario envía ---")
        print(f"💬 '{mensaje}'")
        
        try:
            # Enviamos al FastAPI puerto 3000
            params = {"wa_id": WA_ID, "mensaje": mensaje}
            response = requests.post(URL_LOCAL, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ SERVICIO 2 (Pregunta Casual):")
                print(f"🤖 '{data['whatsapp_msg']}'")
                
                # Opcional: ver qué se guardó en DB (Servicio 1)
                # print(f"DEBUG DB: {data['debug_db']}") 
            else:
                print(f"❌ Error {response.status_code}: {response.text}")

        except Exception as e:
            print(f"💥 Error de conexión: {e}")
        
        print("-" * 40)
        time.sleep(2) # Pausa para simular tiempo de respuesta humano

if __name__ == "__main__":
    realizar_test_paso_a_paso()