"""
Agente Estado 2: opciones múltiples. Solo actúa cuando paso_actual >= 3 (Estado 1 completo).

Campos que define y persiste en Redis (cache):
  - sucursal      → sucursal_nombre (texto)
  - id_sucursal   → id numérico de sucursal (lista desde ws_informacion_ia OBTENER_SUCURSALES)
  - forma de pago → id_forma_pago (transferencia, TD, TC, billetera virtual)
  - medio de pago → tipo_operacion ("contado" | "credito")
"""
from __future__ import annotations

from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository

# Orden de campos Estado 2
CAMPOS_ESTADO2 = ("sucursal", "forma_pago", "tipo_pago")

# Forma de pago: id para la fila (envío a WhatsApp) -> id_forma_pago para Redis y backend
# Ajustar IDs si el backend usa otros valores
FORMAPAGO_IDS = {
    "transferencia": 1,
    "td": 2,
    "tc": 3,
    "billetera_virtual": 4,
}

# Método de pago: contado / crédito (tipo_operacion en Redis)
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

    def get_next(self, wa_id: str, id_empresa: int, phone: str) -> dict:
        """
        Devuelve el payload para la siguiente lista de opciones (Estado 2).
        Si Estado 1 no está completo, devuelve listo_estado1=False.
        El payload_whatsapp_list está listo para POST a ws_send_whatsapp_list.php.
        """
        registro = self._cache.consultar(wa_id, id_empresa) if wa_id and id_empresa else None
        if not registro:
            return {
                "listo_estado1": False,
                "mensaje": "No hay registro activo. Complete primero el registro (Estado 1).",
                "payload_whatsapp_list": None,
            }
        paso = int(registro.get("paso_actual") or 0)
        if paso < 3:
            return {
                "listo_estado1": False,
                "mensaje": "Faltan datos obligatorios del registro. Complete Estado 1 antes de elegir sucursal y forma de pago.",
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
            id_empresa=id_empresa,
            phone=phone or wa_id,
        )
        return {
            "listo_estado1": True,
            "estado2_completo": False,
            "campo_pendiente": campo,
            "payload_whatsapp_list": payload_list,
        }

    def submit(self, wa_id: str, id_empresa: int, campo: str, valor) -> dict:
        """
        Guarda la opción elegida en Redis y devuelve el siguiente paso.
        campo: "sucursal" | "forma_pago" | "tipo_pago"
        valor: id (int) para sucursal, clave (str) para forma_pago, "contado"|"credito" para tipo_pago.
        """
        if campo not in CAMPOS_ESTADO2:
            return {"success": False, "mensaje": f"Campo no válido: {campo}"}

        registro = self._cache.consultar(wa_id, id_empresa) if wa_id and id_empresa else None
        if not registro:
            return {"success": False, "mensaje": "No hay registro activo."}

        datos = {}
        if campo == "sucursal":
            try:
                id_suc = int(valor)
                datos["id_sucursal"] = id_suc
                lista_suc = self._informacion.obtener_sucursales(id_empresa)
                nombre = next((s["nombre"] for s in lista_suc if s.get("id") == id_suc), str(valor))
                datos["sucursal_nombre"] = nombre
            except (TypeError, ValueError):
                return {"success": False, "mensaje": "Valor de sucursal debe ser un ID numérico."}
        elif campo == "forma_pago":
            if isinstance(valor, str) and valor.lower() in FORMAPAGO_IDS:
                datos["id_forma_pago"] = FORMAPAGO_IDS[valor.lower()]
            elif isinstance(valor, int):
                datos["id_forma_pago"] = valor
            else:
                return {"success": False, "mensaje": "Valor de forma de pago no reconocido."}
        elif campo == "tipo_pago":
            v = (str(valor) or "").strip().lower()
            if v not in ("contado", "credito"):
                return {"success": False, "mensaje": "Valor debe ser contado o credito."}
            datos["tipo_operacion"] = v

        try:
            self._cache.actualizar(wa_id, id_empresa, datos)
        except Exception as e:
            return {"success": False, "mensaje": str(e)}

        siguiente = self._siguiente_campo_despues_de(registro, campo, datos)
        return {
            "success": True,
            "campo_guardado": campo,
            "siguiente": siguiente,
        }

    def _siguiente_campo_pendiente(self, registro: dict) -> str | None:
        if not registro.get("id_sucursal"):
            return "sucursal"
        if not registro.get("id_forma_pago"):
            return "forma_pago"
        if (registro.get("tipo_operacion") or "").strip().lower() not in ("contado", "credito"):
            return "tipo_pago"
        return None

    def _siguiente_campo_despues_de(self, registro: dict, campo_guardado: str, datos_guardados: dict) -> str | None:
        reg = {**registro, **datos_guardados}
        return self._siguiente_campo_pendiente(reg)

    def _construir_payload_lista(self, campo: str, id_empresa: int, phone: str) -> dict:
        """Construye el JSON para ws_send_whatsapp_list.php."""
        if campo == "sucursal":
            sucursales = self._informacion.obtener_sucursales(id_empresa)
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
            rows = [
                {"id": "transferencia", "title": "Transferencia", "description": "Pago por transferencia bancaria"},
                {"id": "td", "title": "Tarjeta de débito", "description": "Pago con tarjeta de débito"},
                {"id": "tc", "title": "Tarjeta de crédito", "description": "Pago con tarjeta de crédito"},
                {"id": "billetera_virtual", "title": "Billetera virtual", "description": "Yape, Plin, etc."},
            ]
            return {
                "id_empresa": id_empresa,
                "phone": phone,
                "body_text": "Selecciona entre estas opciones: ",
                "button_text": "Ver opciones",
                "header_text": "Forma de pago",
                "footer_text": "Selecciona forma de pago",
                "sections": [{"title": "Forma de pago", "rows": rows}],
            }
        if campo == "tipo_pago":
            rows = [
                {"id": "contado", "title": "Contado", "description": "Pago al contado"},
                {"id": "credito", "title": "Crédito", "description": "Pago a crédito"},
            ]
            return {
                "id_empresa": id_empresa,
                "phone": phone,
                "body_text": "Selecciona entre estas opciones: ",
                "button_text": "Ver opciones",
                "header_text": "Método de pago",
                "footer_text": "Contado o crédito",
                "sections": [{"title": "Método de pago", "rows": rows}],
            }
        return {}
