"""
Test de inventario público: obtiene el catálogo (OBTENER_CATALOGO), filtra
visible_publico == 1, y envía la lista como mensaje lista a WhatsApp (como test_opciones).

Convención (igual que test_opciones.py): id_empresa para jalar catálogo; id_whatsapp para enviar.

Uso:
  python test/test_inventario.py                      # wa_id, id_empresa=2, id_whatsapp=1
  python test/test_inventario.py 51994748961          # wa_id
  python test/test_inventario.py 51994748961 2 1      # wa_id, id_empresa (catálogo), id_whatsapp (enviar)
"""
import json
import sys

import requests

URL_INFORMACION = "https://api.maravia.pe/servicio/ws_informacion_ia.php"
URL_WHATSAPP_LIST = "https://api.maravia.pe/servicio/n8n/ws_send_whatsapp_list.php"

DEFAULT_WA_ID = "51994748961"
DEFAULT_ID_EMPRESA = 1
DEFAULT_ID_WHATSAPP = 1

# Límite WhatsApp list message: row title 24 caracteres (como test_opciones)
MAX_ROW_TITLE = 24


def _truncar(s: str, max_len: int) -> str:
    if not s or max_len <= 0:
        return (s or "")[:max_len] if max_len > 0 else ""
    return s[:max_len] if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"


def obtener_catalogo(id_empresa: int) -> dict:
    """POST ws_informacion_ia OBTENER_CATALOGO con id_empresa. Devuelve la respuesta cruda."""
    payload = {"codOpe": "OBTENER_CATALOGO", "id_empresa": id_empresa}
    try:
        resp = requests.post(
            URL_INFORMACION,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"success": False, "catalogo": []}
        return resp.json()
    except Exception:
        return {"success": False, "catalogo": []}


def inventario_publico(id_empresa: int) -> list[dict]:
    """
    Obtiene del catálogo solo los ítems con visible_publico == 1
    y devuelve lista de {"id": int, "nombre": str}.
    """
    data = obtener_catalogo(id_empresa)
    if not data.get("success") or not isinstance(data.get("catalogo"), list):
        return []
    catalogo = data["catalogo"]
    out = []
    for item in catalogo:
        if not isinstance(item, dict):
            continue
        visible = item.get("visible_publico")
        if visible != 1 and visible is not True:
            continue
        pid = item.get("id")
        nombre = (item.get("nombre") or "").strip()
        if pid is not None:
            out.append({"id": pid, "nombre": nombre or str(pid)})
    return out


def extraer_filas_inventario(items: list[dict]) -> list[dict]:
    """Convierte inventario (id, nombre) en filas para lista WhatsApp (title ≤24)."""
    if not isinstance(items, list):
        return []
    filas = []
    for it in items:
        if isinstance(it, dict):
            pid = it.get("id")
            nombre = (it.get("nombre") or "").strip() or str(pid)
            filas.append({"id": str(pid), "title": _truncar(nombre, MAX_ROW_TITLE), "description": ""})
    return filas


def build_payload_whatsapp(
    id_empresa: int, phone: str, section_title: str, rows: list[dict],
    body: str, header: str, footer: str, button: str, id_plataforma: int = 6,
) -> dict:
    """Payload para ws_send_whatsapp_list.php (id_plataforma requerido por la API, igual que test_opciones)."""
    if not rows:
        rows = [{"id": "0", "title": "Sin productos", "description": ""}]
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
            try:
                err = resp.json()
                print("  Respuesta API:", json.dumps(err, ensure_ascii=False, indent=2))
            except Exception:
                print("  Body:", resp.text[:500] if resp.text else "(vacío)")
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

    print("id_empresa (catálogo) =", id_empresa, "| id_whatsapp (enviar) =", id_whatsapp, "| phone =", wa_id)
    print("-" * 50)

    print("1) Catálogo público — POST ws_informacion_ia OBTENER_CATALOGO id_empresa=", id_empresa)
    items = inventario_publico(id_empresa)
    print("   Inventario público (visible_publico=1):", len(items), "ítems")
    filas = extraer_filas_inventario(items)
    print("   Filas para lista WhatsApp:", len(filas))
    print("-" * 50)

    print("2) Envío a WhatsApp — id_empresa = id_whatsapp =", id_whatsapp)
    payload = build_payload_whatsapp(
        id_whatsapp, wa_id,
        "Inventario",
        filas,
        "Productos disponibles: ",
        "Inventario público",
        "Selecciona un producto",
        "Ver inventario",
    )
    enviar_lista_whatsapp(id_whatsapp, wa_id, payload)
    print("-" * 50)
    print("OK: inventario público obtenido y enviado como lista a WhatsApp.")


if __name__ == "__main__":
    sys.exit(main() or 0)
