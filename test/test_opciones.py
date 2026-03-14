"""
Test de opciones: centros de costo, métodos de pago y sucursales y envío a WhatsApp.

- Tablas (centros de costo, sucursales, métodos de pago) se obtienen con id_empresa = 2.
- El envío de mensajes a WhatsApp usa id_from = 1 (credenciales), igual que test_obtener_pagos.py.
  En el payload a ws_send_whatsapp_list.php se envía como id_empresa = id_whatsapp (1).

Convención (como en test_obtener_pagos.py): id_empresa = 2 para jalar tablas; id_whatsapp = 1 (id_from) para enviar.

Uso:
  python test/test_opciones.py                      # wa_id, id_empresa=2, id_whatsapp=1
  python test/test_opciones.py 51994748961          # wa_id
  python test/test_opciones.py 51994748961 2 1      # wa_id, id_empresa (tablas), id_whatsapp (enviar)
"""
import json
import sys

import requests

URL_PARAMETROS = "https://api.maravia.pe/servicio/n8n/ws_parametros.php"
URL_INFORMACION = "https://api.maravia.pe/servicio/ws_informacion_ia.php"
URL_WHATSAPP_LIST = "https://api.maravia.pe/servicio/n8n/ws_send_whatsapp_list.php"

DEFAULT_WA_ID = "51994748961"
# id_empresa = 2: de donde se jala las tablas (centros costo, sucursales, métodos pago)
DEFAULT_ID_EMPRESA = 2
# id_whatsapp = 1 (id_from): para enviar mensajes a WhatsApp (credenciales)
DEFAULT_ID_WHATSAPP = 1


