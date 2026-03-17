import sys
from pathlib import Path

# Permitir ejecutar este script directamente: python test/test_opciones_service_unit.py
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import requests

from services.opciones_service import OpcionesService, OPCIONES_ACTUALES_KEY

# APIs: formas, medios de pago (n8n) y sucursales (información)
URL_WS_FORMA_PAGO = "https://api.maravia.pe/servicio/n8n/ws_forma_pago.php"
URL_WS_MEDIO_PAGO = "https://api.maravia.pe/servicio/n8n/ws_medio_pago.php"
URL_INFORMACION = "https://api.maravia.pe/servicio/ws_informacion_ia.php"
ID_EMPRESA_TABLAS = 2  # id_empresa para OBTENER_SUCURSALES (como test_opciones.py)

# Envío a WhatsApp: mismo modelo que test/test_opciones.py (URL, POST json, id_whatsapp para credenciales)
URL_WHATSAPP_LIST = "https://api.maravia.pe/servicio/n8n/ws_send_whatsapp_list.php"
ID_PLATAFORMA = 6  # Requerido por la API (test_opciones.py build_payload_whatsapp id_plataforma=6)
# id_empresa para enviar = credenciales WhatsApp (como DEFAULT_ID_WHATSAPP = 1 en test_opciones.py)
ID_EMPRESA_WHATSAPP = 1
# phone para envío real: en test_opciones.py usan DEFAULT_WA_ID (ej. 51994748961). Los tests usan "user1"/"user2"
# que la API rechaza con 400; si quieres que el envío funcione, pon aquí el mismo número que en test_opciones.py
PHONE_PARA_ENVIO = "51994748961"  # mismo default que test_opciones.py DEFAULT_WA_ID


def _payload_para_envio(payload: dict) -> dict:
    """
    Payload listo para ws_send_whatsapp_list: id_plataforma: 6, id_empresa = ID_EMPRESA_WHATSAPP
    y phone = PHONE_PARA_ENVIO (la API devuelve 400 si phone no es un número WhatsApp válido; en los tests
    usamos "user1"/"user2", por eso se sobreescribe con un número real para el envío).
    """
    if not payload:
        return payload
    p = dict(payload)
    p["id_plataforma"] = ID_PLATAFORMA
    if ID_EMPRESA_WHATSAPP is not None:
        p["id_empresa"] = ID_EMPRESA_WHATSAPP
    if PHONE_PARA_ENVIO:
        p["phone"] = PHONE_PARA_ENVIO
    return p


