"""
Agente Estado 2: opciones múltiples (centro de costo, sucursal, forma de pago, medio de pago).
Solo actúa cuando el registro está confirmado (estado >= 4).
Persiste en Redis: id_centro_costo, centro_costo, id_sucursal, sucursal, forma_pago, medio_pago.

Alineado con test_opciones.py:
- Centros de costo: GET ws_parametros OBTENER_TABLAS_MAESTRAS (wa_id).
- Sucursales / Métodos de pago: POST ws_informacion_ia con id_empresa (tablas).
- Envío lista WhatsApp: id_empresa = id_whatsapp (credenciales). Filas: title ≤24, description ≤72.
"""
from __future__ import annotations

from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository
from repositories.parametros_repository import ParametrosRepository

# Orden del flujo Estado 2 (como en test_opciones: centros, sucursales, métodos de pago, luego medio)
CAMPOS_ESTADO2 = ("centro_costo", "sucursal", "forma_pago", "medio_pago")

# Límites WhatsApp list message (test_opciones.py)
MAX_ROW_TITLE = 24
MAX_ROW_DESC = 72


def _truncar(s: str, max_len: int) -> str:
    if not s or max_len <= 0:
        return (s or "")[:max_len] if max_len > 0 else ""
    return s[:max_len] if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"