def obtener_solo_centros_costo(wa_id: str) -> list[dict]:
    """
    GET ws_parametros OBTENER_TABLAS_MAESTRAS; devuelve solo la tabla centros_costo.
    No imprime ni devuelve el resto de la respuesta.
    """
    params = {"codOpe": "OBTENER_TABLAS_MAESTRAS", "wa_id": wa_id}
    try:
        resp = requests.get(URL_PARAMETROS, params=params, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    tablas = data.get("tablas_maestras") if isinstance(data, dict) else None
    if not isinstance(tablas, dict):
        return []
    centros = tablas.get("centros_costo")
    return centros if isinstance(centros, list) else []


def obtener_sucursales(id_empresa: int) -> list[dict]:
    """POST ws_informacion_ia OBTENER_SUCURSALES con id_empresa. Devuelve solo la lista sucursales."""
    payload = {"codOpe": "OBTENER_SUCURSALES", "id_empresa": id_empresa}
    try:
        resp = requests.post(
            URL_INFORMACION,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    sucursales = data.get("sucursales") if isinstance(data, dict) else []
    return sucursales if isinstance(sucursales, list) else []


def obtener_metodos_pago(id_empresa: int) -> dict:
    """POST ws_informacion_ia OBTENER_METODOS_PAGO con id_empresa. Devuelve la respuesta (para extraer métodos)."""
    payload = {"codOpe": "OBTENER_METODOS_PAGO", "id_empresa": id_empresa}
    try:
        resp = requests.post(
            URL_INFORMACION,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {}
        return resp.json()
    except Exception:
        return {}


# Límites WhatsApp list message: row title 24, row description 72
MAX_ROW_TITLE = 24
MAX_ROW_DESC = 72


def _truncar(s: str, max_len: int) -> str:
    if not s or max_len <= 0:
        return (s or "")[:max_len] if max_len > 0 else ""
    return s[:max_len] if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"


def extraer_filas_centros_costo(centros: list) -> list[dict]:
    """Solo el nombre del centro de costo (title ≤24), sin descripción."""
    if not isinstance(centros, list):
        return []
    filas = []
    for c in centros:
        if isinstance(c, dict):
            cid = c.get("id")
            nombre = (c.get("nombre") or "").strip() or str(cid)
            filas.append({
                "id": str(cid),
                "title": _truncar(nombre, MAX_ROW_TITLE),
                "description": "",
            })
        elif isinstance(c, (str, int)):
            filas.append({"id": str(c), "title": _truncar(str(c), MAX_ROW_TITLE), "description": ""})
    return filas


def extraer_filas_sucursales(sucursales: list) -> list[dict]:
    """Convierte lista sucursales (id, nombre) en filas para lista WhatsApp (title ≤24)."""
    if not isinstance(sucursales, list):
        return []
    filas = []
    for s in sucursales:
        if isinstance(s, dict):
            sid = s.get("id")
            nombre = (s.get("nombre") or "").strip() or str(sid)
            filas.append({"id": str(sid), "title": _truncar(nombre, MAX_ROW_TITLE), "description": ""})
        elif isinstance(s, (str, int)):
            filas.append({"id": str(s), "title": _truncar(str(s), MAX_ROW_TITLE), "description": ""})
    return filas


def extraer_filas_metodos_pago(respuesta: dict) -> list[dict]:
    """Solo el nombre del método de pago (title ≤24), sin descripción."""
    if not isinstance(respuesta, dict):
        return []
    mp = respuesta.get("metodos_pago")
    if not isinstance(mp, dict):
        return []
    filas = []
    bancos = mp.get("bancos") or []
    for b in bancos if isinstance(bancos, list) else []:
        if isinstance(b, dict):
            bid = b.get("id")
            nombre = (b.get("nombre") or "").strip() or str(bid)
            filas.append({"id": str(bid), "title": _truncar(nombre, MAX_ROW_TITLE), "description": ""})
    if mp.get("yape") and isinstance(mp["yape"], dict):
        filas.append({"id": "yape", "title": "Yape", "description": ""})
    if mp.get("plin") and isinstance(mp["plin"], dict):
        filas.append({"id": "plin", "title": "Plin", "description": ""})
    return filas


def build_payload_whatsapp(id_empresa: int, phone: str, section_title: str, rows: list[dict], body: str, header: str, footer: str, button: str, id_plataforma: int = 6) -> dict:
    """Payload genérico para ws_send_whatsapp_list.php (id_plataforma requerido por la API)."""
    if not rows:
        rows = [{"id": "0", "title": f"Sin {section_title.lower()}", "description": ""}]
    return {
        "id_empresa": id_empresa,
        "id_plataforma": id_plataforma,
        "phone": phone,
        "body_text": body,
        "button_text": button,
        "header_text": header,
        "footer_text": footer,
        "sections": [{"title": section_title, "rows": rows}],
    }


def enviar_lista_whatsapp(id_empresa: int, phone: str, payload: dict) -> bool:
    """Envía un list message a WhatsApp. Retorna True si status 200."""
    try:
        resp = requests.post(URL_WHATSAPP_LIST, json=payload, timeout=30)
        print("  Status:", resp.status_code)
        if resp.status_code != 200:
            return False
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not body.get("success") and "credenciales" in (body.get("error") or "").lower():
            print("  >>> id_empresa sin credenciales WhatsApp en el backend.")
        return True
    except requests.RequestException as e:
        print("  Error:", e)
        return False


def main():
    wa_id = DEFAULT_WA_ID
    id_empresa = DEFAULT_ID_EMPRESA
    id_whatsapp = DEFAULT_ID_WHATSAPP
    if len(sys.argv) >= 4:
        wa_id = sys.argv[1]
        id_empresa = int(sys.argv[2])
        id_whatsapp = int(sys.argv[3])
    elif len(sys.argv) == 3:
        wa_id = sys.argv[1]
        id_empresa = int(sys.argv[2])
    elif len(sys.argv) == 2:
        wa_id = sys.argv[1]

    print("id_empresa (tablas) =", id_empresa, "| id_whatsapp (id_from, enviar) =", id_whatsapp, "| phone =", wa_id)
    print("-" * 50)

    # 1) Solo tabla centros de costo (no todo el JSON)
    print("1) Centros de costo (solo tabla) — GET ws_parametros OBTENER_TABLAS_MAESTRAS")
    centros = obtener_solo_centros_costo(wa_id)
    print("centros_costo:", json.dumps(centros, ensure_ascii=False, indent=2))
    filas_centros = extraer_filas_centros_costo(centros)
    print("Filas para lista:", len(filas_centros))
    print("-" * 50)

    # 2) Sucursales desde ws_informacion_ia (id_empresa=2)
    print("2) Sucursales (solo tabla) — POST ws_informacion_ia OBTENER_SUCURSALES id_empresa=", id_empresa)
    sucursales = obtener_sucursales(id_empresa)
    print("sucursales:", json.dumps(sucursales, ensure_ascii=False, indent=2))
    filas_suc = extraer_filas_sucursales(sucursales)
    print("Filas para lista:", len(filas_suc))
    print("-" * 50)

    # 3) Métodos de pago desde ws_informacion_ia (id_empresa=2)
    print("3) Métodos de pago (solo tabla) — POST ws_informacion_ia OBTENER_METODOS_PAGO id_empresa=", id_empresa)
    data_pagos = obtener_metodos_pago(id_empresa)
    filas_pagos = extraer_filas_metodos_pago(data_pagos)
    # Mostrar solo la estructura de métodos (metodos_pago) si existe, no todo el JSON
    mp = data_pagos.get("metodos_pago") if isinstance(data_pagos, dict) else None
    print("metodos_pago (resumen):", json.dumps(mp, ensure_ascii=False, indent=2) if isinstance(mp, dict) else data_pagos)
    print("Filas para lista:", len(filas_pagos))
    print("-" * 50)

    # Envío a WhatsApp con id_whatsapp = 1 (id_from), como en test_obtener_pagos.py
    print("4) Envío a WhatsApp (opciones) — id_empresa = id_whatsapp =", id_whatsapp)
    p1 = build_payload_whatsapp(
        id_whatsapp, wa_id,
        "Centros de costo", filas_centros,
        "Centros de costo disponibles: ", "Centros de costo", "Selecciona un centro de costo", "Ver centros de costo",
    )
    print("  Centros de costo:")
    enviar_lista_whatsapp(id_whatsapp, wa_id, p1)

    p2 = build_payload_whatsapp(
        id_whatsapp, wa_id,
        "Sucursales", filas_suc,
        "Sucursales disponibles: ", "Sucursales", "Selecciona una sucursal", "Ver sucursales",
    )
    print("  Sucursales:")
    enviar_lista_whatsapp(id_whatsapp, wa_id, p2)

    p3 = build_payload_whatsapp(
        id_whatsapp, wa_id,
        "Métodos de pago", filas_pagos,
        "Métodos de pago disponibles: ", "Métodos de pago", "Selecciona un método de pago", "Ver métodos de pago",
    )
    print("  Métodos de pago:")
    enviar_lista_whatsapp(id_whatsapp, wa_id, p3)

    print("-" * 50)
    print("OK: centros de costo, sucursales y métodos de pago obtenidos (solo tablas) y enviados a WhatsApp.")


if __name__ == "__main__":
    main()
