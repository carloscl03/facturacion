from prompts.preguntador import build_prompt_pregunta, build_prompt_preguntador_v2
from repositories.base import CacheRepository
from services.ai_service import AIService


class PreguntadorService:
    """Servicio para /generar-pregunta (versión original con botones)."""

    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, wa_id: str, id_empresa: int) -> dict:
        registro = self._repo.consultar(wa_id, id_empresa)

        if not registro:
            return {
                "pregunta_casual": "¡Hola! Soy MaravIA. Para empezar con el registro, selecciona el tipo de operación:",
                "requiere_botones": True,
                "btn1_id": "ventas", "btn1_title": "Es una Venta",
                "btn2_id": "compras", "btn2_title": "Es una Compra",
            }

        prompt = build_prompt_pregunta(registro)
        resultado = self._ai.completar_json(prompt)

        return {
            "pregunta_casual": resultado["resumen_y_guia"],
            "requiere_botones": resultado["requiere_botones"],
            "btn1_id": resultado.get("btn1_id", ""),
            "btn1_title": resultado.get("btn1_title", ""),
            "btn2_id": resultado.get("btn2_id", ""),
            "btn2_title": resultado.get("btn2_title", ""),
        }


class PreguntadorV2Service:
    """Servicio para /preguntador (versión con síntesis y diagnóstico separados)."""

    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, wa_id: str, id_empresa: int) -> dict:
        registro = self._repo.consultar(wa_id, id_empresa)

        if not registro:
            return {
                "status": "ok",
                "whatsapp_output": {
                    "texto": "¡Hola! Soy MaravIA. 🤖 ¿Qué operación deseas registrar hoy? Puedes enviarme una foto de un comprobante o decirme, por ejemplo: 'Venta de 2 laptops a Inversiones Sur'.",
                    "sintesis_visual": "",
                    "diagnostico": "",
                },
            }

        cod_ope = (registro.get("cod_ope") or "").strip().lower() or None
        prompt = build_prompt_preguntador_v2(registro, cod_ope)
        resultado = self._ai.completar_json(prompt)

        sintesis = (resultado.get("sintesis_visual") or "").strip() or "Aún no hay datos capturados."
        diagnostico = (resultado.get("diagnostico") or "").strip() or "Revisa los datos arriba y dime qué falta o si confirmas."
        texto_final = f"{sintesis}\n\n{diagnostico}"

        return {
            "status": "ok",
            "whatsapp_output": {
                "texto": texto_final,
                "sintesis_visual": sintesis,
                "diagnostico": diagnostico,
            },
        }