class OpcionesService:
    def __init__(
        self,
        cache: CacheRepository,
        informacion: InformacionRepository,
        parametros: ParametrosRepository | None = None,
    ) -> None:
        self._cache = cache
        self._informacion = informacion
        self._parametros = parametros

    def get_next(
        self,
        wa_id: str,
        id_from: int,
        phone: str,
        id_empresa: int,
        id_empresa_tablas: int | None = None,
    ) -> dict:
        """
        id_from = contexto/cache. id_empresa = id_whatsapp (payload lista WhatsApp).
        id_empresa_tablas = empresa para jalar sucursales/métodos (si None, se usa id_empresa).
        """
        registro = self._cache.consultar(wa_id, id_from) if wa_id and id_from else None
        if not registro:
            return {
                "listo_estado1": False,
                "mensaje": "No hay registro activo. Complete primero el registro (Estado 1).",
                "payload_whatsapp_list": None,
            }
        estado = int(registro.get("estado") or 0)
        if estado < 4:
            return {
                "listo_estado1": False,
                "mensaje": "Primero confirme el registro (estado 3 → 4) antes de elegir centro de costo, sucursal y forma de pago.",
                "payload_whatsapp_list": None,
            }

        campo = self._siguiente_campo_pendiente(registro)
        if not campo:
            return {
                "listo_estado1": True,
                "estado2_completo": True,
                "campo_pendiente": None,
                "payload_whatsapp_list": None,
            }

        id_tablas = id_empresa_tablas if id_empresa_tablas is not None else id_empresa
        payload_list = self._construir_payload_lista(
            campo=campo,
            wa_id=wa_id,
            id_empresa=id_empresa,
            id_empresa_tablas=id_tablas,
            phone=phone or wa_id,
        )
        return {
            "listo_estado1": True,
            "estado2_completo": False,
            "campo_pendiente": campo,
            "payload_whatsapp_list": payload_list,
        }

    def submit(self, wa_id: str, id_from: int, campo: str, valor) -> dict:
        if campo not in CAMPOS_ESTADO2:
            return {"success": False, "mensaje": f"Campo no válido: {campo}"}

        registro = self._cache.consultar(wa_id, id_from) if wa_id and id_from else None
        if not registro:
            return {"success": False, "mensaje": "No hay registro activo."}

        datos = {}
        if campo == "centro_costo":
            try:
                id_cc = int(valor)
                datos["id_centro_costo"] = id_cc
                centros = []
                if self._parametros:
                    centros = self._parametros.obtener_centros_costo(wa_id)
                nombre = next((c.get("nombre") or str(c.get("id")) for c in centros if c.get("id") == id_cc), str(valor))
                datos["centro_costo"] = nombre
            except (TypeError, ValueError):
                return {"success": False, "mensaje": "Valor de centro de costo debe ser un ID numérico."}
        elif campo == "sucursal":
            try:
                id_suc = int(valor)
                datos["id_sucursal"] = id_suc
                lista_suc = self._informacion.obtener_sucursales(id_from)
                nombre = next((s["nombre"] for s in lista_suc if s.get("id") == id_suc), str(valor))
                datos["sucursal"] = nombre
            except (TypeError, ValueError):
                return {"success": False, "mensaje": "Valor de sucursal debe ser un ID numérico."}
        elif campo == "forma_pago":
            v = (str(valor) or "").strip()
            if not v:
                return {"success": False, "mensaje": "Valor de forma de pago vacío."}
            datos["forma_pago"] = v
        elif campo == "medio_pago":
            v = (str(valor) or "").strip().lower()
            if v not in ("contado", "credito"):
                return {"success": False, "mensaje": "Valor debe ser contado o credito."}
            datos["medio_pago"] = v

        try:
            self._cache.actualizar(wa_id, id_from, datos)
        except Exception as e:
            return {"success": False, "mensaje": str(e)}

        siguiente = self._siguiente_campo_despues_de(registro, datos)
        return {
            "success": True,
            "campo_guardado": campo,
            "siguiente": siguiente,
        }

    def _siguiente_campo_pendiente(self, registro: dict) -> str | None:
        if self._parametros and not registro.get("id_centro_costo"):
            return "centro_costo"
        if not registro.get("id_sucursal"):
            return "sucursal"
        if not (registro.get("forma_pago") or "").strip():
            return "forma_pago"
        if (registro.get("medio_pago") or "").strip().lower() not in ("contado", "credito"):
            return "medio_pago"
        return None

    def _siguiente_campo_despues_de(self, registro: dict, datos_guardados: dict) -> str | None:
        reg = {**registro, **datos_guardados}
        return self._siguiente_campo_pendiente(reg)

    def _filas_centros_costo(self, wa_id: str) -> list[dict]:
        """Filas para lista WhatsApp (title ≤24, description "")."""
        centros = self._parametros.obtener_centros_costo(wa_id) if self._parametros else []
        if not isinstance(centros, list):
            return []
        filas = []
        for c in centros:
            if isinstance(c, dict):
                cid = c.get("id")
                nombre = (c.get("nombre") or "").strip() or str(cid)
                filas.append({"id": str(cid), "title": _truncar(nombre, MAX_ROW_TITLE), "description": ""})
            elif isinstance(c, (str, int)):
                filas.append({"id": str(c), "title": _truncar(str(c), MAX_ROW_TITLE), "description": ""})
        return filas

    def _filas_sucursales(self, id_empresa_tablas: int) -> list[dict]:
        sucursales = self._informacion.obtener_sucursales(id_empresa_tablas)
        if not sucursales:
            return []
        return [
            {"id": str(s["id"]), "title": _truncar((s.get("nombre") or "").strip() or str(s["id"]), MAX_ROW_TITLE), "description": ""}
            for s in sucursales
        ]

    def _filas_metodos_pago(self, id_empresa_tablas: int) -> list[dict]:
        rows = self._informacion.obtener_metodos_pago(id_empresa_tablas)
        if not rows:
            return []
        return [
            {"id": r.get("id", ""), "title": _truncar(r.get("title") or "", MAX_ROW_TITLE), "description": _truncar(r.get("description") or "", MAX_ROW_DESC)}
            for r in rows
        ]

    def _build_payload_whatsapp(
        self,
        id_empresa: int,
        phone: str,
        section_title: str,
        rows: list[dict],
        body: str,
        header: str,
        footer: str,
        button: str,
    ) -> dict:
        """Payload para ws_send_whatsapp_list.php (como test_opciones.build_payload_whatsapp)."""
        if not rows:
            rows = [{"id": "0", "title": f"Sin {section_title.lower()}", "description": ""}]
        return {
            "id_empresa": id_empresa,
            "phone": phone,
            "body_text": body,
            "button_text": button,
            "header_text": header,
            "footer_text": footer,
            "sections": [{"title": section_title, "rows": rows}],
        }

    def _construir_payload_lista(
        self,
        campo: str,
        wa_id: str,
        id_empresa: int,
        id_empresa_tablas: int,
        phone: str,
    ) -> dict:
        """Payload para ws_send_whatsapp_list.php. id_empresa = id_whatsapp; tablas con id_empresa_tablas."""
        if campo == "centro_costo" and self._parametros:
            filas = self._filas_centros_costo(wa_id)
            return self._build_payload_whatsapp(
                id_empresa, phone,
                "Centros de costo", filas,
                "Centros de costo disponibles: ", "Centros de costo", "Selecciona un centro de costo", "Ver centros de costo",
            )
        if campo == "sucursal":
            filas = self._filas_sucursales(id_empresa_tablas)
            if not filas:
                filas = [{"id": "0", "title": "Sin sucursales", "description": ""}]
            return self._build_payload_whatsapp(
                id_empresa, phone,
                "Sucursales", filas,
                "Sucursales disponibles: ", "Sucursales", "Selecciona una sucursal", "Ver sucursales",
            )
        if campo == "forma_pago":
            filas = self._filas_metodos_pago(id_empresa_tablas)
            if not filas:
                filas = [{"id": "0", "title": "Sin métodos de pago", "description": ""}]
            return self._build_payload_whatsapp(
                id_empresa, phone,
                "Métodos de pago", filas,
                "Métodos de pago disponibles: ", "Métodos de pago", "Selecciona un método de pago", "Ver métodos de pago",
            )
        if campo == "medio_pago":
            rows = [
                {"id": "contado", "title": "Contado", "description": "Pago al contado"},
                {"id": "credito", "title": "Crédito", "description": "Pago a crédito"},
            ]
            return self._build_payload_whatsapp(
                id_empresa, phone,
                "Medio de pago", rows,
                "Selecciona entre estas opciones: ", "Medio de pago", "Contado o crédito", "Ver opciones",
            )
        return {}
