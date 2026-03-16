import requests


class EntityRepository:
    """Acceso a la API de clientes, proveedores y compras."""

    def __init__(self, url_cliente: str, url_proveedor: str, url_compra: str = "") -> None:
        self._url_cliente = url_cliente
        self._url_proveedor = url_proveedor
        self._url_compra = url_compra

    # ------------------------------------------------------------------ #
    # BÚSQUEDA
    # ------------------------------------------------------------------ #

    def buscar_cliente(self, id_from: int, termino: str) -> dict | None:
        """Busca un cliente por RUC, DNI o nombre. Retorna data o None."""
        res = requests.get(
            self._url_cliente,
            params={"codOpe": "BUSCAR_CLIENTE", "empresa_id": id_from, "termino": termino},
        ).json()
        return res.get("data") if res.get("found") else None

    def buscar_proveedor(self, id_from: int, termino: str) -> dict | None:
        """Busca un proveedor por nombre. Retorna data o None."""
        res = requests.post(
            self._url_proveedor,
            json={"codOpe": "BUSCAR_PROVEEDOR", "id_from": id_from, "nombre_completo": termino},
        ).json()
        return res.get("data") if res.get("found") else None

    # ------------------------------------------------------------------ #
    # REGISTRO
    # ------------------------------------------------------------------ #

    def registrar_cliente(self, reg: dict, id_from: int) -> dict:
        """
        Registra un cliente nuevo.
        - Persona Natural (tipo_persona=1): nombres, apellido_paterno, id_tipo_documento, numero_documento.
        - Persona Jurídica (tipo_persona=2): razon_social, id_tipo_documento, ruc.
        """
        num_raw = str(reg.get("entidad_numero") or reg.get("entidad_numero_documento") or "").strip()
        id_tipo = 6 if len(num_raw) == 11 else 1
        numero_doc = num_raw
        nombre = str(reg.get("entidad_nombre") or "").strip() or "Sin nombre"
        es_ruc = id_tipo == 6

        payload: dict = {"codOpe": "REGISTRAR_CLIENTE", "empresa_id": id_from}
        if es_ruc:
            payload["tipo_persona"] = 2
            payload["razon_social"] = nombre
            payload["id_tipo_documento"] = id_tipo
            payload["ruc"] = numero_doc
        else:
            payload["tipo_persona"] = 1
            payload["nombres"] = nombre
            payload["apellido_paterno"] = "."
            payload["id_tipo_documento"] = id_tipo
            payload["numero_documento"] = numero_doc

        for k in ("telefono", "correo", "direccion", "nombre_comercial", "representante_legal"):
            if reg.get(k):
                payload[k] = reg[k]

        try:
            r = requests.post(self._url_cliente, json=payload, timeout=15)
            return r.json()
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ------------------------------------------------------------------ #
    # ACTUALIZACIÓN
    # ------------------------------------------------------------------ #

    def actualizar_cliente(self, cliente_id: int, reg: dict, id_from: int) -> dict:
        """Actualiza los datos de un cliente existente."""
        payload: dict = {
            "codOpe": "ACTUALIZAR_CLIENTE",
            "cliente_id": cliente_id,
            "empresa_id": id_from,
        }
        for k in (
            "nombres", "apellido_paterno", "apellido_materno", "id_tipo_documento",
            "numero_documento", "telefono", "correo", "direccion", "razon_social",
            "nombre_comercial", "ruc", "representante_legal",
        ):
            if reg.get(k) is not None and reg.get(k) != "":
                payload[k] = reg[k]

        if reg.get("entidad_nombre") and "nombres" not in payload and "razon_social" not in payload:
            payload["razon_social"] = reg["entidad_nombre"]
        ent_num = reg.get("entidad_numero") or reg.get("entidad_numero_documento")
        if ent_num:
            payload.setdefault("numero_documento", ent_num)
            payload.setdefault("ruc", ent_num)

        try:
            r = requests.post(self._url_cliente, json=payload, timeout=15)
            return r.json()
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ------------------------------------------------------------------ #
    # COMPRAS
    # ------------------------------------------------------------------ #

    def registrar_compra(self, payload: dict) -> dict:
        """
        Envía el payload REGISTRAR_COMPRA a ws_compra.php.
        Espera JSON con success, message, id_compra o error/details.
        """
        if not self._url_compra:
            return {"success": False, "message": "URL de compras no configurada"}
        try:
            r = requests.post(
                self._url_compra,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if "application/json" in (r.headers.get("content-type") or ""):
                return r.json()
            return {"success": False, "message": r.text, "status_code": r.status_code}
        except Exception as e:
            return {"success": False, "message": str(e)}
