"""
Test aislado: enviar mensaje con botones interactivos vía ws_send_whatsapp_buttons.php

POST JSON a la API de MaravIA (WhatsApp Cloud / plataforma configurada).

Uso:
  python test/test_whatsapp_buttons.py
  python test/test_whatsapp_buttons.py 51994748961
  MARAVIA_PHONE=51994748961 MARAVIA_ID_EMPRESA=1 python test/test_whatsapp_buttons.py

Variables de entorno:
  URL_SEND_WHATSAPP_BUTTONS — override del endpoint
  MARAVIA_TOKEN — Bearer opcional (Authorization)
  MARAVIA_PHONE — destino (default: 51994748961)
  MARAVIA_ID_EMPRESA — id_empresa (default: 1)
  MARAVIA_ID_PLATAFORMA — id_plataforma (default: 6)
"""
from __future__ import annotations

import json
import os
import sys

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

import requests

from config import settings

URL_BUTTONS = os.environ.get("URL_SEND_WHATSAPP_BUTTONS") or getattr(
    settings, "URL_SEND_WHATSAPP_BUTTONS", "https://api.maravia.pe/servicio/n8n/ws_send_whatsapp_buttons.php"
)

PHONE_DEFAULT = os.environ.get("MARAVIA_PHONE", "51994748961")
ID_EMPRESA_DEFAULT = int(os.environ.get("MARAVIA_ID_EMPRESA", "1"))
ID_PLATAFORMA_DEFAULT = int(os.environ.get("MARAVIA_ID_PLATAFORMA", "6"))


def payload_default(
    phone: str,
    id_empresa: int = ID_EMPRESA_DEFAULT,
    id_plataforma: int = ID_PLATAFORMA_DEFAULT,
) -> dict:
    return {
        "id_empresa": id_empresa,
        "id_plataforma": id_plataforma,
        "phone": phone,
        "body_text": "hola si",
        "footer_text": "Selecciona una opción",
        "buttons": [
            {"id": "btn_ventas", "title": "ventas"},
            {"id": "btn_compras", "title": "compras"},
        ],
    }


def enviar_botones(
    phone: str,
    id_empresa: int = ID_EMPRESA_DEFAULT,
    id_plataforma: int = ID_PLATAFORMA_DEFAULT,
) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("MARAVIA_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = payload_default(phone=phone, id_empresa=id_empresa, id_plataforma=id_plataforma)
    return requests.post(URL_BUTTONS, json=body, headers=headers, timeout=60)


def run() -> None:
    phone = PHONE_DEFAULT
    id_empresa = ID_EMPRESA_DEFAULT
    id_plataforma = ID_PLATAFORMA_DEFAULT

    if len(sys.argv) >= 2:
        phone = sys.argv[1].strip()
    if len(sys.argv) >= 3:
        id_empresa = int(sys.argv[2])
    if len(sys.argv) >= 4:
        id_plataforma = int(sys.argv[3])

    payload = payload_default(phone=phone, id_empresa=id_empresa, id_plataforma=id_plataforma)

    print("--- REQUEST (ws_send_whatsapp_buttons) ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("\n--- POST", URL_BUTTONS, "---\n")

    try:
        res = enviar_botones(phone=phone, id_empresa=id_empresa, id_plataforma=id_plataforma)
    except requests.RequestException as e:
        print("❌ Error de conexión:", e)
        return

    print("--- RESPUESTA (raw) ---")
    print(res.text)

    if res.status_code in (502, 503, 504):
        print(f"\n⚠ Servidor no disponible (HTTP {res.status_code}).")
        return

    try:
        data = res.json()
    except ValueError:
        print("\n⚠ Respuesta no es JSON.")
        return

    print("\n--- RESPUESTA (JSON formateado) ---")
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run()
