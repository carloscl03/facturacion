"""
Test análogo para proveedores: flujo idempotente "obtener o crear" contra ws_proveedor.php.

API objetivo:
  - URL: https://api.maravia.pe/servicio/n8n_asistente/ws_proveedor.php
  - BUSCAR: codOpe=BUSCAR_PROVEEDOR (POST)
  - REGISTRAR: codOpe=REGISTRAR_PROVEEDOR_SIMPLE (POST)

Uso:
  python test/test_proveedor_obtener_o_crear.py
  python test/test_proveedor_obtener_o_crear.py natural
  python test/test_proveedor_obtener_o_crear.py juridica
  python test/test_proveedor_obtener_o_crear.py confirmar
  python test/test_proveedor_obtener_o_crear.py crear_confirmar

Notas:
  - El flujo busca por documento (DNI/RUC) y crea solo si no existe.
  - Respuesta normalizada: {success, proveedor_id, created, message}.

Configuración fija confirmada en este entorno (mar-2026):
  - id_empresa = 2
  - id_tipo_documento DNI = 1
  - id_tipo_documento RUC = 4
  - id_tipo_documento RUC (fallback) = [4]
  - idempotencia validada: segunda llamada mantiene proveedor_id y created=false.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

import requests

from config import settings

URL_PROVEEDOR = settings.URL_PROVEEDOR

# Configuración final del test (fija y validada por ejecución real).
# Objetivo: script determinista sin depender de parámetros externos para datos base.
EMPRESA_ID_DEFAULT = 2
ID_TIPO_DOC_DNI = 1
ID_TIPO_DOC_RUC = 4
# Confirmado en proveedor para empresa_id=2.
ID_TIPO_DOC_RUC_CANDIDATOS = [4]
VALIDAR_RUC_LOCAL = True

DNI_PRUEBA = "85274196"
RUC_PRUEBA = "20601234565"


def _headers() -> dict[str, str]:
    # Header fijo del endpoint. Authorization queda opcional solo para compatibilidad,
    # aunque este ws_proveedor.php no lo exige según contrato actual.
    h = {"Content-Type": "application/json"}
    token = os.environ.get("MARAVIA_TOKEN", "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def validar_digito_verificador_ruc(ruc: str) -> bool:
    s = (ruc or "").strip()
    if len(s) != 11 or not s.isdigit():
        return False
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(s[i]) * pesos[i] for i in range(10))
    resto = total % 11
    dv = 11 - resto
    if dv == 10:
        dv = 0
    elif dv == 11:
        dv = 1
    return int(s[10]) == dv


def generar_ruc_valido(prefijo10: str) -> str:
    s = "".join(c for c in str(prefijo10) if c.isdigit())[:10].ljust(10, "0")
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(s[i]) * pesos[i] for i in range(10))
    resto = total % 11
    dv = 11 - resto
    if dv == 10:
        dv = 0
    elif dv == 11:
        dv = 1
    return s + str(dv)


def _mensaje_error_api(data: dict[str, Any]) -> str:
    parts = [data.get("message"), data.get("error"), data.get("details"), data.get("mensaje")]
    if isinstance(data.get("data"), dict):
        d = data["data"]
        parts.extend([d.get("message"), d.get("error")])
    out = " | ".join(str(p) for p in parts if p is not None and str(p).strip())
    return out or "Error desconocido (sin mensaje en JSON)"


def _extraer_proveedor_id(resp: dict[str, Any]) -> int | None:
    if resp.get("proveedor_id") is not None:
        try:
            return int(resp["proveedor_id"])
        except (TypeError, ValueError):
            pass
    data = resp.get("data") or {}
    for k in ("proveedor_id", "id"):
        if data.get(k) is not None:
            try:
                return int(data[k])
            except (TypeError, ValueError):
                pass
    return None


def buscar_proveedor(empresa_id: int, termino: str) -> dict[str, Any]:
    payload = {
        "codOpe": "BUSCAR_PROVEEDOR",
        "id_empresa": empresa_id,
        "nombre_completo": (termino or "").strip(),
    }
    r = requests.post(URL_PROVEEDOR, json=payload, headers=_headers(), timeout=30)
    try:
        return r.json()
    except ValueError:
        return {"found": False, "message": r.text[:300], "http_status": r.status_code}


def registrar_proveedor(empresa_id: int, payload_sin_codope: dict[str, Any]) -> dict[str, Any]:
    body = {"codOpe": "REGISTRAR_PROVEEDOR_SIMPLE", "id_empresa": empresa_id, **payload_sin_codope}
    r = requests.post(URL_PROVEEDOR, json=body, headers=_headers(), timeout=30)
    try:
        data = r.json()
    except ValueError:
        return {"success": False, "message": r.text[:300] if r.text else f"HTTP {r.status_code}"}
    if r.status_code >= 400:
        data.setdefault("success", False)
    return data


def registrar_proveedor_con_fallback(empresa_id: int, payload_base: dict[str, Any], *, es_juridica: bool) -> dict[str, Any]:
    # Fallback mínimo: solo reintenta con los IDs confirmados para RUC.
    intento = registrar_proveedor(empresa_id, payload_base)
    if intento.get("success") or not es_juridica:
        return intento
    msg = _mensaje_error_api(intento).lower()
    if "id_tipo_documento" not in msg and "tipodocumentoempresa" not in msg and "fkey" not in msg:
        return intento

    for cand in ID_TIPO_DOC_RUC_CANDIDATOS:
        payload_try = {**payload_base, "id_tipo_documento": cand}
        out = registrar_proveedor(empresa_id, payload_try)
        if out.get("success"):
            out["id_tipo_documento_usado"] = cand
            return out
    return intento


def obtener_o_crear_proveedor(
    empresa_id: int,
    id_tipo_persona: int,
    *,
    nombre: str | None = None,
    id_tipo_documento: int | None = None,
    numero_documento: str | None = None,
    razon_social: str | None = None,
    ruc: str | None = None,
    nombre_comercial: str | None = None,
) -> dict[str, Any]:
    if id_tipo_persona == 1:
        termino = (numero_documento or "").strip()
        if not termino or not nombre or id_tipo_documento is None:
            return {"success": False, "proveedor_id": None, "created": False, "message": "Natural: requiere nombre, id_tipo_documento y numero_documento"}
        reg_payload = {
            "tipo_persona": 1,
            "nombres": nombre.strip(),
            "apellido_paterno": ".",
            "id_tipo_documento": int(id_tipo_documento),
            "numero_documento": termino,
        }
    elif id_tipo_persona == 2:
        termino = (ruc or "").strip()
        if not termino or not (razon_social or "").strip():
            return {"success": False, "proveedor_id": None, "created": False, "message": "Jurídica: requiere razon_social y ruc"}
        if VALIDAR_RUC_LOCAL and not validar_digito_verificador_ruc(termino):
            return {"success": False, "proveedor_id": None, "created": False, "message": f"RUC inválido: {termino}"}
        reg_payload = {
            "tipo_persona": 2,
            "razon_social": razon_social.strip(),
            "id_tipo_documento": ID_TIPO_DOC_RUC,
            "ruc": termino,
        }
    else:
        return {"success": False, "proveedor_id": None, "created": False, "message": "id_tipo_persona debe ser 1 o 2"}

    if nombre_comercial:
        reg_payload["nombre_comercial"] = nombre_comercial.strip()

    found = buscar_proveedor(empresa_id, termino)
    if found.get("found"):
        pid = _extraer_proveedor_id(found)
        if pid is not None:
            return {"success": True, "proveedor_id": pid, "created": False, "message": "Proveedor encontrado por documento (ya existía)"}

    reg = registrar_proveedor_con_fallback(empresa_id, reg_payload, es_juridica=(id_tipo_persona == 2))
    if not reg.get("success"):
        return {"success": False, "proveedor_id": None, "created": False, "message": _mensaje_error_api(reg)}

    pid = _extraer_proveedor_id(reg)
    return {"success": True, "proveedor_id": pid, "created": True, "message": str(reg.get("message") or "Proveedor creado")}


def _demo_natural(empresa_id: int) -> None:
    out = obtener_o_crear_proveedor(
        empresa_id,
        1,
        nombre="Proveedor Demo",
        id_tipo_documento=ID_TIPO_DOC_DNI,
        numero_documento=DNI_PRUEBA,
    )
    print("--- Proveedor natural (DNI) ---")
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _demo_juridica(empresa_id: int) -> None:
    out = obtener_o_crear_proveedor(
        empresa_id,
        2,
        razon_social="PROVEEDOR DEMO SAC",
        ruc=RUC_PRUEBA,
    )
    print("--- Proveedor jurídica (RUC) ---")
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _confirmar_idempotencia(empresa_id: int) -> None:
    n1 = obtener_o_crear_proveedor(empresa_id, 1, nombre="Proveedor Demo", id_tipo_documento=ID_TIPO_DOC_DNI, numero_documento=DNI_PRUEBA)
    n2 = obtener_o_crear_proveedor(empresa_id, 1, nombre="Proveedor Demo", id_tipo_documento=ID_TIPO_DOC_DNI, numero_documento=DNI_PRUEBA)
    j1 = obtener_o_crear_proveedor(empresa_id, 2, razon_social="PROVEEDOR DEMO SAC", ruc=RUC_PRUEBA)
    j2 = obtener_o_crear_proveedor(empresa_id, 2, razon_social="PROVEEDOR DEMO SAC", ruc=RUC_PRUEBA)

    def chk(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        ok = bool(a.get("success")) and bool(b.get("success")) and a.get("proveedor_id") == b.get("proveedor_id") and b.get("created") is False
        return {"ok_total": ok, "primera": a, "segunda": b}

    out = {"natural": chk(n1, n2), "juridica": chk(j1, j2)}
    out["ok_global"] = bool(out["natural"]["ok_total"] and out["juridica"]["ok_total"])
    print("--- Confirmación automática ---")
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _crear_y_confirmar_registro_nuevo(empresa_id: int) -> None:
    # Genera documento nuevo para forzar alta (created=true) y luego verifica found=true.
    stamp = str(int(time.time()))
    dni_nuevo = ("8" + stamp[-7:])[-8:]
    ruc_nuevo = generar_ruc_valido("2098" + stamp[-6:])
    nombre_nat = f"Proveedor Demo {stamp}"
    razon_soc = f"PROVEEDOR DEMO {stamp} SAC"

    nat = obtener_o_crear_proveedor(empresa_id, 1, nombre=nombre_nat, id_tipo_documento=ID_TIPO_DOC_DNI, numero_documento=dni_nuevo)
    nat_b = buscar_proveedor(empresa_id, dni_nuevo)
    jur = obtener_o_crear_proveedor(empresa_id, 2, razon_social=razon_soc, ruc=ruc_nuevo)
    jur_b = buscar_proveedor(empresa_id, ruc_nuevo)

    nat_ok = bool(nat.get("success")) and nat.get("proveedor_id") is not None and bool(nat_b.get("found"))
    jur_ok = bool(jur.get("success")) and jur.get("proveedor_id") is not None and bool(jur_b.get("found"))
    out = {
        "input": {"dni_nuevo": dni_nuevo, "ruc_nuevo": ruc_nuevo, "razon_social": razon_soc},
        "natural": {"crear": nat, "buscar": nat_b, "ok": nat_ok},
        "juridica": {"crear": jur, "buscar": jur_b, "ok": jur_ok},
        "ok_global": bool(nat_ok and jur_ok),
    }
    print("--- Crear y confirmar registro nuevo ---")
    print(json.dumps(out, indent=2, ensure_ascii=False))


def run() -> None:
    empresa_id = EMPRESA_ID_DEFAULT
    modo = (sys.argv[1] if len(sys.argv) > 1 else "ambos").lower()
    print("URL:", URL_PROVEEDOR)
    print("empresa_id:", empresa_id)
    print()

    if modo in ("natural", "nat", "1"):
        _demo_natural(empresa_id)
    elif modo in ("juridica", "jur", "2", "ruc"):
        _demo_juridica(empresa_id)
    elif modo in ("confirmar", "check", "ok"):
        _confirmar_idempotencia(empresa_id)
    elif modo in ("crear_confirmar", "crear", "nuevo"):
        _crear_y_confirmar_registro_nuevo(empresa_id)
    else:
        _demo_natural(empresa_id)
        print()
        _demo_juridica(empresa_id)


if __name__ == "__main__":
    run()

