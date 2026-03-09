import requests
import json
import os
from datetime import date

# --- CONFIGURACIÓN ---
URL_HISTORIAL = "https://api.maravia.pe/servicio/n8n_asistente/ws_informacion_historial.php"
URL_VENTA_SUNAT = "https://api.maravia.pe/servicio/ws_ventas.php"
# Login en endpoint propio; override con MARAVIA_URL_LOGIN si hace falta
URL_LOGIN = os.environ.get("MARAVIA_URL_LOGIN", "https://api.maravia.pe/servicio/ws_login.php")
# Token fijo o obtenido por LOGIN
TOKEN = os.environ.get(
    "MARAVIA_TOKEN",
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpZCI6MywidXNlcm5hbWUiOiJkaWVnbyIsImVtYWlsIjoiZGllZ29JQG1hcmF2aWEucGUiLCJub21icmVzIjoiRGllZ28iLCJhcGVsbGlkb3MiOiJNYXJhdmlhIE1vcmV5cmEiLCJpZF9lbXByZXNhIjoyLCJpZF9yb2wiOjIsInBlcm1pc29fbGlicmUiOjEsImlhdCI6MTc3MjQ5MDkwMywiZXhwIjoxNzcyNTc3MzAzLCJpc3MiOiJtYXJhdmlhLnNsaW5reWxhYnMuY29tIiwiYXVkIjoibWFyYXZpYS1mcm9udGVuZCJ9.BmDa_e9B0aR3qEx8N75IeQ_BV6hrAFr9CAgtXEgvSWE",
)


def login(username: str, password: str) -> str | None:
    """Obtiene token JWT con credenciales. Payload: codOpe=LOGIN, username, password."""
    payload = {"codOpe": "LOGIN", "username": username, "password": password}
    url = URL_LOGIN if URL_LOGIN else URL_VENTA_SUNAT  # si LOGIN va al mismo WS, usar URL_VENTA_SUNAT
    try:
        r = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        if r.status_code != 200:
            print(f"❌ Login falló: {r.status_code} - {r.text[:200]}")
            return None
        data = r.json()
        token = (data.get("token") or data.get("data", {}).get("token"))
        if token:
            print("✅ Login OK, token obtenido")
            return token
        print("❌ Login: no se encontró 'token' en la respuesta:", list(data.keys()))
        return None
    except Exception as e:
        print(f"❌ Error en login: {e}")
        return None


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
        print("🧪 Ejecutando prueba directa CREAR_VENTA con payload fijo...")
        prueba_crear_venta_directa()
        return

    # 3. EJECUCIÓN SEGÚN EL TIPO DE OPERACIÓN
    if "VENTA" in tipo_ope:
        print("🚀 Iniciando envío a SUNAT...")
        
        # Payload alineado al que funciona en Postman (id_medio_pago, serie, numero, observaciones opcionales)
        subtotal = round(float(monto) / 1.18, 2)
        igv = round(float(monto) * 0.18 / 1.18, 2)
        payload_venta = {
            "codOpe": "CREAR_VENTA",
            "id_usuario": historial.get("id_usuario", 3),
            "id_cliente": int(cliente),
            "id_sucursal": historial.get("id_sucursal", 14),
            "id_moneda": historial.get("id_moneda", 1),
            "id_forma_pago": historial.get("id_forma_pago", 9),
            "id_medio_pago": historial.get("id_medio_pago"),
            "tipo_venta": historial.get("tipo_venta", "Contado"),
            "fecha_emision": historial.get("fecha_emision") or date.today().isoformat(),
            "fecha_pago": historial.get("fecha_pago") or historial.get("fecha_emision") or date.today().isoformat(),
            "id_tipo_afectacion": historial.get("id_tipo_afectacion", 1),
            "id_caja_banco": historial.get("id_caja_banco", 4),
            "tipo_facturacion": "facturacion_electronica",
            "id_tipo_comprobante": 1,
            "serie": historial.get("serie"),
            "numero": historial.get("numero"),
            "observaciones": historial.get("observaciones", "Prueba Factura desde test_pdf_sunat"),
            "detalle_items": [{
                "id_inventario": historial.get("id_inventario", 7),
                "cantidad": 1,
                "precio_unitario": float(monto),
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_subtotal_item": subtotal,
                "valor_igv": igv,
                "valor_total_item": float(monto),
                "id_tipo_producto": 2,
            }],
        }

        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        res_sunat = requests.post(URL_VENTA_SUNAT, json=payload_venta, headers=headers)

        print("\n--- RESPUESTA SUNAT ---")
        print(res_sunat.text)

        # Extraer PDF desde la estructura real de respuesta (sunat.sunat_data)
        try:
            res_json = res_sunat.json()
            if res_json.get("success"):
                sunat_data = (res_json.get("sunat") or {}).get("sunat_data") or {}
                url_pdf = sunat_data.get("sunat_pdf") or sunat_data.get("enlace_documento")
                if url_pdf:
                    print(f"\n📄 PDF Comprobante: {url_pdf}")
                if res_json.get("id"):
                    print(f"🆔 id venta: {res_json['id']}")
            else:
                print(f"\n❌ Error: {res_json.get('message', res_sunat.text[:200])}")
        except Exception as e:
            print(f"\n⚠ No se pudo parsear respuesta: {e}")

    elif "COMPRA" in tipo_ope or "GASTO" in tipo_ope:
        print("\n📝 GENERANDO RESUMEN DE COMPRA/GASTO...")
        print(f"OPERACIÓN: {tipo_ope}")
        print(f"TOTAL: {monto}")
        print(f"PROVEEDOR: {historial.get('nombre_cliente_o_proveedor', 'No especificado')}")
        print("✅ Registro completado localmente.")

