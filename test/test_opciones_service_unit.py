from services.opciones_service import OpcionesService, OPCIONES_ACTUALES_KEY


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

