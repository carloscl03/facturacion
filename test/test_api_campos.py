"""
Test de campos obligatorios y opcionales de la API Maravia:
- LOGIN (ws_login.php): codOpe, username, password
- CREAR_VENTA (ws_ventas.php): payload completo según documentación

Ejecutar: python test/test_api_campos.py
Requiere: MARAVIA_USER, MARAVIA_PASSWORD en env (opcional; por defecto diego/123123)
"""

import os
import json
import requests
from datetime import date

# --- URLs (mismo origen que test_pdf_sunat) ---
URL_LOGIN = os.environ.get("MARAVIA_URL_LOGIN", "https://api.maravia.pe/servicio/ws_login.php")
URL_VENTA_SUNAT = os.environ.get("MARAVIA_URL_VENTAS", "https://api.maravia.pe/servicio/ws_ventas.php")

USER = os.environ.get("MARAVIA_USER", "diego")
PASSWORD = os.environ.get("MARAVIA_PASSWORD", "123123")

# Token obtenido por LOGIN al iniciar
TOKEN = None


def login(username: str, password: str) -> str | None:
    """Obtiene token JWT. Payload: codOpe=LOGIN, username, password."""
    payload = {"codOpe": "LOGIN", "username": username, "password": password}
    try:
        r = requests.post(URL_LOGIN, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        data = r.json() if r.status_code == 200 else {}
        token = data.get("token") or (data.get("data") or {}).get("token")
        return token
    except Exception:
        return None


def _item_detalle_minimo():
    """Ítem alineado al payload que funciona en Postman (sin id_unidad)."""
    return {
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


def _item_detalle_completo():
    """Ítem con campos opcionales (descuentos)."""
    d = _item_detalle_minimo().copy()
    d["porcentaje_descuento"] = 0
    d["valor_descuento"] = 0
    return d


def payload_crear_venta_minimo():
    """Payload CREAR_VENTA alineado al que funciona en Postman."""
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
        "detalle_items": [_item_detalle_minimo()],
    }


def payload_crear_venta_completo():
    """Todos los campos (obligatorios + opcionales)."""
    p = payload_crear_venta_minimo().copy()
    p["id_medio_pago"] = None
    p["serie"] = None
    p["numero"] = None
    p["observaciones"] = "Test API campos obligatorios/opcionales"
    p["detalle_items"] = [_item_detalle_completo()]
    return p


def post_venta(payload: dict, token: str | None) -> tuple[int, dict]:
    """Envía CREAR_VENTA. Retorna (status_code, json)."""
    if not token:
        return 401, {"error": "Sin token"}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.post(URL_VENTA_SUNAT, json=payload, headers=headers, timeout=30)
        return r.status_code, r.json() if r.text else {}
    except Exception as e:
        return 0, {"error": str(e)}


def run_test(nombre: str, esperado_ok: bool, status: int, data: dict) -> bool:
    """Imprime resultado del test y retorna si pasó (resultado coherente con esperado_ok)."""
    ok = data.get("success", False) if isinstance(data, dict) else False
    paso = (ok == esperado_ok)
    simbolo = "[OK]" if paso else "[FAIL]"
    msg = (data.get("message") or data.get("error") or data.get("details") or "").strip()
    if not msg and isinstance(data, dict) and data.get("sunat"):
        msg = (data["sunat"].get("error") or data["sunat"].get("message") or "")
    msg_short = (msg[:80] + "…") if len(msg) > 80 else msg
    print(f"  {simbolo} {nombre}")
    print(f"      HTTP {status} | success={ok} (esperado success={esperado_ok})")
    if msg_short:
        print(f"      -> {msg_short}")
    return paso


def main():
    global TOKEN
    print("=" * 60)
    print("TEST API MARAVIA – Campos obligatorios y opcionales")
    print("=" * 60)

    # --- 1. LOGIN ---
    print("\n--- 1. LOGIN (ws_login.php) ---")
    # 1.1 Login completo (todos los campos) -> debe funcionar
    token = login(USER, PASSWORD)
    if token:
        TOKEN = token
        print("  [OK] Login con codOpe + username + password -> token obtenido")
    else:
        print("  [FAIL] Login con campos completos fallo (revisar credenciales o URL)")
        print("  Los tests de CREAR_VENTA se omitirán o usarán token en env.")
        token_env = os.environ.get("MARAVIA_TOKEN")
        if token_env:
            TOKEN = token_env
            print("  -> Usando MARAVIA_TOKEN de entorno")

    # 1.2 Sin password
    r = requests.post(URL_LOGIN, json={"codOpe": "LOGIN", "username": USER}, headers={"Content-Type": "application/json"}, timeout=10)
    data = r.json() if r.text else {}
    token_ok = data.get("token") or (data.get("data") or {}).get("token")
    if not token_ok:
        print("  [OK] Sin 'password' -> rechazado (esperado)")
    else:
        print("  [FAIL] Sin 'password' -> aceptado (no esperado)")

    # 1.3 Sin username
    r = requests.post(URL_LOGIN, json={"codOpe": "LOGIN", "password": PASSWORD}, headers={"Content-Type": "application/json"}, timeout=10)
    data = r.json() if r.text else {}
    token_ok = data.get("token") or (data.get("data") or {}).get("token")
    if not token_ok:
        print("  [OK] Sin 'username' -> rechazado (esperado)")
    else:
        print("  [FAIL] Sin 'username' -> aceptado (no esperado)")

    # 1.4 Sin codOpe
    r = requests.post(URL_LOGIN, json={"username": USER, "password": PASSWORD}, headers={"Content-Type": "application/json"}, timeout=10)
    data = r.json() if r.text else {}
    token_ok = data.get("token") or (data.get("data") or {}).get("token")
    if not token_ok:
        print("  [OK] Sin 'codOpe' -> rechazado (esperado)")
    else:
        print("  [FAIL] Sin 'codOpe' -> aceptado (no esperado)")

    # --- 2. CREAR_VENTA ---
    if not TOKEN:
        print("\n--- 2. CREAR_VENTA (omitido: sin token) ---")
        return

    print("\n--- 2. CREAR_VENTA (ws_ventas.php) ---")

    # 2.1 Payload mínimo (solo obligatorios) -> debe ser aceptado por API; SUNAT puede aceptar o rechazar por negocio
    status, data = post_venta(payload_crear_venta_minimo(), TOKEN)
    run_test("Payload MÍNIMO (solo campos obligatorios)", True, status, data)

    # 2.2 Payload completo (con opcionales)
    status, data = post_venta(payload_crear_venta_completo(), TOKEN)
    run_test("Payload COMPLETO (obligatorios + opcionales)", True, status, data)

    # 2.3 Sin id_cliente
    p = payload_crear_venta_minimo().copy()
    p.pop("id_cliente", None)
    status, data = post_venta(p, TOKEN)
    run_test("Sin 'id_cliente'", False, status, data)

    # 2.4 Sin fecha_emision
    p = payload_crear_venta_minimo().copy()
    p.pop("fecha_emision", None)
    status, data = post_venta(p, TOKEN)
    run_test("Sin 'fecha_emision'", False, status, data)

    # 2.5 Sin detalle_items
    p = payload_crear_venta_minimo().copy()
    p.pop("detalle_items", None)
    status, data = post_venta(p, TOKEN)
    run_test("Sin 'detalle_items'", False, status, data)

    # 2.6 detalle_items vacío
    p = payload_crear_venta_minimo().copy()
    p["detalle_items"] = []
    status, data = post_venta(p, TOKEN)
    run_test("'detalle_items' vacío []", False, status, data)

    # 2.7 Sin id_usuario
    p = payload_crear_venta_minimo().copy()
    p.pop("id_usuario", None)
    status, data = post_venta(p, TOKEN)
    run_test("Sin 'id_usuario'", False, status, data)

    # 2.8 Sin codOpe
    p = payload_crear_venta_minimo().copy()
    p.pop("codOpe", None)
    status, data = post_venta(p, TOKEN)
    run_test("Sin 'codOpe'", False, status, data)

    # 2.9 Sin id_tipo_comprobante
    p = payload_crear_venta_minimo().copy()
    p.pop("id_tipo_comprobante", None)
    status, data = post_venta(p, TOKEN)
    run_test("Sin 'id_tipo_comprobante'", False, status, data)

    # 2.10 Ítem sin valor_total_item (campo obligatorio en ítem)
    p = payload_crear_venta_minimo().copy()
    p["detalle_items"] = [{k: v for k, v in _item_detalle_minimo().items() if k != "valor_total_item"}]
    status, data = post_venta(p, TOKEN)
    run_test("Ítem sin 'valor_total_item'", False, status, data)

    print("\n" + "=" * 60)
    print("Fin del test de campos.")
    print("=" * 60)


if __name__ == "__main__":
    main()
