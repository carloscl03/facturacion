from prompts.plantillas import formatear_resumen_registro
from prompts.preguntador import build_prompt_pregunta, build_prompt_preguntador_v2
from repositories.base import CacheRepository
from services.ai_service import AIService

# Emojis numéricos para listar preguntas obligatorias (1️⃣ 2️⃣ …)
EMOJI_NUM = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣")


def _formatear_obligatorias(texto: str) -> str:
    """Añade encabezado 'Datos obligatorios' y prefijos 1️⃣ 2️⃣ … a cada línea."""
    if not texto or not texto.strip():
        return ""
    lineas = [ln.strip() for ln in texto.strip().split("\n") if ln.strip()]
    if not lineas:
        return ""
    encabezado = "📋 *Datos obligatorios (para emitir el comprobante):*"
    partes = [f"{EMOJI_NUM[i]} {lineas[i]}" for i in range(min(len(lineas), len(EMOJI_NUM)))]
    if len(lineas) > len(EMOJI_NUM):
        partes.extend(lineas[len(EMOJI_NUM) :])
    return encabezado + "\n" + "\n".join(partes)


class PreguntadorService:
    """Servicio para /generar-pregunta (versión original con botones)."""

    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(
        self,
        wa_id: str,
        id_empresa: int,
        texto_desde_registrador: str | None = None,
        datos_registrados: dict | None = None,
    ) -> dict:
        registro = self._repo.consultar(wa_id, id_empresa)
        bloques_previos = []
        if texto_desde_registrador and texto_desde_registrador.strip():
            bloques_previos.append(texto_desde_registrador.strip())
        if datos_registrados:
            resumen = formatear_resumen_registro(datos_registrados)
            if resumen:
                bloques_previos.append(resumen)

        if not registro:
            pregunta = "¡Hola! Soy MaravIA. Para empezar con el registro, selecciona el tipo de operación:"
            if bloques_previos:
                pregunta = "\n\n".join(bloques_previos) + "\n\n" + pregunta
            return {
                "pregunta_casual": pregunta,
                "requiere_botones": True,
                "btn1_id": "ventas", "btn1_title": "Es una Venta",
                "btn2_id": "compras", "btn2_title": "Es una Compra",
            }

        prompt = build_prompt_pregunta(registro)
        resultado = self._ai.completar_json(prompt)
        pregunta_casual = resultado["resumen_y_guia"]
        if bloques_previos:
            pregunta_casual = "\n\n".join(bloques_previos) + "\n\n" + pregunta_casual

        return {
            "pregunta_casual": pregunta_casual,
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

    def ejecutar(
        self,
        wa_id: str,
        id_empresa: int,
        texto_desde_registrador: str | None = None,
        datos_registrados: dict | None = None,
    ) -> dict:
        registro = self._repo.consultar(wa_id, id_empresa)
        bloques_previos = []
        if texto_desde_registrador and texto_desde_registrador.strip():
            bloques_previos.append(texto_desde_registrador.strip())
        if datos_registrados:
            resumen = formatear_resumen_registro(datos_registrados)
            if resumen:
                bloques_previos.append(resumen)

        if not registro:
            texto = "¡Hola! Soy MaravIA. 🤖 ¿Qué operación deseas registrar hoy? Puedes enviarme una foto de un comprobante o decirme, por ejemplo: 'Venta de 2 laptops a Inversiones Sur'."
            if bloques_previos:
                texto = "\n\n".join(bloques_previos) + "\n\n" + texto
            return {
                "status": "ok",
                "whatsapp_output": {
                    "texto": texto,
                    "sintesis_visual": "",
                    "diagnostico": "",
                },
            }

        operacion = (registro.get("operacion") or "").strip().lower() or None
        prompt = build_prompt_preguntador_v2(registro, operacion)
        resultado = self._ai.completar_json(prompt)

        sintesis = (resultado.get("sintesis_visual") or "").strip() or "Aún no hay datos capturados."
        obligatorias_raw = (resultado.get("preguntas_obligatorias") or "").strip()
        obligatorias = _formatear_obligatorias(obligatorias_raw)
        opcionales = (resultado.get("preguntas_opcionales") or "").strip()
        # Retrocompatibilidad: si la IA devuelve "diagnostico", usarlo; si no, armar desde obligatorias + opcionales
        if resultado.get("diagnostico") is not None and (resultado.get("diagnostico") or "").strip():
            diagnostico = (resultado.get("diagnostico") or "").strip()
        else:
            partes = [p for p in (obligatorias, opcionales) if p]
            diagnostico = "\n\n".join(partes) if partes else "Revisa los datos arriba y dime qué falta o si confirmas."
        texto_final = f"{sintesis}\n\n{diagnostico}"
        if bloques_previos:
            texto_final = "\n\n".join(bloques_previos) + "\n\n" + texto_final

        listo_para_finalizar = bool(resultado.get("listo_para_finalizar") is True)

        return {
            "status": "ok",
            "whatsapp_output": {
                "texto": texto_final,
                "sintesis_visual": sintesis,
                "diagnostico": diagnostico,
            },
            "listo_para_finalizar": listo_para_finalizar,
        }
