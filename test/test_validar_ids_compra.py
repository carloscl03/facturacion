"""
Prueba de compatibilidad de id_tipo_comprobante en ws_compra.php (REGISTRAR_COMPRA).

Objetivo:
  - Enviar el mismo payload de compra variando solo id_tipo_comprobante.
  - Reportar que IDs son aceptados por la API y cuales fallan.

Variables de entorno:
  URL_COMPRA_N8N              Endpoint (default: https://api.maravia.pe/servicio/n8n/ws_compra.php)
  MARAVIA_TOKEN               Bearer opcional.
  MARAVIA_EMPRESA_ID          default: 2
  MARAVIA_USUARIO_ID          default: 3
  MARAVIA_ID_PROVEEDOR        default: 5
  MARAVIA_FECHA_EMISION       YYYY-MM-DD (default: hoy)
  MARAVIA_FECHA_PAGO          YYYY-MM-DD (default: fecha_emision)
  MARAVIA_FECHA_VENCIMIENTO   YYYY-MM-DD (default: fecha_pago)
  MARAVIA_IDS_COMPRA          Lista separada por comas (default: "1,2,3,4,5,6,7,8")
  MARAVIA_ID_CATALOGO_PRUEBA  default: 10
  MARAVIA_ID_SUCURSAL         default: 1
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import requests

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

from config import settings


def _get_url_compra() -> str:
    env = os.environ.get("URL_COMPRA_N8N")
    if env:
        return env
    if hasattr(settings, "URL_COMPRA_N8N"):
        return getattr(settings, "URL_COMPRA_N8N")
    return "https://api.maravia.pe/servicio/n8n/ws_compra.php"


URL_COMPRA = _get_url_compra()
EMPRESA_ID = int(os.environ.get("MARAVIA_EMPRESA_ID", "2"))
USUARIO_ID = int(os.environ.get("MARAVIA_USUARIO_ID", "3"))
ID_PROVEEDOR = int(os.environ.get("MARAVIA_ID_PROVEEDOR", "5"))
ID_CATALOGO_PRUEBA = int(os.environ.get("MARAVIA_ID_CATALOGO_PRUEBA", "10"))
ID_SUCURSAL = int(os.environ.get("MARAVIA_ID_SUCURSAL", "1"))

FECHA_EMISION = os.environ.get("MARAVIA_FECHA_EMISION") or date.today().isoformat()
FECHA_PAGO = os.environ.get("MARAVIA_FECHA_PAGO") or FECHA_EMISION
FECHA_VENCIMIENTO = os.environ.get("MARAVIA_FECHA_VENCIMIENTO") or FECHA_PAGO


def _parse_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        if p.isdigit():
            ids.append(int(p))
    return ids


IDS_A_PROBAR = _parse_ids(os.environ.get("MARAVIA_IDS_COMPRA", "1,2,3,4,5,6,7,8"))


def _payload_base(id_tipo_comprobante: int) -> dict:
    return {
        "codOpe": "REGISTRAR_COMPRA",
        "empresa_id": EMPRESA_ID,
        "usuario_id": USUARIO_ID,
        "id_proveedor": ID_PROVEEDOR,
        "id_tipo_comprobante": id_tipo_comprobante,
        "fecha_emision": FECHA_EMISION,
        "id_medio_pago": 1,
        "id_forma_pago": 1,
        "id_moneda": 1,
        "id_sucursal": ID_SUCURSAL,
        "tipo_compra": "Contado",
        "dias_credito": 0,
        "cuotas": 1,
        "porcentaje_detraccion": 0,
        "fecha_pago": FECHA_PAGO,
        "fecha_vencimiento": FECHA_VENCIMIENTO,
        "id_tipo_afectacion": 1,
        "observacion": f"Prueba IDs compra (id_tipo_comprobante={id_tipo_comprobante})",
        "id_caja_banco": 1,
        "id_centro_costo": 1,
        "id_tipo_compra_gasto": 1,
        "detalles": [
            {
                "id_inventario": None,
                "id_catalogo": ID_CATALOGO_PRUEBA,
                "id_tipo_producto": 1,
                "cantidad": 1,
                "id_unidad": 1,
                "precio_unitario": 118.0,
                "concepto": "Item prueba ids compra",
                "valor_subtotal_item": 100.0,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": 18.0,
                "valor_icbper": 0,
                "valor_total_item": 118.0,
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        ],
    }


def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("MARAVIA_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _safe_json(res: requests.Response) -> dict | None:
    try:
        data = res.json()
        if isinstance(data, dict):
            return data
        return {"_raw_json": data}
    except ValueError:
        return None


def run() -> None:
    if not IDS_A_PROBAR:
        print("No hay IDs validos en MARAVIA_IDS_COMPRA.")
        return

    print("--- VALIDACION IDS COMPRA (REGISTRAR_COMPRA) ---")
    print("Endpoint:", URL_COMPRA)
    print("IDs a probar:", IDS_A_PROBAR)
    print()

    resultados: list[dict] = []
    headers = _headers()

    for tipo_id in IDS_A_PROBAR:
        payload = _payload_base(tipo_id)
        print(f"===> Probando id_tipo_comprobante={tipo_id}")
        try:
            res = requests.post(URL_COMPRA, json=payload, headers=headers, timeout=60)
        except requests.RequestException as e:
            print("    Error de conexion:", e)
            resultados.append(
                {
                    "id": tipo_id,
                    "ok": False,
                    "http": None,
                    "error": f"conexion: {e}",
                }
            )
            continue

        data = _safe_json(res)
        success = bool(isinstance(data, dict) and data.get("success") is True)
        err = None
        id_compra = None
        if isinstance(data, dict):
            err = data.get("error") or data.get("message") or data.get("details")
            id_compra = data.get("id_compra")
        if data is None:
            err = (res.text or "")[:300]

        print(f"    HTTP {res.status_code} | success={success} | id_compra={id_compra}")
        if err:
            print(f"    detalle: {err}")

        resultados.append(
            {
                "id": tipo_id,
                "ok": success,
                "http": res.status_code,
                "id_compra": id_compra,
                "detalle": err,
            }
        )

    print("\n--- RESUMEN ---")
    aceptados = [r["id"] for r in resultados if r["ok"]]
    rechazados = [r["id"] for r in resultados if not r["ok"]]
    print("Aceptados:", aceptados if aceptados else "ninguno")
    print("Rechazados:", rechazados if rechazados else "ninguno")
    print("\nResultados completos:")
    print(json.dumps(resultados, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run()
