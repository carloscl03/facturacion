"""
Test aislado: venta con payload hardcodeado (CREAR_VENTA o REGISTRAR_VENTA_N8N).
No conecta a historial ni login; solo envía el JSON al endpoint e imprime la respuesta.

Contrato REGISTRAR_VENTA_N8N (php/ventan8n.txt, ws_venta.php):
  - Requeridos en body: codOpe, empresa_id, usuario_id (validados antes del switch).
  - En registrarVentaN8N: id_cliente, fecha_emision, id_moneda; detalle_items o detalles (array, ≥1 ítem).
  - generacion_comprobante = 1 → genera comprobante SUNAT y devuelve pdf_url y sunat_estado.
  - Respuesta éxito (201): success, message, id_venta, codigo_venta, serie, numero, cronograma;
    si facturación electrónica: sunat_estado, pdf_url (enlace_documento) en la raíz.
"""
import json
import os
import sys
from datetime import date

# Raíz del proyecto para importar config
_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

import requests

from config import settings

# Endpoint N8N (ws_ventas.php o ws_venta.php). Override con URL_VENTA_SUNAT en config o env.
URL_VENTA = os.environ.get("URL_VENTA_SUNAT") or getattr(settings, "URL_VENTA_SUNAT", "https://api.maravia.pe/servicio/n8n/ws_venta.php")

# Empresa y usuario fijos
EMPRESA_ID = 2
USUARIO_ID = 3

# SUNAT valida que la fecha de emisión sea hoy o hasta 3 días previos.
# Por defecto usamos hoy; puedes override con MARAVIA_FECHA_EMISION=YYYY-MM-DD
FECHA_EMISION = os.environ.get("MARAVIA_FECHA_EMISION") or date.today().isoformat()

# Payload REGISTRAR_VENTA_N8N (ventan8n.txt): empresa_id, usuario_id, id_cliente, fecha_emision, id_moneda,
# detalle_items o detalles, generacion_comprobante=1 para PDF SUNAT.
PAYLOAD_REGISTRAR_VENTA_N8N = {
    "codOpe": "REGISTRAR_VENTA_N8N",
    "empresa_id": EMPRESA_ID,
    "usuario_id": USUARIO_ID,
    "id_cliente": 5,
    "id_tipo_comprobante": 7,   # 7 = Nota de venta (salta bloque SUNAT)
    "fecha_emision": FECHA_EMISION,
    "fecha_pago": FECHA_EMISION,
    "id_moneda": 1,
    "id_forma_pago": 9,
    "id_medio_pago": None,
    "id_sucursal": 14,
    "tipo_venta": "Contado",
    "observaciones": "Prueba Nota de Venta - test aislamiento bug",
    "generacion_comprobante": 0,  # Sin SUNAT: salta generarFacturaElectronica
    "detalle_items": [
        {
            "id_inventario": None,
            "id_catalogo": None,
            "id_tipo_producto": 2,
            "cantidad": 1,
            "id_unidad": 1,
            "precio_unitario": 1111.00,
            "valor_subtotal_item": 941.53,
            "porcentaje_descuento": 0,
            "valor_descuento": 0,
            "valor_isc": 0,
            "valor_igv": 169.47,
            "valor_icbper": 0,
            "valor_total_item": 1111.00,
            "anticipo": 0,
            "otros_cargos": 0,
            "otros_tributos": 0,
        }
    ],
}


def run():
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("MARAVIA_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = PAYLOAD_REGISTRAR_VENTA_N8N
    print("--- REQUEST (REGISTRAR_VENTA_N8N) ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("\n--- POST", URL_VENTA, "---\n")

    try:
        res = requests.post(URL_VENTA, json=payload, headers=headers, timeout=30)
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

    # Resumen: soporta respuesta REGISTRAR_VENTA_N8N (id_venta, pdf_url en raíz) y CREAR_VENTA (id, sunat.sunat_data)
    if data.get("success"):
        print("\n--- RESUMEN ---")
        print("✅ success:", data.get("success"))
        print("🆔 id_venta:", data.get("id_venta") or data.get("id"))
        if data.get("message"):
            print("📋 message:", data.get("message"))
        if data.get("sunat_message"):
            print("📋 sunat_message:", data.get("sunat_message"))

        # PDF: REGISTRAR_VENTA_N8N devuelve pdf_url en raíz; CREAR_VENTA en sunat.sunat_data / payload.pdf
        pdf_url = data.get("pdf_url") or data.get("url_pdf")
        if not pdf_url:
            sunat = data.get("sunat") or {}
            sunat_data = sunat.get("sunat_data") or {}
            payload_data = (sunat.get("data") or {}).get("payload") or {}
            pdf_obj = payload_data.get("pdf") if isinstance(payload_data.get("pdf"), dict) else {}
            pdf_url = (
                sunat_data.get("sunat_pdf")
                or sunat_data.get("enlace_documento")
                or pdf_obj.get("ticket")
                or pdf_obj.get("a4")
            )
        if pdf_url:
            print("📄 PDF:", pdf_url)

        sunat_estado = data.get("sunat_estado")
        if not sunat_estado and data.get("sunat"):
            sd = (data.get("sunat") or {}).get("sunat_data") or {}
            sunat_estado = sd.get("sunat_estado") if isinstance(sd, dict) else None
        if sunat_estado:
            print("📋 sunat_estado:", sunat_estado)
        if data.get("serie") or data.get("numero") is not None:
            print("📄 Comprobante:", data.get("serie"), "-", data.get("numero"))
        elif data.get("sunat") and (data.get("sunat") or {}).get("sunat_data"):
            sd = (data.get("sunat") or {}).get("sunat_data") or {}
            if sd.get("serie") or sd.get("numero") is not None:
                print("📄 Comprobante:", sd.get("serie"), "-", sd.get("numero"))

        crono = data.get("cronograma")
        if crono is not None:
            print("📅 cronograma:", crono.get("generado"), "| cuotas:", crono.get("cuotas_insertadas"))
    else:
        err = (
            (data.get("sunat") or {}).get("sunat_data") or {}
        ).get("sunat_error_mensaje") or data.get("message") or data.get("error") or data.get("details") or res.text[:300]
        print("\n❌ Error:", err)


if __name__ == "__main__":
    run()
