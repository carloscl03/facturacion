"""
Prueba directa del flujo "obtener o registrar" contra ws_proveedor.php.

Pasos:
  1. BUSCAR_PROVEEDOR por documento (DNI/RUC)
  2. Si no existe → REGISTRAR_PROVEEDOR_SIMPLE
  3. Imprime el proveedor_id resultante

Campos confirmados en PHP (mar-2026):
  - Natural  (tipo_persona=1): nombres, apellido_paterno, id_tipo_documento, numero_documento
  - Jurídica (tipo_persona=2): razon_social, id_tipo_documento (6→4 fallback), ruc

Uso:
  python test/test_proveedor_obtener_o_registrar.py
  python test/test_proveedor_obtener_o_registrar.py natural
  python test/test_proveedor_obtener_o_registrar.py juridica
"""
from __future__ import annotations

import json
import os
import sys

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

import requests

URL = "https://api.maravia.pe/servicio/n8n_asistente/ws_proveedor.php"
EMPRESA_ID = 2

# id_tipo_documento para DNI y RUC (orden de intento para RUC = [6, 4])
ID_TIPO_DNI = 1
ID_TIPO_RUC_CANDIDATOS = [6, 4]

# Datos de prueba
DNI_PRUEBA = "85274196"
NOMBRE_PRUEBA = "Proveedor Demo Natural"

RUC_PRUEBA = "20992823055"
RAZON_SOCIAL_PRUEBA = "PROVEEDOR DEMO SAC"


def _post(payload: dict) -> dict:
    print("  >> PAYLOAD:", json.dumps(payload, ensure_ascii=False))
    r = requests.post(URL, json=payload, timeout=30)
    try:
        data = r.json()
    except ValueError:
        data = {"success": False, "raw": r.text[:300], "http_status": r.status_code}
    print("  << RESPUESTA:", json.dumps(data, ensure_ascii=False))
    return data


def buscar(termino: str) -> dict:
    print(f"\n[BUSCAR] termino={termino!r}")
    return _post({
        "codOpe": "BUSCAR_PROVEEDOR",
        "id_empresa": EMPRESA_ID,
        "nombre_completo": termino,
    })


def registrar(payload_extra: dict) -> dict:
    payload = {
        "codOpe": "REGISTRAR_PROVEEDOR_SIMPLE",
        "id_empresa": EMPRESA_ID,
        **payload_extra,
    }
    print("\n[REGISTRAR]")
    return _post(payload)


def registrar_con_fallback_ruc(payload_base: dict) -> dict:
    """Intenta id_tipo_documento = 6 primero, luego 4, para RUC."""
    ultimo = {"success": False, "message": "Sin intentos"}
    for cand in ID_TIPO_RUC_CANDIDATOS:
        payload = {**payload_base, "id_tipo_documento": cand}
        data = registrar(payload)
        if data.get("success"):
            data["id_tipo_documento_usado"] = cand
            return data
        # Solo continúa si el error parece ser de FK en tipo_documento
        msg = (
            str(data.get("message") or "") +
            str(data.get("error") or "") +
            str(data.get("details") or "")
        ).lower()
        fk_tipo = any(k in msg for k in ("id_tipo_documento", "tipodocumentoempresa", "fkey", "foreign key"))
        ultimo = data
        if not fk_tipo:
            break
    return ultimo


def obtener_o_registrar_natural(numero_documento: str, nombre: str) -> dict:
    print(f"\n{'='*50}")
    print(f"NATURAL | DNI={numero_documento} | nombre={nombre!r}")
    print(f"{'='*50}")

    encontrado = buscar(numero_documento)
    if encontrado.get("found"):
        pid = encontrado.get("proveedor_id")
        print(f"\n[OK] Proveedor ya existe → proveedor_id={pid}")
        return {"proveedor_id": pid, "created": False}

    print("\n[INFO] No encontrado. Registrando...")
    resultado = registrar({
        "tipo_persona": 1,
        "nombres": nombre,
        "apellido_paterno": ".",
        "id_tipo_documento": ID_TIPO_DNI,
        "numero_documento": numero_documento,
    })
    pid = resultado.get("proveedor_id")
    if resultado.get("success"):
        print(f"\n[OK] Proveedor creado → proveedor_id={pid}")
        return {"proveedor_id": pid, "created": True}
    else:
        print(f"\n[ERROR] No se pudo crear: {resultado}")
        return {"proveedor_id": None, "created": False, "error": resultado}


def obtener_o_registrar_juridica(ruc: str, razon_social: str) -> dict:
    print(f"\n{'='*50}")
    print(f"JURIDICA | RUC={ruc} | razon_social={razon_social!r}")
    print(f"{'='*50}")

    encontrado = buscar(ruc)
    if encontrado.get("found"):
        pid = encontrado.get("proveedor_id")
        print(f"\n[OK] Proveedor ya existe → proveedor_id={pid}")
        return {"proveedor_id": pid, "created": False}

    print("\n[INFO] No encontrado. Registrando (intentando id_tipo_documento 6 → 4)...")
    resultado = registrar_con_fallback_ruc({
        "tipo_persona": 2,
        "razon_social": razon_social,
        "ruc": ruc,
    })
    pid = resultado.get("proveedor_id")
    if resultado.get("success"):
        print(f"\n[OK] Proveedor creado → proveedor_id={pid} (id_tipo_doc={resultado.get('id_tipo_documento_usado')})")
        return {"proveedor_id": pid, "created": True}
    else:
        print(f"\n[ERROR] No se pudo crear: {resultado}")
        return {"proveedor_id": None, "created": False, "error": resultado}


def run() -> None:
    modo = (sys.argv[1] if len(sys.argv) > 1 else "ambos").lower()

    if modo in ("natural", "nat", "dni", "1"):
        obtener_o_registrar_natural(DNI_PRUEBA, NOMBRE_PRUEBA)
    elif modo in ("juridica", "jur", "ruc", "2"):
        obtener_o_registrar_juridica(RUC_PRUEBA, RAZON_SOCIAL_PRUEBA)
    else:
        obtener_o_registrar_natural(DNI_PRUEBA, NOMBRE_PRUEBA)
        obtener_o_registrar_juridica(RUC_PRUEBA, RAZON_SOCIAL_PRUEBA)


if __name__ == "__main__":
    run()
