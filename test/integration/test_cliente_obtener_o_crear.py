"""
Test: flujo idempotente «obtener o crear» cliente (ws_cliente.php).

Contrato deseado (cuando exista en backend):
  OBTENER_O_CREAR_CLIENTE — busca por documento/RUC; si no existe, crea.
  Persona natural (id_tipo_persona=1): nombre, id_tipo_documento, numero_documento
  Persona jurídica (id_tipo_persona=2): razon_social, ruc
  Opcional: nombre_comercial
  Respuesta esperada: { success, cliente_id, created, message }

Implementación actual: la API pública no expone aún ese codOpe en el repo; el script
implementa el mismo comportamiento con:
  - GET  BUSCAR_CLIENTE  (codOpe, empresa_id, termino) — como test_cliente.py
  - POST REGISTRAR_CLIENTE (mismo contrato que repositories/entity_repository)

Si MARAVIA_USAR_OBTENER_O_CREAR_API=1, intenta primero POST con codOpe=OBTENER_O_CREAR_CLIENTE;
si falla, hace fallback al flujo anterior.

Uso:
  python test/test_cliente_obtener_o_crear.py
  python test/test_cliente_obtener_o_crear.py natural
  python test/test_cliente_obtener_o_crear.py juridica
  python test/test_cliente_obtener_o_crear.py confirmar
  python test/test_cliente_obtener_o_crear.py crear_confirmar

Valores fijados para este entorno (confirmados):
  - empresa_id = 2
  - id_tipo_documento RUC = 4
  - DNI demo = 44556677
  - RUC demo = 20123456786

Resumen de validación real (mar-2026):
  - Persona natural (DNI + nombre): OK (crea y luego encuentra por documento).
  - Persona jurídica (RUC + razón social): OK (crea y luego encuentra por documento).
  - idempotencia: OK (segunda llamada devuelve created=false y mismo cliente_id).
  - Nota importante de catálogo: en empresa_id=2 el id_tipo_documento para RUC es 4.
    El backend devuelve tipo_documento_nombre="PAS", pero aun así ese id funciona para
    registrar y buscar por RUC en esta empresa.
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

URL_CLIENTE = settings.URL_CLIENTE

# Configuración final del test (confirmada por ejecución real en este entorno).
# No usar variables de entorno para estos campos: el objetivo del test es ser determinista.
ID_TIPO_DOC_DNI = 1
ID_TIPO_DOC_RUC = 4

EMPRESA_ID_DEFAULT = 2
# Confirmado: para empresa_id=2, RUC usa id_tipo_documento=4.
ID_TIPO_DOC_RUC_CANDIDATOS = [4]
USAR_OBTENER_O_CREAR_API = False
VALIDAR_RUC_LOCAL = True
DNI_PRUEBA = "44556677"
RUC_PRUEBA = "20123456786"
NOMBRE_COMERCIAL_DEMO = None

# Datos de ejemplo para creación explícita (modo crear_confirmar).
# Se construyen nombres con timestamp para evitar colisiones y permitir validar created=true.


def validar_digito_verificador_ruc(ruc: str) -> bool:
    """
    RUC Perú 11 dígitos (persona jurídica 20…): módulo 11 con pesos SUNAT.
    El RUC de demo anterior 20123456781 era inválido (DV correcto = 6 → 20123456786).
    """
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


def generar_ruc_valido(prefijo10: str = "2099999999") -> str:
    """
    Genera un RUC válido de 11 dígitos a partir de los primeros 10.
    Para pruebas usa un prefijo no productivo.
    """
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
    """Une message + error + details para diagnosticar REGISTRAR_CLIENTE."""
    parts = [
        data.get("message"),
        data.get("error"),
        data.get("details"),
        data.get("mensaje"),
    ]
    if isinstance(data.get("data"), dict):
        d = data["data"]
        parts.extend([d.get("message"), d.get("error")])
    out = " | ".join(str(p) for p in parts if p is not None and str(p).strip())
    return out or "Error desconocido (sin mensaje en JSON)"


def _extraer_candidatos_id_tipo_doc_ruc() -> list[int]:
    """
    Candidatos para id_tipo_documento de RUC en esta empresa.
    Fijado a [4] porque ya fue confirmado en pruebas.
    """
    return ID_TIPO_DOC_RUC_CANDIDATOS


def _es_error_fk_tipo_documento(msg: str) -> bool:
    m = (msg or "").lower()
    return "persona_id_tipo_documento_fkey" in m or "tipodocumentoempresa" in m


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    token = os.environ.get("MARAVIA_TOKEN", "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _extraer_cliente_id(resp: dict[str, Any]) -> int | None:
    if resp.get("cliente_id") is not None:
        try:
            return int(resp["cliente_id"])
        except (TypeError, ValueError):
            pass
    data = resp.get("data") or {}
    for k in ("cliente_id", "id"):
        if data.get(k) is not None:
            try:
                return int(data[k])
            except (TypeError, ValueError):
                pass
    return None


def buscar_cliente(empresa_id: int, termino: str) -> dict[str, Any]:
    """GET ws_cliente.php — mismo patrón que test/test_cliente.py."""
    r = requests.get(
        URL_CLIENTE,
        params={
            "codOpe": "BUSCAR_CLIENTE",
            "empresa_id": empresa_id,
            "termino": (termino or "").strip(),
        },
        timeout=30,
    )
    try:
        return r.json()
    except ValueError:
        return {"found": False, "message": r.text[:300], "http_status": r.status_code}


def registrar_cliente(empresa_id: int, payload_sin_codope: dict[str, Any]) -> dict[str, Any]:
    body = {"codOpe": "REGISTRAR_CLIENTE", "empresa_id": empresa_id, **payload_sin_codope}
    r = requests.post(URL_CLIENTE, json=body, headers=_headers(), timeout=30)
    try:
        data = r.json()
    except ValueError:
        return {"success": False, "message": r.text[:300] if r.text else f"HTTP {r.status_code}"}
    if r.status_code >= 400:
        data.setdefault("success", False)
    return data


def registrar_cliente_con_fallback(
    empresa_id: int,
    payload_base: dict[str, Any],
    *,
    es_juridica: bool,
) -> dict[str, Any]:
    """
    Registra cliente con fallback mínimo.
    En este entorno el único candidato válido confirmado es 4; se mantiene el patrón de reintento
    solo para robustez del flujo y para preservar el diagnóstico en caso de cambio futuro.
    1) Intenta payload_base.
    2) Si jurídica y falla por id_tipo_documento, reintenta con candidatos.
    """
    intento = registrar_cliente(empresa_id, payload_base)
    if intento.get("success"):
        return intento
    if not es_juridica:
        return intento

    msg = _mensaje_error_api(intento) if isinstance(intento, dict) else str(intento)
    m = (msg or "").lower()
    if not (_es_error_fk_tipo_documento(msg) or "campo requerido: id_tipo_documento" in m):
        return intento

    candidatos = _extraer_candidatos_id_tipo_doc_ruc()
    for cand in candidatos:
        payload_try = {**payload_base, "id_tipo_documento": cand}
        intento_n = registrar_cliente(empresa_id, payload_try)
        if intento_n.get("success"):
            intento_n["id_tipo_documento_usado"] = cand
            return intento_n
        msg_n = _mensaje_error_api(intento_n) if isinstance(intento_n, dict) else str(intento_n)
        # Si ya dejó de ser error de id_tipo_documento, devolvemos ese para no ocultar otra validación real.
        mn = (msg_n or "").lower()
        if not (_es_error_fk_tipo_documento(msg_n) or "campo requerido: id_tipo_documento" in mn):
            return intento_n

    intento["message"] = (
        f"{msg} | No se encontró id_tipo_documento válido para RUC. "
        f"Candidatos probados: {candidatos}. "
        "Define MARAVIA_ID_TIPO_DOC_RUC_CANDIDATOS con los IDs reales de tipodocumentoempresa para esta empresa."
    )
    return intento


def intentar_obtener_o_crear_api(empresa_id: int, body: dict[str, Any]) -> dict[str, Any] | None:
    """POST codOpe=OBTENER_O_CREAR_CLIENTE si el backend lo soporta."""
    payload = {"codOpe": "OBTENER_O_CREAR_CLIENTE", "empresa_id": empresa_id, **body}
    r = requests.post(URL_CLIENTE, json=payload, headers=_headers(), timeout=30)
    try:
        data = r.json()
    except ValueError:
        return None
    # Operación desconocida / error de enrutamiento
    err = (data.get("error") or data.get("message") or "").lower()
    if r.status_code == 400 and ("operación" in err or "operacion" in err or "no válid" in err or "invalid" in err):
        return None
    return data


def obtener_o_crear_cliente(
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
    """
    Idempotente: BUSCAR por documento/RUC; si no hay coincidencia, REGISTRAR_CLIENTE.

    id_tipo_persona: 1 = natural, 2 = jurídica (en POST se envía como tipo_persona, convención ws_cliente).
    Retorno unificado: { success, cliente_id, created, message }.
    """
    usar_api = USAR_OBTENER_O_CREAR_API

    if id_tipo_persona == 1:
        termino = (numero_documento or "").strip()
        if not termino or not nombre or id_tipo_documento is None:
            return {
                "success": False,
                "cliente_id": None,
                "created": False,
                "message": "Persona natural: requiere nombre, id_tipo_documento y numero_documento",
            }
        api_body = {
            "id_tipo_persona": 1,
            "nombre": nombre.strip(),
            "id_tipo_documento": id_tipo_documento,
            "numero_documento": termino,
        }
        reg_payload = {
            "tipo_persona": 1,
            "nombres": nombre.strip(),
            "apellido_paterno": ".",
            "id_tipo_documento": id_tipo_documento,
            "numero_documento": termino,
        }
    elif id_tipo_persona == 2:
        termino = (ruc or "").strip()
        if not termino or not (razon_social or "").strip():
            return {
                "success": False,
                "cliente_id": None,
                "created": False,
                "message": "Persona jurídica: requiere razon_social y ruc",
            }
        if VALIDAR_RUC_LOCAL:
            if not validar_digito_verificador_ruc(termino):
                return {
                    "success": False,
                    "cliente_id": None,
                    "created": False,
                    "message": (
                        f"RUC con dígito verificador inválido: {termino}. "
                        "Usa un RUC de 11 dígitos válido (SUNAT)."
                    ),
                }
        api_body = {
            "id_tipo_persona": 2,
            "razon_social": razon_social.strip(),
            "ruc": termino,
        }
        id_tipo_doc_ruc = ID_TIPO_DOC_RUC
        reg_payload = {
            "tipo_persona": 2,
            "razon_social": razon_social.strip(),
            "id_tipo_documento": id_tipo_doc_ruc,
            "ruc": termino,
        }
    else:
        return {
            "success": False,
            "cliente_id": None,
            "created": False,
            "message": "id_tipo_persona debe ser 1 (natural) o 2 (jurídica)",
        }

    if nombre_comercial:
        api_body["nombre_comercial"] = nombre_comercial.strip()
        reg_payload["nombre_comercial"] = nombre_comercial.strip()

    if usar_api:
        raw = intentar_obtener_o_crear_api(empresa_id, api_body)
        if raw is not None and raw.get("success"):
            cid = raw.get("cliente_id")
            if cid is None:
                cid = _extraer_cliente_id(raw)
            return {
                "success": True,
                "cliente_id": cid,
                "created": bool(raw.get("created", False)),
                "message": str(raw.get("message") or "OK (OBTENER_O_CREAR_CLIENTE)"),
            }

    found = buscar_cliente(empresa_id, termino)
    if found.get("found"):
        cid = _extraer_cliente_id(found)
        if cid is not None:
            return {
                "success": True,
                "cliente_id": cid,
                "created": False,
                "message": "Cliente encontrado por documento (ya existía)",
            }

    reg = registrar_cliente_con_fallback(
        empresa_id,
        reg_payload,
        es_juridica=(id_tipo_persona == 2),
    )
    if not reg.get("success"):
        msg = _mensaje_error_api(reg) if isinstance(reg, dict) else str(reg)
        return {"success": False, "cliente_id": None, "created": False, "message": msg}

    cid = _extraer_cliente_id(reg)
    if cid is None:
        cid = reg.get("cliente_id")
    return {
        "success": True,
        "cliente_id": cid,
        "created": True,
        "message": str(reg.get("message") or "Cliente creado"),
    }


def _demo_natural(empresa_id: int) -> None:
    # DNI de prueba: cambiar si en tu BD ya existe otro uso
    dni = DNI_PRUEBA
    out = obtener_o_crear_cliente(
        empresa_id,
        1,
        nombre="Cliente Prueba Obtener OC",
        id_tipo_documento=ID_TIPO_DOC_DNI,
        numero_documento=dni,
        nombre_comercial=NOMBRE_COMERCIAL_DEMO,
    )
    print("--- Persona natural (DNI) ---")
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _demo_juridica(empresa_id: int) -> None:
    # DV válido (6), no el 20123456781 que fallaba validación SUNAT / BD
    ruc = RUC_PRUEBA
    out = obtener_o_crear_cliente(
        empresa_id,
        2,
        razon_social="EMPRESA PRUEBA OBTENER OC SAC",
        ruc=ruc,
        nombre_comercial=NOMBRE_COMERCIAL_DEMO,
    )
    print("--- Persona jurídica (RUC) ---")
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _confirmar_idempotencia(empresa_id: int) -> None:
    """
    Confirmación rápida del flujo:
    - Natural y jurídica responden success=true.
    - Segunda llamada mantiene el mismo cliente_id y created=false.
    - Este modo no fuerza altas nuevas; valida consistencia sobre registros existentes.
    """
    print("--- Confirmación automática ---")
    print(
        json.dumps(
            {
                "empresa_id": empresa_id,
                "id_tipo_doc_dni": ID_TIPO_DOC_DNI,
                "id_tipo_doc_ruc": ID_TIPO_DOC_RUC,
                "dni_prueba": DNI_PRUEBA,
                "ruc_prueba": RUC_PRUEBA,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    nat_1 = obtener_o_crear_cliente(
        empresa_id,
        1,
        nombre="Cliente Prueba Obtener OC",
        id_tipo_documento=ID_TIPO_DOC_DNI,
        numero_documento=DNI_PRUEBA,
        nombre_comercial=NOMBRE_COMERCIAL_DEMO,
    )
    nat_2 = obtener_o_crear_cliente(
        empresa_id,
        1,
        nombre="Cliente Prueba Obtener OC",
        id_tipo_documento=ID_TIPO_DOC_DNI,
        numero_documento=DNI_PRUEBA,
        nombre_comercial=NOMBRE_COMERCIAL_DEMO,
    )
    jur_1 = obtener_o_crear_cliente(
        empresa_id,
        2,
        razon_social="EMPRESA PRUEBA OBTENER OC SAC",
        ruc=RUC_PRUEBA,
        nombre_comercial=NOMBRE_COMERCIAL_DEMO,
    )
    jur_2 = obtener_o_crear_cliente(
        empresa_id,
        2,
        razon_social="EMPRESA PRUEBA OBTENER OC SAC",
        ruc=RUC_PRUEBA,
        nombre_comercial=NOMBRE_COMERCIAL_DEMO,
    )

    def check_pair(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        ok_success = bool(a.get("success")) and bool(b.get("success"))
        same_id = a.get("cliente_id") is not None and a.get("cliente_id") == b.get("cliente_id")
        second_not_created = b.get("created") is False
        return {
            "ok_success_ambas": ok_success,
            "cliente_id_estable": same_id,
            "segunda_llamada_created_false": second_not_created,
            "ok_total": ok_success and same_id and second_not_created,
            "primera": a,
            "segunda": b,
        }

    resultado = {
        "natural": check_pair(nat_1, nat_2),
        "juridica": check_pair(jur_1, jur_2),
    }
    resultado["ok_global"] = bool(resultado["natural"]["ok_total"] and resultado["juridica"]["ok_total"])

    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    if not resultado["ok_global"]:
        print(
            "\n⚠ Hay algo por revisar. Verifica mensaje/error en primera/segunda llamada para natural y jurídica."
        )


def _crear_y_confirmar_registro_nuevo(empresa_id: int) -> None:
    """
    Crea nuevos registros (natural y jurídica) y confirma por BUSCAR_CLIENTE que quedaron persistidos.
    Criterio de éxito:
    - crear.success = true y cliente_id no nulo
    - buscar.found = true y cliente_id de búsqueda == cliente_id de creación
    """
    stamp = str(int(time.time()))
    dni_nuevo = ("8" + stamp[-7:])[-8:]
    ruc_nuevo = generar_ruc_valido("2099" + stamp[-6:])

    nombre_natural = f"Cliente Demo {stamp}"
    razon_social = f"EMPRESA DEMO {stamp} SAC"

    print("--- Crear y confirmar registro nuevo ---")
    print(
        json.dumps(
            {
                "empresa_id": empresa_id,
                "dni_nuevo": dni_nuevo,
                "nombre_natural": nombre_natural,
                "ruc_nuevo": ruc_nuevo,
                "razon_social": razon_social,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    # 1) Crear natural
    nat = obtener_o_crear_cliente(
        empresa_id,
        1,
        nombre=nombre_natural,
        id_tipo_documento=ID_TIPO_DOC_DNI,
        numero_documento=dni_nuevo,
        nombre_comercial=NOMBRE_COMERCIAL_DEMO,
    )
    nat_busqueda = buscar_cliente(empresa_id, dni_nuevo)

    # 2) Crear jurídica
    # En empresa_id=2 se usa id_tipo_documento=4 para este flujo de RUC (confirmado en pruebas).
    jur = obtener_o_crear_cliente(
        empresa_id,
        2,
        razon_social=razon_social,
        ruc=ruc_nuevo,
        nombre_comercial=NOMBRE_COMERCIAL_DEMO,
    )
    jur_busqueda = buscar_cliente(empresa_id, ruc_nuevo)

    def _ok_creacion(y: dict[str, Any]) -> bool:
        return bool(y.get("success")) and y.get("cliente_id") is not None

    def _ok_busqueda(y: dict[str, Any], cid: Any) -> bool:
        found = bool(y.get("found"))
        cid_b = _extraer_cliente_id(y)
        return found and cid_b is not None and str(cid_b) == str(cid)

    resultado = {
        "natural": {
            "crear": nat,
            "buscar": nat_busqueda,
            "ok_creacion": _ok_creacion(nat),
            "ok_busqueda_mismo_id": _ok_busqueda(nat_busqueda, nat.get("cliente_id")),
        },
        "juridica": {
            "crear": jur,
            "buscar": jur_busqueda,
            "ok_creacion": _ok_creacion(jur),
            "ok_busqueda_mismo_id": _ok_busqueda(jur_busqueda, jur.get("cliente_id")),
        },
    }
    resultado["ok_global"] = bool(
        resultado["natural"]["ok_creacion"]
        and resultado["natural"]["ok_busqueda_mismo_id"]
        and resultado["juridica"]["ok_creacion"]
        and resultado["juridica"]["ok_busqueda_mismo_id"]
    )

    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    if not resultado["ok_global"]:
        print("\n⚠ La confirmación no fue completa. Revisar payload/response de crear y buscar.")


def run() -> None:
    empresa_id = EMPRESA_ID_DEFAULT
    modo = (sys.argv[1] if len(sys.argv) > 1 else "ambos").lower()
    print("URL:", URL_CLIENTE)
    print("empresa_id:", empresa_id)
    print("usar OBTENER_O_CREAR_CLIENTE API:", USAR_OBTENER_O_CREAR_API)
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