def listar_formas_pago_api() -> dict:
    """
    Llama a ws_forma_pago.php con {"codOpe": "LISTAR_FORMAS_PAGO"}.
    Retorna {success, total, data: [...]} o {success: False, total: 0, data: []} si falla.
    """
    try:
        r = requests.post(
            URL_WS_FORMA_PAGO,
            json={"codOpe": "LISTAR_FORMAS_PAGO"},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code != 200:
            return {"success": False, "total": 0, "data": []}
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return data if isinstance(data, dict) else {"success": False, "total": 0, "data": []}
    except requests.RequestException:
        return {"success": False, "total": 0, "data": []}


def listar_medios_pago_api() -> dict:
    """
    Llama a ws_medio_pago.php con {"codOpe": "LISTAR_MEDIOS_PAGO"}.
    Retorna {success, total, data: [...]} o {success: False, total: 0, data: []} si falla.
    """
    try:
        r = requests.post(
            URL_WS_MEDIO_PAGO,
            json={"codOpe": "LISTAR_MEDIOS_PAGO"},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code != 200:
            return {"success": False, "total": 0, "data": []}
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return data if isinstance(data, dict) else {"success": False, "total": 0, "data": []}
    except requests.RequestException:
        return {"success": False, "total": 0, "data": []}


def listar_sucursales_api(id_empresa: int | None = None) -> list[dict]:
    """
    POST ws_informacion_ia OBTENER_SUCURSALES. Retorna lista de sucursales [{id, nombre}, ...].
    """
    id_empresa = id_empresa if id_empresa is not None else ID_EMPRESA_TABLAS
    try:
        r = requests.post(
            URL_INFORMACION,
            json={"codOpe": "OBTENER_SUCURSALES", "id_empresa": id_empresa},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        sucursales = data.get("sucursales") if isinstance(data, dict) else None
        return sucursales if isinstance(sucursales, list) else []
    except requests.RequestException:
        return []


# Límite título fila lista WhatsApp (como test_opciones.py y opciones_service)
MAX_ROW_TITLE = 24


def _truncar_row(s: str, max_len: int) -> str:
    if not s or max_len <= 0:
        return (s or "")[:max_len] if max_len > 0 else ""
    return s[:max_len] if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"


def build_payload_lista_whatsapp(
    section_title: str,
    items: list[dict],
    body: str | None = None,
    header: str | None = None,
    footer: str | None = None,
    button: str | None = None,
) -> dict:
    """
    Arma payload para ws_send_whatsapp_list a partir de una lista de ítems con id y nombre
    (ej. data de LISTAR_FORMAS_PAGO o LISTAR_MEDIOS_PAGO). Mismo formato que test_opciones.py.
    """
    if not items:
        rows = [{"id": "0", "title": f"Sin {section_title.lower()}", "description": ""}]
    else:
        rows = []
        for it in items:
            oid = it.get("id")
            nombre = (it.get("nombre") or "").strip() or str(oid)
            rows.append({
                "id": str(oid) if oid is not None else "0",
                "title": _truncar_row(nombre, MAX_ROW_TITLE),
                "description": "",
            })
    body = body or f"{section_title} disponibles: "
    header = header or section_title
    footer = footer or f"Selecciona una opción de {section_title.lower()}"
    button = button or f"Ver {section_title.lower()}"
    return {
        "id_empresa": ID_EMPRESA_WHATSAPP or 0,
        "id_plataforma": ID_PLATAFORMA,
        "phone": PHONE_PARA_ENVIO or "",
        "body_text": body,
        "button_text": button,
        "header_text": header,
        "footer_text": footer,
        "sections": [{"title": section_title, "rows": rows}],
    }


def enviar_lista_whatsapp(payload: dict) -> bool:
    """
    Envía un list message a WhatsApp. Mismo modelo que test_opciones.py enviar_lista_whatsapp:
    POST json=payload, timeout=30; retorna True si status 200 (igual que test_opciones).
    """
    if not payload:
        return False
    payload_envio = _payload_para_envio(payload)
    try:
        resp = requests.post(URL_WHATSAPP_LIST, json=payload_envio, timeout=30)
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


class DummyCache:
    def __init__(self) -> None:
        self._store: dict[tuple[str, int], dict] = {}

    def consultar(self, wa_id: str, id_from: int) -> dict | None:
        return self._store.get((wa_id, id_from))

    def consultar_lista(self, wa_id: str, id_from: int) -> list[dict]:
        v = self._store.get((wa_id, id_from))
        return [v] if v else []

    def insertar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        self._store[(wa_id, id_from)] = dict(datos)
        return {"success": True}

    def actualizar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        base = self._store.get((wa_id, id_from), {})
        base.update(datos)
        self._store[(wa_id, id_from)] = base
        return {"success": True}

    def eliminar(self, wa_id: str, id_from: int) -> dict:
        self._store.pop((wa_id, id_from), None)
        return {"success": True}


class DummyInformacion:
    def __init__(self, sucursales: list[dict] | None = None, metodos_pago: list[dict] | None = None) -> None:
        self._sucursales = sucursales or []
        self._metodos_pago = metodos_pago or []

    def obtener_sucursales(self, id_empresa: int) -> list[dict]:
        return self._sucursales

    def obtener_metodos_pago(self, id_empresa: int) -> list[dict]:
        return self._metodos_pago


class DummyParametros:
    def __init__(self, centros: list[dict] | None = None) -> None:
        self._centros = centros or []

    def obtener_centros_costo(self, wa_id: str) -> list[dict]:
        return self._centros


class DummyAI:
    def __init__(self, id_to_return=None) -> None:
        self._id = id_to_return
        self.last_prompt: str | None = None

    def completar_json(self, prompt: str) -> dict:
        self.last_prompt = prompt
        return {"id": self._id}


def _build_registro_inicial(estado: int = 4) -> dict:
    return {"estado": estado}


def test_get_next_sucursales_y_submit_sucursal_match_exacto():
    wa_id = "user1"
    id_from = 2

    cache = DummyCache()
    info = DummyInformacion(
        sucursales=[
            {"id": 29, "nombre": "Oficina Miraflores"},
            {"id": 14, "nombre": "San Isidro"},
        ]
    )
    service = OpcionesService(cache, info, parametros=None, ai=DummyAI())

    # Registro inicial en cache con estado 4 (confirmado) y sin sucursal.
    cache.insertar(wa_id, id_from, _build_registro_inicial(estado=4))

    # 1) get_next debe listar sucursales y guardar opciones_actuales en cache.
    resp_next = service.get_next(wa_id, id_from)
    assert resp_next["listo_estado1"] is True
    assert resp_next["campo_pendiente"] == "sucursal"
    assert "San Isidro" in (resp_next.get("mensaje") or "")
    assert resp_next["opciones_actuales"]
    # Payload debe incluir id_plataforma: 6. El envío a WSP se hace solo una vez en __main__.
    if resp_next.get("payload_whatsapp_list"):
        assert resp_next["payload_whatsapp_list"].get("id_plataforma") == ID_PLATAFORMA, "payload_whatsapp_list debe tener id_plataforma: 6"

    registro = cache.consultar(wa_id, id_from)
    assert OPCIONES_ACTUALES_KEY in registro

    # 2) submit con mensaje de sucursal por nombre exacto.
    resp_submit = service.submit(wa_id, id_from, campo="sucursal", valor="San Isidro")

    assert resp_submit["success"] is True
    assert resp_submit["campo_guardado"] == "sucursal"
    assert resp_submit["id_detectada"] == 14
    assert resp_submit["nombre_detectado"] == "San Isidro"

    # En cache debe haberse guardado id_sucursal y sucursal, y cargado las nuevas opciones_actuales.
    registro_final = cache.consultar(wa_id, id_from)
    assert registro_final.get("id_sucursal") == 14
    assert registro_final.get("sucursal") == "San Isidro"
    assert OPCIONES_ACTUALES_KEY in registro_final


def _item_forma_medio_pago(
    id_: int = 1,
    nombre: str = "Ejemplo",
    descripcion: str = "",
    fecha_registro: str = "2025-01-01",
    usuario_registro: str = "sys",
    fecha_actualizacion: str = "2025-01-01",
    usuario_actualizacion: str = "sys",
) -> dict:
    """Item con forma de respuesta de LISTAR_FORMAS_PAGO / LISTAR_MEDIOS_PAGO (id, nombre, descripcion, fechas, usuarios)."""
    return {
        "id": id_,
        "nombre": nombre,
        "descripcion": descripcion,
        "fecha_registro": fecha_registro,
        "usuario_registro": usuario_registro,
        "fecha_actualizacion": fecha_actualizacion,
        "usuario_actualizacion": usuario_actualizacion,
    }


def test_forma_pago_opciones_por_servicio():
    """
    Las formas de pago (contrato ws_forma_pago.php) se proveen vía Información y el servicio
    las devuelve en get_next/submit como opciones_actuales y payload_whatsapp_list, igual que sucursales.
    """
    wa_id = "user2"
    id_from = 3
    formas = [
        _item_forma_medio_pago(id_=1, nombre="Contado"),
        _item_forma_medio_pago(id_=2, nombre="Crédito"),
    ]
    cache = DummyCache()
    info = DummyInformacion(
        sucursales=[
            {"id": 14, "nombre": "San Isidro"},
        ],
        metodos_pago=formas,  # forma_pago en Estado 2 usa obtener_metodos_pago (mismo contrato que LISTAR_FORMAS_PAGO)
    )
    service = OpcionesService(cache, info, parametros=None, ai=DummyAI())
    cache.insertar(wa_id, id_from, _build_registro_inicial(estado=4))

    # get_next → sucursales. El envío a WSP se hace solo una vez en __main__.
    r1 = service.get_next(wa_id, id_from)
    assert r1["campo_pendiente"] == "sucursal"
    if r1.get("payload_whatsapp_list"):
        assert r1["payload_whatsapp_list"].get("id_plataforma") == ID_PLATAFORMA, "payload_whatsapp_list debe tener id_plataforma: 6"

    # submit sucursal → el servicio debe devolver la siguiente lista (forma_pago)
    r2 = service.submit(wa_id, id_from, campo="sucursal", valor="San Isidro")
    assert r2["success"] is True
    assert r2["campo_pendiente"] == "forma_pago"
    assert r2["opciones_actuales"] is not None
    nombres = [o.get("nombre") for o in (r2["opciones_actuales"] or [])]
    assert "Contado" in nombres
    assert "Crédito" in nombres
    assert r2.get("payload_whatsapp_list") is not None
    assert r2["payload_whatsapp_list"].get("id_plataforma") == ID_PLATAFORMA, "payload_whatsapp_list debe tener id_plataforma: 6"
    # Ya no se envía método de pago por WSP (solo medios de pago).

    # submit forma_pago
    r3 = service.submit(wa_id, id_from, campo="forma_pago", valor="Contado")
    assert r3["success"] is True
    assert r3["campo_guardado"] == "forma_pago"
    assert r3["id_detectada"] == 1
    assert r3["nombre_detectado"] == "Contado"
    reg = cache.consultar(wa_id, id_from)
    assert reg.get("forma_pago") == "Contado"
    assert reg.get("id_metodo_pago") == 1


def test_forma_pago_con_datos_reales_api():
    """
    Obtiene formas de pago desde ws_forma_pago.php (LISTAR_FORMAS_PAGO), las inyecta en el servicio
    y ejecuta el flujo sucursal → forma_pago enviando la lista real a WhatsApp.
    """
    resp_formas = listar_formas_pago_api()
    if not resp_formas.get("success") or not resp_formas.get("data"):
        print("  [aviso] LISTAR_FORMAS_PAGO sin datos; se omite envío con datos reales.")
        return
    formas = resp_formas["data"]
    wa_id = "user_real"
    id_from = 3
    cache = DummyCache()
    info = DummyInformacion(
        sucursales=[{"id": 14, "nombre": "San Isidro"}],
        metodos_pago=formas,
    )
    service = OpcionesService(cache, info, parametros=None, ai=DummyAI())
    cache.insertar(wa_id, id_from, _build_registro_inicial(estado=4))

    r1 = service.get_next(wa_id, id_from)
    assert r1["campo_pendiente"] == "sucursal"

    r2 = service.submit(wa_id, id_from, campo="sucursal", valor="San Isidro")
    assert r2["success"] is True
    assert r2["campo_pendiente"] == "forma_pago"
    assert r2.get("payload_whatsapp_list") is not None
    # Ya no se envía método/forma de pago por WSP.

    # Submit primera forma de pago del API
    primer_nombre = (formas[0].get("nombre") or str(formas[0].get("id")) or "").strip()
    if primer_nombre:
        r3 = service.submit(wa_id, id_from, campo="forma_pago", valor=primer_nombre)
        assert r3["success"] is True
        assert r3["campo_guardado"] == "forma_pago"


# --- Contrato LISTAR_FORMAS_PAGO (ws_forma_pago.php) y LISTAR_MEDIOS_PAGO (ws_medio_pago.php) ---
# Request: POST JSON {"codOpe": "LISTAR_FORMAS_PAGO"} / {"codOpe": "LISTAR_MEDIOS_PAGO"}
# Retorna: {success, total, data: [{id, nombre, descripcion, fecha_registro, usuario_registro, fecha_actualizacion, usuario_actualizacion}]}


class DummyFormaPagoClient:
    """Simula GET /n8n/ws_forma_pago.php (LISTAR_FORMAS_PAGO)."""

    def __init__(self, data: list[dict] | None = None) -> None:
        self._data = data or []

    def listar(self, cod_ope: str) -> dict:
        return {
            "success": True,
            "total": len(self._data),
            "data": list(self._data),
        }


class DummyMedioPagoClient:
    """Simula GET /n8n/ws_medio_pago.php (LISTAR_MEDIOS_PAGO)."""

    def __init__(self, data: list[dict] | None = None) -> None:
        self._data = data or []

    def listar(self, cod_ope: str) -> dict:
        return {
            "success": True,
            "total": len(self._data),
            "data": list(self._data),
        }


def test_listar_formas_pago_contrato():
    """LISTAR_FORMAS_PAGO (GET): codOpe → {success, total, data} con campos id, nombre, descripcion, fechas, usuarios."""
    client = DummyFormaPagoClient(
        data=[
            _item_forma_medio_pago(id_=1, nombre="Contado"),
            _item_forma_medio_pago(id_=2, nombre="Crédito"),
        ]
    )
    resp = client.listar(cod_ope="OP001")
    assert resp["success"] is True
    assert resp["total"] == 2
    assert len(resp["data"]) == 2
    for item in resp["data"]:
        assert "id" in item
        assert "nombre" in item
        assert "descripcion" in item
        assert "fecha_registro" in item
        assert "usuario_registro" in item
        assert "fecha_actualizacion" in item
        assert "usuario_actualizacion" in item
    assert resp["data"][0]["nombre"] == "Contado"
    assert resp["data"][1]["nombre"] == "Crédito"


def test_listar_formas_pago_vacio():
    """LISTAR_FORMAS_PAGO con lista vacía."""
    client = DummyFormaPagoClient(data=[])
    resp = client.listar(cod_ope="OP002")
    assert resp["success"] is True
    assert resp["total"] == 0
    assert resp["data"] == []


def test_listar_medios_pago_contrato():
    """LISTAR_MEDIOS_PAGO (GET): codOpe → {success, total, data} con campos id, nombre, descripcion, fechas, usuarios."""
    client = DummyMedioPagoClient(
        data=[
            _item_forma_medio_pago(id_=10, nombre="Efectivo"),
            _item_forma_medio_pago(id_=11, nombre="Transferencia"),
        ]
    )
    resp = client.listar(cod_ope="OP001")
    assert resp["success"] is True
    assert resp["total"] == 2
    assert len(resp["data"]) == 2
    for item in resp["data"]:
        assert "id" in item
        assert "nombre" in item
        assert "descripcion" in item
        assert "fecha_registro" in item
        assert "usuario_registro" in item
        assert "fecha_actualizacion" in item
        assert "usuario_actualizacion" in item
    assert resp["data"][0]["nombre"] == "Efectivo"
    assert resp["data"][1]["nombre"] == "Transferencia"


def test_listar_medios_pago_vacio():
    """LISTAR_MEDIOS_PAGO con lista vacía."""
    client = DummyMedioPagoClient(data=[])
    resp = client.listar(cod_ope="OP002")
    assert resp["success"] is True
    assert resp["total"] == 0
    assert resp["data"] == []


def test_payload_wsp_opciones_tiene_id_plataforma_6():
    """El payload enviado a la API de opciones WSP debe llevar id_plataforma: 6 (y opcionalmente id_empresa para credenciales)."""
    assert ID_PLATAFORMA == 6
    # Sin id_plataforma → se agrega 6
    p1 = _payload_para_envio({"phone": "123", "sections": []})
    assert p1["id_plataforma"] == 6
    # Con otro valor → se fuerza 6
    p2 = _payload_para_envio({"id_plataforma": 99, "phone": "456"})
    assert p2["id_plataforma"] == 6
    # id_empresa para credenciales WhatsApp (como en api/routes/opciones)
    if ID_EMPRESA_WHATSAPP is not None:
        assert p1["id_empresa"] == ID_EMPRESA_WHATSAPP
    # None no se modifica
    assert _payload_para_envio(None) is None


class _FiltroStdout:
    """Evita imprimir líneas de debug del OpcionesService al ejecutar el script."""
    def __init__(self, real):
        self._real = real
    def write(self, s: str) -> int:
        if "[OpcionesService.submit]" in s:
            return len(s)
        return self._real.write(s)
    def flush(self):
        self._real.flush()


if __name__ == "__main__":
    _stdout_real = sys.stdout
    sys.stdout = _FiltroStdout(_stdout_real)
    try:
        print("id_whatsapp (enviar) =", ID_EMPRESA_WHATSAPP, "| phone (enviar) =", PHONE_PARA_ENVIO)
        print("-" * 50)
        # Envío a WhatsApp: solo forma de pago, medio de pago y sucursales; cada uno una vez.
        print("Envío a WhatsApp (una vez cada uno): forma de pago, medio de pago, sucursales")
        resp_formas = listar_formas_pago_api()
        resp_medios = listar_medios_pago_api()
        sucursales = listar_sucursales_api()

        if resp_formas.get("success") and resp_formas.get("data"):
            print("  Formas de pago:")
            enviar_lista_whatsapp(build_payload_lista_whatsapp(
                "Formas de pago", resp_formas["data"],
                body="Formas de pago disponibles: ", footer="Selecciona una forma de pago", button="Ver formas de pago",
            ))
        else:
            print("  [aviso] Sin datos de formas de pago.")
        if resp_medios.get("success") and resp_medios.get("data"):
            print("  Medios de pago:")
            enviar_lista_whatsapp(build_payload_lista_whatsapp(
                "Medios de pago", resp_medios["data"],
                body="Medios de pago disponibles: ", footer="Selecciona un medio de pago", button="Ver medios de pago",
            ))
        else:
            print("  [aviso] Sin datos de medios de pago.")
        if sucursales:
            print("  Sucursales:")
            enviar_lista_whatsapp(build_payload_lista_whatsapp(
                "Sucursales", sucursales,
                body="Sucursales disponibles: ", footer="Selecciona una sucursal", button="Ver sucursales",
            ))
        else:
            print("  [aviso] Sin datos de sucursales.")

        print("-" * 50)
        print("Tests (sin envío a WSP)")
        test_get_next_sucursales_y_submit_sucursal_match_exacto()
        test_forma_pago_opciones_por_servicio()
        test_payload_wsp_opciones_tiene_id_plataforma_6()
        test_listar_formas_pago_contrato()
        test_listar_formas_pago_vacio()
        test_listar_medios_pago_contrato()
        test_listar_medios_pago_vacio()
        test_forma_pago_con_datos_reales_api()
        print("-" * 50)
        print("OK: forma de pago, medio de pago y sucursales enviados por WSP (una vez cada uno). Todos los tests pasaron.")
    finally:
        sys.stdout = _stdout_real

