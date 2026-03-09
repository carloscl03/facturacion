import requests
import json

# --- CONFIGURACIÓN ---
URL_HISTORIAL = "https://api.maravia.pe/servicio/n8n_asistente/ws_informacion_historial.php"
URL_VENTA_SUNAT = "https://api.maravia.pe/servicio/ws_ventas.php"
TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpZCI6MywidXNlcm5hbWUiOiJkaWVnbyIsImVtYWlsIjoiZGllZ29JQG1hcmF2aWEucGUiLCJub21icmVzIjoiRGllZ28iLCJhcGVsbGlkb3MiOiJNYXJhdmlhIE1vcmV5cmEiLCJpZF9lbXByZXNhIjoyLCJpZF9yb2wiOjIsInBlcm1pc29fbGlicmUiOjEsImlhdCI6MTc3MjQ5MDkwMywiZXhwIjoxNzcyNTc3MzAzLCJpc3MiOiJtYXJhdmlhLnNsaW5reWxhYnMuY29tIiwiYXVkIjoibWFyYXZpYS1mcm9udGVuZCJ9.BmDa_e9B0aR3qEx8N75IeQ_BV6hrAFr9CAgtXEgvSWE"

def sincronizar_registro(wa_id):
    # 1. LEER LA BASE DE DATOS (HISTORIAL)
    print(f"🔎 Consultando datos para {wa_id}...")
    res = requests.get(URL_HISTORIAL, params={'ws_whatsapp': wa_id})
    
    if res.status_code != 200:
        print(f"❌ Error al conectar con el historial: {res.status_code}")
        return

    data_json = res.json()
    historial = data_json.get('data', [])[0] if data_json.get('data') else {}

    if not historial:
        print("⚠️ No se encontró ningún registro pendiente.")
        return

    # Imprimir para auditoría visual rápida
    tipo_ope = str(historial.get('cod_ope', '')).upper()
    print(f"📊 Registro detectado: {tipo_ope}")

    # 2. VALIDACIÓN DE CAMPOS CRÍTICOS (Sincronización Inmediata)
    # Si faltan datos clave, no enviamos a SUNAT para evitar errores 400
    monto = historial.get('monto')
    cliente = historial.get('id_cliente')

    if not monto or not cliente:
        print(f"🚫 Sincronización cancelada: Faltan datos (Monto: {monto}, Cliente: {cliente})")
        return

    # 3. EJECUCIÓN SEGÚN EL TIPO DE OPERACIÓN
    if "VENTA" in tipo_ope:
        print("🚀 Iniciando envío a SUNAT...")
        
        payload_venta = {
            "codOpe": "CREAR_VENTA",
            "id_usuario": historial.get("id_usuario", 3),
            "id_cliente": cliente,
            "id_sucursal": historial.get("id_sucursal", 14),
            "id_moneda": historial.get("id_moneda", 1),
            "id_forma_pago": historial.get("id_forma_pago", 9),
            "tipo_venta": "Contado",
            "fecha_emision": "2026-03-03",
            "tipo_facturacion": "facturacion_electronica",
            "id_tipo_comprobante": 1,
            "detalle_items": [{
                "id_inventario": historial.get("id_inventario", 7),
                "cantidad": 1,
                "precio_unitario": float(monto),
                "valor_subtotal_item": round(float(monto) / 1.18, 2),
                "valor_igv": round(float(monto) * 0.18 / 1.18, 2),
                "valor_total_item": float(monto),
                "id_tipo_producto": 2
            }]
        }

        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        res_sunat = requests.post(URL_VENTA_SUNAT, json=payload_venta, headers=headers)
        
        print("\n--- RESPUESTA SUNAT ---")
        print(res_sunat.text)

    elif "COMPRA" in tipo_ope or "GASTO" in tipo_ope:
        print("\n📝 GENERANDO RESUMEN DE COMPRA/GASTO...")
        print(f"OPERACIÓN: {tipo_ope}")
        print(f"TOTAL: {monto}")
        print(f"PROVEEDOR: {historial.get('nombre_cliente_o_proveedor', 'No especificado')}")
        print("✅ Registro completado localmente.")

# Ejecución de prueba
if __name__ == "__main__":
    sincronizar_registro("51994748961")