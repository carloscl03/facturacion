"""
Agente Estado 2: opciones múltiples (sucursal, forma de pago, medio de pago).
Solo actúa cuando el registro está confirmado (estado >= 4).
Persiste en Redis: id_sucursal, sucursal, forma_pago (str), medio_pago (str).

Convención: id_from = id_informacion (API de información: sucursales, métodos de pago).
id_empresa = id_whatsapp (solo para el payload a ws_send_whatsapp_list.php).
La lista de forma de pago se obtiene de ws_informacion_ia (OBTENER_METODOS_PAGO) como en test_obtener_pagos.
"""
from __future__ import annotations

from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository

CAMPOS_ESTADO2 = ("sucursal", "forma_pago", "medio_pago")

TIPO_PAGO_OPCIONES = (
    ("contado", "Contado", "Pago al contado"),
    ("credito", "Crédito", "Pago a crédito"),
)


class OpcionesService:
    def __init__(
        self,
        cache: CacheRepository,
        informacion: InformacionRepository,
    ) -> None:
        self._cache = cache
        self._informacion = informacion

    def get_next(
        self,
        wa_id: str,
        id_from: int,
        phone: str,
        id_empresa: int,
    ) -> dict:
        """id_from = id_informacion (cache y API información). id_empresa = id_whatsapp (payload lista WhatsApp)."""
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
                "mensaje": "Primero confirme el registro (estado 3 → 4) antes de elegir sucursal y forma de pago.",
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

        payload_list = self._construir_payload_lista(
            campo=campo,
            id_from=id_from,
            id_empresa=id_empresa,
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
        if campo == "sucursal":
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
            # Acepta id de banco (numérico), "yape", "plin" o los legacy transferencia/td/tc/billetera_virtual
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

    def _construir_payload_lista(
        self,
        campo: str,
        id_from: int,
        id_empresa: int,
        phone: str,
    ) -> dict:
        """Payload para ws_send_whatsapp_list.php. id_from = id_informacion; id_empresa = id_whatsapp."""
        if campo == "sucursal":
            sucursales = self._informacion.obtener_sucursales(id_from)
            rows = [{"id": str(s["id"]), "title": s["nombre"], "description": ""} for s in sucursales]
            if not rows:
                rows = [{"id": "0", "title": "Sin sucursales", "description": ""}]
            return {
                "id_empresa": id_empresa,
                "phone": phone,
                "body_text": "Selecciona entre estas opciones: ",
                "button_text": "Ver opciones",
                "header_text": "Sucursal",
                "footer_text": "Selecciona una sucursal",
                "sections": [{"title": "Sucursales", "rows": rows}],
            }
        if campo == "forma_pago":
            # Igual que test_obtener_pagos: OBTENER_METODOS_PAGO con id_from, lista con id_empresa
            rows = self._informacion.obtener_metodos_pago(id_from)
            if not rows:
                rows = [{"id": "0", "title": "Sin métodos de pago", "description": ""}]
            return {
                "id_empresa": id_empresa,
                "phone": phone,
                "body_text": "Métodos de pago disponibles: ",
                "button_text": "Ver métodos de pago",
                "header_text": "Métodos de pago",
                "footer_text": "Selecciona un método de pago",
                "sections": [{"title": "Métodos de pago", "rows": rows}],
            }
        if campo == "medio_pago":
            rows = [
                {"id": "contado", "title": "Contado", "description": "Pago al contado"},
                {"id": "credito", "title": "Crédito", "description": "Pago a crédito"},
            ]
            return {
                "id_empresa": id_empresa,
                "phone": phone,
                "body_text": "Selecciona entre estas opciones: ",
                "button_text": "Ver opciones",
                "header_text": "Medio de pago",
                "footer_text": "Contado o crédito",
                "sections": [{"title": "Medio de pago", "rows": rows}],
            }
        return {}
