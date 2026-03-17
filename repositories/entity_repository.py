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
        """Busca un cliente por RUC, DNI o nombre. Retorna data con cliente_id o None."""
        res = requests.get(
            self._url_cliente,
            params={"codOpe": "BUSCAR_CLIENTE", "empresa_id": id_from, "termino": termino},
        ).json()
        if not res.get("found"):
            return None
        data = res.get("data") or {}
        if res.get("cliente_id") is not None:
            data = {**data, "cliente_id": res["cliente_id"]}
        return data

    def buscar_proveedor(self, id_from: int, termino: str) -> dict | None:
        """Busca un proveedor por nombre, RUC o DNI. Retorna data con proveedor_id/persona_id o None."""
        termino = (termino or "").strip()
        # La API espera id_empresa y nombre_completo (acepta RUC/DNI como número o string)
        payload = {
            "codOpe": "BUSCAR_PROVEEDOR",
            "id_empresa": id_from,
            "nombre_completo": termino,
        }
        res = requests.post(self._url_proveedor, json=payload, timeout=15).json()
        if not res.get("found"):
            return None
        data = res.get("data") or {}
        # Asegurar proveedor_id y persona_id (pueden venir en raíz o dentro de data)
        if res.get("proveedor_id") is not None:
            data = {**data, "proveedor_id": res["proveedor_id"]}
        if res.get("persona_id") is not None:
            data = {**data, "persona_id": res["persona_id"]}
        return data

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
            try:
                data = r.json()
            except Exception:
                data = {"success": False, "message": r.text or f"Respuesta no JSON (status {r.status_code})"}
            if r.status_code >= 400:
                data["success"] = False
            if not data.get("success") and "message" not in data:
                data["message"] = (
                    data.get("error") or data.get("msg") or data.get("detail") or data.get("mensaje")
                    or (r.text and r.text[:200])
                    or f"Error HTTP {r.status_code}"
                )
            # Normalizar cliente_id por si viene en data.data o como id
            if data.get("success") and "cliente_id" not in data:
                data["cliente_id"] = (data.get("data") or {}).get("cliente_id") or data.get("data", {}).get("id") or data.get("id")
            return data
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
        Errores posibles (ws_compra.php): 400 (JSON inválido, codOpe/empresa_id/usuario_id,
        campo requerido, detalles vacíos, nro_documento inválido), 405 (método), 500 (BD, SP).
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
            try:
                data = r.json()
            except Exception:
                data = {}
            # 4xx/5xx: forzar success=False y unificar error/message/details
            if r.status_code >= 400:
                return {
                    "success": False,
                    "error": data.get("error"),
                    "message": data.get("message") or data.get("error") or r.text or f"Error HTTP {r.status_code}",
                    "details": data.get("details"),
                    "status_code": r.status_code,
                }
            # 2xx pero body con success=false (p. ej. SP devolvió error)
            if not data.get("success") and "error" not in data and "message" not in data:
                data["error"] = data.get("details") or "Error al registrar compra"
                data["message"] = data.get("message") or data["error"]
            return data
        except Exception as e:
            return {"success": False, "message": str(e)}
