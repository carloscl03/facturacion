"""
Test: enviar PDF por WhatsApp vía ws_send_whatsapp_oficial.php

Envía un documento (PDF) usando la API oficial de WhatsApp Cloud.
El endpoint ws_send_whatsapp_oficial.php soporta type="document" con:
  - document_url: URL pública del PDF (requerido)
  - filename: nombre del archivo (requerido)
  - message: caption opcional

Uso:
  python test/test_pdf_wsp.py
  python test/test_pdf_wsp.py 51999999998 2    # phone, id_empresa
  PHONE=51999999998 ID_EMPRESA=2 python test/test_pdf_wsp.py
"""
import json
import os
import sys

import requests

# Raíz del proyecto para importar config
_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

from config import settings

URL_WHATSAPP = os.environ.get("URL_SEND_WHATSAPP_OFICIAL") or settings.URL_SEND_WHATSAPP_OFICIAL

# PDF de comprobante SUNAT (ejemplo)
PDF_URL = "https://maravia-uploads.s3.us-east-1.amazonaws.com/uploads/comprobantes_sunat/2/comprobante_FM01-110_a4_20260319_125753.pdf"
PDF_FILENAME = "comprobante_FM01-110.pdf"

# Parámetros por defecto (override con env o args)
PHONE_DEFAULT = os.environ.get("PHONE", "51999999999")
ID_EMPRESA_DEFAULT = int(os.environ.get("ID_EMPRESA", "1"))


def enviar_pdf_whatsapp(
    phone: str,
    document_url: str = PDF_URL,
    filename: str = PDF_FILENAME,
    caption: str = "",
    id_empresa: int = ID_EMPRESA_DEFAULT,
    id_plataforma: int = 6,
) -> dict:
    """
    Envía un PDF por WhatsApp usando ws_send_whatsapp_oficial.php.

    Args:
        phone: Número destino (con código país, ej: 51999999998)
        document_url: URL pública del PDF
        filename: Nombre del archivo (requerido por la API)
        caption: Mensaje opcional que acompaña al documento
        id_empresa: ID de empresa para credenciales WhatsApp

    Returns:
        Respuesta JSON de la API
    """
    payload = {
        "id_empresa": id_empresa,
        "id_plataforma": id_plataforma,
        "phone": phone,
        "type": "document",
        "document_url": document_url,
        "filename": filename,
    }
    if caption:
        payload["message"] = caption

    headers = {"Content-Type": "application/json"}
    res = requests.post(URL_WHATSAPP, json=payload, headers=headers, timeout=30)
    return {"status_code": res.status_code, "response": res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text}


def run():
    phone = sys.argv[1] if len(sys.argv) > 1 else PHONE_DEFAULT
    id_empresa = int(sys.argv[2]) if len(sys.argv) > 2 else ID_EMPRESA_DEFAULT

    print("--- Enviar PDF por WhatsApp ---")
    print(f"URL: {URL_WHATSAPP}")
    print(f"Phone: {phone}")
    print(f"id_empresa: {id_empresa}")
    print(f"id_plataforma: 6")
    print(f"document_url: {PDF_URL}")
    print(f"filename: {PDF_FILENAME}")
    print()

    try:
        result = enviar_pdf_whatsapp(
            phone=phone,
            document_url=PDF_URL,
            filename=PDF_FILENAME,
            caption="Tu comprobante de pago electrónico.",
            id_empresa=id_empresa,
        )
    except requests.RequestException as e:
        print(f"❌ Error de conexión: {e}")
        return

    print("--- RESPUESTA ---")
    print(f"HTTP {result['status_code']}")
    if isinstance(result["response"], dict):
        print(json.dumps(result["response"], indent=2, ensure_ascii=False))
        if result["response"].get("success"):
            print("\n✅ PDF enviado correctamente por WhatsApp")
        else:
            err = result["response"].get("error") or result["response"].get("details")
            print(f"\n❌ Error: {err}")
    else:
        print(result["response"])


if __name__ == "__main__":
    run()
