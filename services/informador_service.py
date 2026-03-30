import json

from fastapi import HTTPException

from prompts.informador import build_prompt_info
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.whatsapp_sender import enviar_texto as _enviar_texto


class InformadorService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, mensaje: str, wa_id: str | None, id_from: int | None, *, id_empresa: int | None = None, id_plataforma: int | None = None) -> dict:
        estado_registro, resumen_debug = self._obtener_estado_y_debug(wa_id, id_from)
        prompt = build_prompt_info(mensaje, estado_registro, resumen_debug)

        try:
            texto = self._ai.completar_texto(prompt)
            texto_final = texto or "Puedes indicarme, por ejemplo: cliente con RUC o DNI, productos con cantidad y precio, tipo de comprobante (Factura/Boleta) y si el pago es al contado o crédito."
            if id_empresa is not None and wa_id:
                _enviar_texto(id_empresa, wa_id, texto_final, id_plataforma)
            return {
                "status": "ok",
                "destino": "informador",
                "whatsapp_output": {"texto": texto_final},
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def _obtener_estado_y_debug(self, wa_id: str | None, id_from: int | None) -> tuple[str, str]:
        if wa_id is None or id_from is None:
            return "(No se proporcionó wa_id/id_from; no hay contexto de registro.)", ""
        try:
            registro = self._repo.consultar(wa_id, id_from)
            debug = getattr(self._repo, "consultar_debug", lambda *a: {})(wa_id, id_from)
            resumen_debug = self._construir_resumen_debug(registro, debug)
            if registro:
                estado_str = json.dumps(registro, ensure_ascii=False, indent=0)
            else:
                estado_str = "(No hay registro activo; el usuario puede estar por iniciar una operación.)"
            return estado_str, resumen_debug
        except Exception:
            return "(No se pudo leer el estado actual del registro.)", ""

    @staticmethod
    def _construir_resumen_debug(registro: dict | None, debug: dict) -> str:
        """Genera un resumen en lenguaje natural del estado y últimas acciones para el informador."""
        lineas = []
        extraccion = (debug or {}).get("extraccion") or {}
        registro_debug = (debug or {}).get("registro") or {}

        if not registro:
            lineas.append("El usuario no tiene actualmente ningún registro en curso.")
            if registro_debug.get("motivo"):
                lineas.append(registro_debug["motivo"])
            return " ".join(lineas).strip() or "Sin información adicional de estado."

        estado = int(registro.get("estado") or 0)
        operacion = (registro.get("operacion") or registro.get("cod_ope") or "").strip().lower()

        if operacion in ("venta", "compra"):
            lineas.append(f"Tiene un registro de {operacion} en curso.")

        if estado == 0:
            lineas.append("Aún no se ha definido bien la operación o los datos principales.")
        elif estado == 1:
            lineas.append("Ha indicado el tipo de operación; faltan datos obligatorios (cliente o proveedor, comprobante, moneda, monto o productos).")
        elif estado == 2:
            lineas.append("Tiene algunos datos ya guardados pero aún faltan otros obligatorios.")
            que_falta = extraccion.get("que_falta")
            if que_falta:
                lineas.append(f"Último diagnóstico: {que_falta}")
        elif estado == 3:
            lineas.append("Ya tiene todos los datos obligatorios completos; puede confirmar el registro para pasar a elegir sucursal y forma de pago.")
        elif estado == 4:
            if registro_debug.get("confirmado"):
                lineas.append("El registro ya fue confirmado. El siguiente paso es elegir sucursal, forma de pago y medio de pago.")
            else:
                lineas.append("El registro está en fase de opciones (sucursal, forma de pago, medio de pago).")

        if extraccion.get("identificacion_no_encontrado"):
            lineas.append(f"Sobre la búsqueda del documento: {extraccion['identificacion_no_encontrado']}")
        if extraccion.get("aviso_fechas"):
            lineas.append(extraccion["aviso_fechas"])

        if not registro_debug.get("confirmado") and registro_debug.get("motivo"):
            lineas.append(registro_debug["motivo"])

        return " ".join(lineas).strip() or "Sin información adicional de estado."
