"""
Test de OBTENER_METODOS_PAGO (ws_informacion_ia.php) y envío del resultado a WhatsApp.

1. POST a ws_informacion_ia.php con codOpe=OBTENER_METODOS_PAGO e id_from (id_informacion). Se imprime primero la salida de la API.
2. Construye un list message con la respuesta y lo envía a WhatsApp (ws_send_whatsapp_list.php) con id_empresa (id_whatsapp).

Convención: id_informacion = id_from (API de información); id_whatsapp = id_empresa (API WhatsApp).

Uso:
  python test/test_obtener_pagos.py                      # id_informacion=2, id_whatsapp=1, phone por defecto
  python test/test_obtener_pagos.py 2 1 51999999999     # id_informacion, id_whatsapp, phone
"""
import json
import sys

import requests

URL_INFORMACION = "https://api.maravia.pe/servicio/ws_informacion_ia.php"
URL_WHATSAPP_LIST = "https://api.maravia.pe/servicio/n8n/ws_send_whatsapp_list.php"

# API información: se envía como id_from (contexto/empresa de la que se obtienen métodos de pago)
DEFAULT_ID_INFORMACION = 2
# API WhatsApp: se envía como id_empresa (credenciales de envío)
DEFAULT_ID_WHATSAPP = 1
DEFAULT_PHONE = "51999999999"


def obtener_metodos_pago(id_informacion: int) -> dict:
    """POST a ws_informacion_ia.php con codOpe=OBTENER_METODOS_PAGO e id_from (id_informacion)."""
    payload = {
        "codOpe": "OBTENER_METODOS_PAGO",
        "id_from": id_informacion,
    }
    try:
        resp = requests.post(
            URL_INFORMACION,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        return {"status": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}
    except requests.RequestException as e:
        return {"status": 0, "error": str(e)}


def extraer_filas_metodos(respuesta: dict) -> list[dict]:
    """
    Extrae lista de métodos de pago de la respuesta.
    Acepta formato plano (data/items) o el formato real de la API:
    metodos_pago: { bancos: [...], yape: {...}|null, plin: {...}|null }
    """
    if not isinstance(respuesta, dict):
        return []
    filas = []

    # Formato real: metodos_pago con bancos, yape, plin
    mp = respuesta.get("metodos_pago")
    if isinstance(mp, dict):
        bancos = mp.get("bancos") or []
        for b in bancos if isinstance(bancos, list) else []:
            if isinstance(b, dict):
                bid = b.get("id")
                nombre = (b.get("nombre") or "").strip() or str(bid)
                num = (b.get("numero_cuenta") or "").strip()
                cci = (b.get("cci") or "").strip()
                desc = " | ".join(x for x in [num, cci] if x)
                filas.append({"id": str(bid), "title": nombre, "description": desc})
        if mp.get("yape") and isinstance(mp["yape"], dict):
            cel = (mp["yape"].get("celular") or "").strip()
            filas.append({"id": "yape", "title": "Yape", "description": cel or "Billetera Yape"})
        if mp.get("plin") and isinstance(mp["plin"], dict):
            cel = (mp["plin"].get("celular") or "").strip()
            filas.append({"id": "plin", "title": "Plin", "description": cel or "Billetera Plin"})
        if filas:
            return filas

    # Formato plano: data, items, etc.
    raw = (
        respuesta.get("data")
        or respuesta.get("metodos")
        or respuesta.get("items")
        or respuesta.get("result")
        or []
    )
    if not isinstance(raw, list):
        return []
    for item in raw:
        if isinstance(item, dict):
            mid = item.get("id") or item.get("id_metodo_pago") or item.get("id_medio_pago")
            nombre = (
                item.get("nombre")
                or item.get("nombre_metodo")
                or item.get("descripcion")
                or item.get("name")
                or ""
            ).strip() or str(mid)
            desc = (item.get("description") or item.get("descripcion") or "").strip()
            filas.append({"id": str(mid), "title": nombre, "description": desc})
        elif isinstance(item, (str, int)):
            filas.append({"id": str(item), "title": str(item), "description": ""})
    return filas


def build_payload_whatsapp(id_whatsapp: int, phone: str, filas: list[dict], id_plataforma: int = 6) -> dict:
    """Payload para ws_send_whatsapp_list.php; id_whatsapp se envía como id_empresa; id_plataforma requerido por la API."""
    if not filas:
        filas = [{"id": "0", "title": "Sin métodos de pago", "description": ""}]
    return {
        "id_empresa": id_whatsapp,
        "id_plataforma": id_plataforma,
        "phone": phone,
        "body_text": "Métodos de pago disponibles: ",
        "button_text": "Ver métodos de pago",
        "header_text": "Métodos de pago",
        "footer_text": "Selecciona un método de pago",
        "sections": [{"title": "Métodos de pago", "rows": filas}],
    }


def main():
    id_informacion = DEFAULT_ID_INFORMACION
    id_whatsapp = DEFAULT_ID_WHATSAPP
    phone = DEFAULT_PHONE
    if len(sys.argv) >= 4:
        id_informacion = int(sys.argv[1])
        id_whatsapp = int(sys.argv[2])
        phone = sys.argv[3]
    elif len(sys.argv) == 3:
        id_informacion = int(sys.argv[1])
        id_whatsapp = int(sys.argv[2])
    elif len(sys.argv) == 2:
        id_informacion = int(sys.argv[1])

    print("1) POST ws_informacion_ia.php — OBTENER_METODOS_PAGO")
    print("   URL:", URL_INFORMACION)
    print("   Payload (id_from = id_informacion):", json.dumps({"codOpe": "OBTENER_METODOS_PAGO", "id_from": id_informacion}, ensure_ascii=False))
    print("-" * 50)

    result = obtener_metodos_pago(id_informacion)
    if result.get("status") != 200:
        print("Error API:", result.get("error", result.get("data", "Unknown")))
        sys.exit(1)

    data = result.get("data")
    if isinstance(data, str):
        print("Salida de la API (text):", data[:500])
        sys.exit(1)

    print("Salida de la API (JSON):")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    filas = extraer_filas_metodos(data)
    print("-" * 50)
    print("Filas extraídas para la lista:", len(filas))
    if filas:
        print(json.dumps(filas, ensure_ascii=False, indent=2))

    payload_wsp = build_payload_whatsapp(id_whatsapp, phone, filas)
    print("-" * 50)
    print("2) POST a WhatsApp (lista)")
    print("   URL:", URL_WHATSAPP_LIST)
    print("   id_empresa = id_whatsapp =", id_whatsapp, "| phone =", phone)
    print("Payload enviado:", json.dumps(payload_wsp, ensure_ascii=False, indent=2))
    print("-" * 50)

    try:
        resp = requests.post(URL_WHATSAPP_LIST, json=payload_wsp, timeout=30)
        print("Status:", resp.status_code)
        try:
            body = resp.json()
            print("Response (JSON):", json.dumps(body, ensure_ascii=False, indent=2))
            if not body.get("success") and "credenciales" in (body.get("error") or "").lower():
                print("-" * 50)
                print(">>> Este id_whatsapp (id_empresa) no tiene credenciales de WhatsApp en el backend.")
        except Exception:
            print("Response (text):", resp.text[:500])
    except requests.RequestException as e:
        print("Error de red:", e)
        sys.exit(1)

    if resp.status_code != 200:
        sys.exit(1)
    print("-" * 50)
    print("OK: métodos de pago obtenidos y enviados a WhatsApp.")


if __name__ == "__main__":
    main()
