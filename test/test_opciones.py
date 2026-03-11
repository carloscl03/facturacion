"""
Test del endpoint PHP ws_send_whatsapp_list.php.
Envía un JSON de lista interactiva (list message) y muestra la respuesta.

Este PHP es el único que recibe id_empresa (credenciales WhatsApp por empresa).
El resto del proyecto usa id_from como identificador de contexto.

Uso:
  python test_opciones.py                    # id_empresa=1, phone por defecto
  python test_opciones.py 2 51994748961     # id_empresa=2, phone=51994748961

Nota: Si devuelve 404 "No se encontraron credenciales de WhatsApp para la empresa",
es que ese id_empresa no tiene credenciales en la BD del backend. Probar con id_empresa=1.
"""
import json
import sys

import requests

URL = "https://api.maravia.pe/servicio/n8n/ws_send_whatsapp_list.php"

DEFAULT_ID_EMPRESA = 1
DEFAULT_PHONE = "51994748961"


def build_payload(id_empresa: int, phone: str) -> dict:
    return {
        "id_empresa": id_empresa,
        "phone": phone,
        "body_text": "Selecciona entre estas opciones: ",
        "button_text": "Ver opciones",
        "header_text": "Nuestros Servicios",
        "footer_text": "Selecciona una opción",
        "sections": [
            {
                "title": "Operaciones",
                "rows": [
                    {"id": "ventas", "title": "Ventas", "description": "Realizar una operacion de ventas"},
                    {"id": "compras", "title": "Compras", "description": "Realizar una operacion de compras"},
                    {"id": "gastos", "title": "Gastos", "description": "Realizar una operacion de gastos"},
                ],
            }
        ],
    }


def main():
    id_empresa = DEFAULT_ID_EMPRESA
    phone = DEFAULT_PHONE
    if len(sys.argv) >= 3:
        id_empresa = int(sys.argv[1])
        phone = sys.argv[2]
    elif len(sys.argv) == 2:
        id_empresa = int(sys.argv[1])

    payload = build_payload(id_empresa, phone)

    print("Enviando POST a:", URL)
    print("id_empresa =", id_empresa, "| phone =", phone)
    print("Payload:", json.dumps(payload, ensure_ascii=False, indent=2))
    print("-" * 50)

    try:
        resp = requests.post(URL, json=payload, timeout=30)
        print("Status:", resp.status_code)
        try:
            body = resp.json()
            print("Response (JSON):", json.dumps(body, ensure_ascii=False, indent=2))
            if not body.get("success") and "credenciales" in (body.get("error") or "").lower():
                print("-" * 50)
                print(">>> Este id_empresa no tiene credenciales de WhatsApp en el backend.")
                print("    Probar con id_empresa=1 o configurar credenciales para esta empresa.")
        except Exception:
            print("Response (text):", resp.text[:500])
    except requests.RequestException as e:
        print("Error de red:", e)
        sys.exit(1)

    if resp.status_code != 200:
        sys.exit(1)
    print("-" * 50)
    print("OK: request completado.")


if __name__ == "__main__":
    main()