def _payload_prueba_directa():
    """Payload CREAR_VENTA alineado al que funciona en Postman (id_medio_pago, serie, numero, observaciones opcionales)."""
    hoy = date.today().isoformat()
    return {
        "codOpe": "CREAR_VENTA",
        "id_usuario": 3,
        "id_cliente": 5,
        "id_sucursal": 14,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "id_medio_pago": None,
        "tipo_venta": "Contado",
        "fecha_emision": hoy,
        "fecha_pago": hoy,
        "id_tipo_afectacion": 1,
        "id_caja_banco": 4,
        "tipo_facturacion": "facturacion_electronica",
        "id_tipo_comprobante": 1,
        "serie": None,
        "numero": None,
        "observaciones": "Prueba Factura Postman",
        "detalle_items": [
            {
                "id_inventario": 7,
                "cantidad": 1,
                "precio_unitario": 1111.00,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_subtotal_item": 941.53,
                "valor_igv": 169.47,
                "valor_total_item": 1111.00,
                "id_tipo_producto": 2,
            }
        ],
    }


def prueba_crear_venta_directa():
    """Envía CREAR_VENTA con payload de prueba (fecha = hoy). Para probar SUNAT cuando el historial no tiene VENTA."""
    print("🧪 Modo prueba directa: enviando CREAR_VENTA con payload fijo...")
    payload = _payload_prueba_directa()
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    res = requests.post(URL_VENTA_SUNAT, json=payload, headers=headers)
    print("\n--- RESPUESTA SUNAT ---")
    print(res.text)
    try:
        res_json = res.json()
        if res_json.get("success"):
            sunat_data = (res_json.get("sunat") or {}).get("sunat_data") or {}
            url_pdf = sunat_data.get("sunat_pdf") or sunat_data.get("enlace_documento")
            if url_pdf:
                print(f"\n📄 PDF Comprobante: {url_pdf}")
            if res_json.get("id"):
                print(f"🆔 id venta: {res_json['id']}")
        else:
            print(f"\n❌ Error: {res_json.get('message', res.text[:200])}")
    except Exception as e:
        print(f"\n⚠ No se pudo parsear respuesta: {e}")


# Ejecución de prueba
if __name__ == "__main__":
    # Obtener token por LOGIN (evita token expirado). Credenciales por env o por defecto.
    user = os.environ.get("MARAVIA_USER", "diego")
    password = os.environ.get("MARAVIA_PASSWORD", "123123")
    token = login(user, password)
    if token:
        globals()["TOKEN"] = token
    else:
        print("⚠ Usando TOKEN por defecto o MARAVIA_TOKEN (puede estar expirado).")

    # Modo directo: probar CREAR_VENTA con payload fijo (sin historial)
    if os.environ.get("MARAVIA_TEST_DIRECTO", "").lower() in ("1", "true", "yes"):
        prueba_crear_venta_directa()
    else:
        sincronizar_registro("51994748961")