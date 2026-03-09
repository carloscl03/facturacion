from repositories.base import CacheRepository
from services.ai_service import AIService
from services.identificador_service import IdentificadorService
from services.preguntador_service import PreguntadorV2Service
from services.registrador_service import RegistradorService


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
        res_reg = self._registrador.ejecutar(wa_id, id_empresa)

        if res_reg.get("status") != "exito":
            return res_reg

        datos_registrados = res_reg.get("datos_registrados")
        salida_id = res_reg.get("salida_identificador")
        # Solo anteponer mensaje del identificador (ficha) cuando hubo identificación; no pasar
        # datos_registrados para evitar resumen duplicado (el preguntador genera su propia síntesis desde cache).
        texto_desde_registrador = None
        if salida_id and salida_id.get("identificado") and salida_id.get("resumen_confirmacion"):
            texto_desde_registrador = salida_id.get("resumen_confirmacion")

        res_preg = self._preguntador.ejecutar(
            wa_id,
            id_empresa,
            texto_desde_registrador=texto_desde_registrador,
            datos_registrados=None,
        )

        out: dict = {
            "status": "ok",
            "whatsapp_output": res_preg.get("whatsapp_output", {}),
            "datos_registrados": datos_registrados,
        }
        if salida_id:
            out["salida_identificador"] = salida_id

        return out
