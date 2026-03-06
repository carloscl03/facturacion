import requests
import json

# Configuración
DNI_BUSCAR = "73181775"
URL_CLIENTE = "https://api.maravia.pe/servicio/n8n/ws_cliente.php"
URL_PROVEEDOR = "https://api.maravia.pe/servicio/n8n_asistente/ws_proveedor.php"

def consultar_datos_dni():
    print(f"🔍 Consultando información para el DNI: {DNI_BUSCAR}\n")

    # --- 👤 CONSULTA EN CLIENTE ---
    print("--- [SECCIÓN CLIENTE] ---")
    params_cli = {
        "codOpe": "BUSCAR_CLIENTE", 
        "empresa_id": 2, 
        "termino": DNI_BUSCAR
    }
    
    try:
        r_cli = requests.get(URL_CLIENTE, params=params_cli)
        data_cli = r_cli.json()
        
        if data_cli.get('found'):
            print("✅ ¡CLIENTE ENCONTRADO!")
            # Imprime todo el JSON formateado
            print(json.dumps(data_cli.get('data'), indent=4, ensure_ascii=False))
        else:
            print(f"❌ No existe un cliente con DNI {DNI_BUSCAR}.")
            print(f"Respuesta del servidor: {data_cli.get('message', 'Sin mensaje')}")
            
    except Exception as e:
        print(f"💥 Error al consultar cliente: {e}")


    print("\n" + "="*40 + "\n")


    # --- 🏢 CONSULTA EN PROVEEDOR ---
    print("--- [SECCIÓN PROVEEDOR] ---")
    payload_prov = {
        "codOpe": "BUSCAR_PROVEEDOR", 
        "id_empresa": 2, 
        "nombre_completo": DNI_BUSCAR
    }
    
    try:
        r_prov = requests.post(URL_PROVEEDOR, json=payload_prov)
        data_prov = r_prov.json()
        
        if data_prov.get('found'):
            print("✅ ¡PROVEEDOR ENCONTRADO!")
            # Imprime todo el JSON formateado
            print(json.dumps(data_prov.get('data'), indent=4, ensure_ascii=False))
        else:
            print(f"❌ No existe un proveedor con DNI {DNI_BUSCAR}.")
            print(f"Respuesta del servidor: {data_prov.get('message', 'Sin mensaje')}")

    except Exception as e:
        print(f"💥 Error al consultar proveedor: {e}")

if __name__ == "__main__":
    consultar_datos_dni()