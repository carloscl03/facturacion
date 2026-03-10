"""DEPRECATED: Reemplazado por services/extraccion_service.py (flujo unificado sin metadata_ia)."""

import json

from config.estados import LISTO_PARA_FINALIZAR, PENDIENTE_IDENTIFICACION
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.identificador_service import IdentificadorService
from services.preguntador_service import PreguntadorV2Service
from services.registrador_service import RegistradorService


def _parsear_metadata(raw) -> dict:
    if isinstance(raw, dict):
        return raw.copy()
    if not raw:
        return {}
    s = str(raw).strip()
    if not s:
        return {}
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


class ConfirmadorService:
    """Orquesta Registrador + Identificador + PreguntadorV2 en una sola llamada."""

    def __init__(
        self,
        repo: CacheRepository,
        identificador: IdentificadorService,
        ai: AIService,
    ) -> None:
        self._repo = repo
        self._registrador = RegistradorService(repo, identificador)
        self._preguntador = PreguntadorV2Service(repo, ai)

    def ejecutar(self, wa_id: str, id_empresa: int) -> dict:
        # Leer estado ANTES del registrador para saber de qué flujo venimos (bandera).
        registro_previo = self._repo.consultar(wa_id, id_empresa) or {}
        metadata_prev = _parsear_metadata(registro_previo.get("metadata_ia"))
        estado_antes = (metadata_prev.get("estado_flujo") or "").strip()
        ultima_pregunta = (registro_previo.get("ultima_pregunta") or "").strip()
        venia_de_identificacion = (
            estado_antes == PENDIENTE_IDENTIFICACION
            or "IDENTIFICACION PENDIENTE" in (ultima_pregunta or "").upper()
        )

        res_reg = self._registrador.ejecutar(wa_id, id_empresa)

        if res_reg.get("status") != "exito":
            return res_reg

        datos_registrados = res_reg.get("datos_registrados")
        salida_id = res_reg.get("salida_identificador")

        res_preg = self._preguntador.ejecutar(
            wa_id,
            id_empresa,
            texto_desde_registrador=None,
            datos_registrados=None,
        )

        if res_preg.get("listo_para_finalizar") is True:
            registro = self._repo.consultar(wa_id, id_empresa) or {}
            metadata_ia = _parsear_metadata(registro.get("metadata_ia"))
            metadata_ia["estado_flujo"] = LISTO_PARA_FINALIZAR
            self._repo.actualizar(wa_id, id_empresa, {"metadata_ia": json.dumps(metadata_ia, ensure_ascii=False)})

        wo = res_preg.get("whatsapp_output", {})
        sintesis = (wo.get("sintesis_visual") or "").strip() or "Aún no hay datos capturados."
        diagnostico = (wo.get("diagnostico") or "").strip()
        mensaje_sintesis_y_faltantes = f"{sintesis}\n\n{diagnostico}".strip() if diagnostico else sintesis

        mensaje_identificacion = None
        if salida_id and salida_id.get("identificado") and salida_id.get("resumen_confirmacion"):
            mensaje_identificacion = (salida_id.get("resumen_confirmacion") or "").strip()

        # Solo se entrega UN mensaje según el tipo de registro:
        # - Si veníamos de dato identificado (confirmación de ficha): solo síntesis + preguntas.
        # - Si veníamos de dato analizado y el identificador encontró algo: solo mensaje identificación.
        # - Si veníamos de dato analizado y no hay identificación: solo síntesis + preguntas.
        if venia_de_identificacion:
            texto_completo = mensaje_sintesis_y_faltantes
            mensaje_identificacion_out = None
        else:
            if mensaje_identificacion:
                texto_completo = mensaje_identificacion
                mensaje_identificacion_out = mensaje_identificacion
            else:
                texto_completo = mensaje_sintesis_y_faltantes
                mensaje_identificacion_out = None

        out: dict = {
            "status": "ok",
            "whatsapp_output": {
                "texto": texto_completo,
                "sintesis_visual": sintesis,
                "diagnostico": diagnostico,
                "mensaje_sintesis_y_faltantes": mensaje_sintesis_y_faltantes,
                "mensaje_identificacion": mensaje_identificacion_out,
            },
            "datos_registrados": datos_registrados,
        }
        if salida_id:
            out["salida_identificador"] = salida_id

        return out
