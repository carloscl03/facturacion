"""Envía una factura con el mínimo de campos requeridos (doc CREAR_VENTA) y muestra la respuesta y el PDF si fue aceptado."""
import os
import sys
import json
from datetime import date

# Permitir importar desde test/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from test_api_campos import (
    login,
    URL_VENTA_SUNAT,
    USER,
    PASSWORD,
)


def _payload_factura_minimo():
    """
    Payload mínimo según documentación CREAR_VENTA (ws_ventas.php):
    - Siempre requeridos: id_cliente, id_sucursal, tipo_venta, id_forma_pago, id_moneda, tipo_facturacion, detalle_items.
    - Por ítem: id_inventario, id_tipo_producto, cantidad, id_unidad, precio_unitario (+ valores IGV/descuento que exige el backend).
    - Condicional facturado: id_tipo_afectacion, id_tipo_comprobante.
    - Sin opcionales: id_medio_pago, serie, numero, observaciones.
    """
    hoy = date.today().isoformat()
    return {
        "codOpe": "CREAR_VENTA",
        "id_usuario": 3,
        "id_cliente": 5,
        "id_sucursal": 14,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "tipo_venta": "Contado",
        "fecha_emision": hoy,
        "fecha_pago": hoy,
        "id_tipo_afectacion": 1,
        "id_caja_banco": 4,
        "tipo_facturacion": "facturacion_electronica",
        "id_tipo_comprobante": 1,
        "detalle_items": [
            {
                "id_inventario": 7,
                "id_tipo_producto": 2,
                "cantidad": 1,
                "id_unidad": 1,
                "precio_unitario": 1111.00,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_subtotal_item": 941.53,
                "valor_igv": 169.47,
                "valor_total_item": 1111.00,
            }
        ],
    }


def _url_pdf_from_response(data):
    """Extrae la URL del PDF de la respuesta (sunat_data o payload.pdf)."""
    if not isinstance(data, dict):
        return None
    sunat = data.get("sunat") or {}
    sunat_data = sunat.get("sunat_data") or {}
    url = sunat_data.get("sunat_pdf") or sunat_data.get("enlace_documento")
    if url:
        return url
    payload = (sunat.get("data") or {}).get("payload") or {}
    pdf = payload.get("pdf")
    if isinstance(pdf, dict):
        return pdf.get("ticket") or pdf.get("a4")
    return None


def _es_rechazo_duplicado(data):
    """True si el rechazo es por comprobante ya emitido (duplicado)."""
    if not isinstance(data, dict):
        return False
    msg = (data.get("details") or data.get("error") or data.get("message") or "").lower()
    sunat_msg = (data.get("sunat") or {}).get("sunat_data", {}).get("sunat_error_mensaje") or ""
    return "emitido anteriormente" in msg or "emitido anteriormente" in sunat_msg.lower()


def _numero_usado_en_respuesta(data):
    """Devuelve el numero del comprobante en la respuesta (ej. 15) o None."""
    try:
        return (data.get("sunat") or {}).get("sunat_data", {}).get("numero")
    except Exception:
        return None


def main():
    token = login(USER, PASSWORD)
    if not token:
        print("No se obtuvo token.")
        return
    print("Token OK. Enviando CREAR_VENTA (factura) con payload MINIMO (doc)...\n")
    payload = _payload_factura_minimo()

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = None
    next_numero = None  # None = primero sin enviar numero; luego 16, 17, ...
    max_reintentos = 5  # probar numeros 16, 17, ... hasta 5 intentos mas

    for intento in range(max_reintentos + 1):
        if next_numero is not None:
            payload["numero"] = next_numero
            print(f"Reintento {intento} con numero={next_numero}...")
        else:
            print("Payload enviado:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        print()
        r = requests.post(URL_VENTA_SUNAT, json=payload, headers=headers, timeout=30)
        data = r.json() if r.text else {}
        print("HTTP", r.status_code)

        url_pdf = _url_pdf_from_response(data)
        if url_pdf:
            print("\n--- PDF COMPROBANTE ---")
            print(url_pdf)
            print()
            break
        if data.get("success"):
            break
        if _es_rechazo_duplicado(data) and intento < max_reintentos:
            usado = _numero_usado_en_respuesta(data)
            if next_numero is not None:
                next_numero += 1
            else:
                next_numero = (usado + 1) if isinstance(usado, int) else 16
            continue
        if not data.get("success") and not _url_pdf_from_response(data or {}):
            motivo = (data or {}).get("details") or (data or {}).get("error") or (data or {}).get("message") or ""
            print("\n--- POR QUE NO HAY PDF ---")
            print("SUNAT rechazo el comprobante.")
            if motivo:
                print("Motivo:", motivo)
            print("El PDF solo se devuelve cuando SUNAT ACEPTA.")
        break

    print("Respuesta completa:")
    try:
        print(json.dumps(data or {}, indent=2, ensure_ascii=False))
    except Exception:
        print(r.text if data is None else "")


if __name__ == "__main__":
    main()
