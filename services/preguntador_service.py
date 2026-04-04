from prompts.plantillas import formatear_resumen_registro
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.helpers.resumen_visual import generar_resumen_completo
from services.whatsapp_sender import enviar_texto as _enviar_texto

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
        id_from: int,
        texto_desde_registrador: str | None = None,
        datos_registrados: dict | None = None,
        id_empresa: int | None = None,
        id_plataforma: int | None = None,
    ) -> dict:
        registro = self._repo.consultar(wa_id, id_from)
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
            if id_empresa is not None:
                _enviar_texto(id_empresa, wa_id, pregunta, id_plataforma)
            return {
                "pregunta_casual": pregunta,
                "requiere_botones": True,
                "btn1_id": "ventas", "btn1_title": "Es una Venta",
                "btn2_id": "compras", "btn2_title": "Es una Compra",
            }

        resultado = generar_resumen_completo(registro)
        pregunta_casual = resultado["texto_completo"]
        if bloques_previos:
            pregunta_casual = "\n\n".join(bloques_previos) + "\n\n" + pregunta_casual

        listo = resultado["listo_para_finalizar"]
        # Botones: confirmar si todo completo, tipo doc si falta
        tipo_doc = (registro.get("tipo_documento") or "").strip()
        if listo:
            requiere_botones = True
            btn1_id, btn1_title = "confirmar_registro", "Confirmar registro"
            btn2_id, btn2_title = "", ""
        elif not tipo_doc:
            requiere_botones = True
            btn1_id, btn1_title = "factura", "Factura"
            btn2_id, btn2_title = "boleta", "Boleta"
        else:
            requiere_botones = False
            btn1_id = btn1_title = btn2_id = btn2_title = ""

        if id_empresa is not None:
            _enviar_texto(id_empresa, wa_id, pregunta_casual, id_plataforma)

        return {
            "pregunta_casual": pregunta_casual,
            "requiere_botones": requiere_botones,
            "btn1_id": btn1_id, "btn1_title": btn1_title,
            "btn2_id": btn2_id, "btn2_title": btn2_title,
        }


class PreguntadorV2Service:
    """Servicio para /preguntador (versión con síntesis y diagnóstico separados)."""

    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(
        self,
        wa_id: str,
        id_from: int,
        texto_desde_registrador: str | None = None,
        datos_registrados: dict | None = None,
        id_empresa: int | None = None,
        id_plataforma: int | None = None,
    ) -> dict:
        registro = self._repo.consultar(wa_id, id_from)
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
            if id_empresa is not None:
                _enviar_texto(id_empresa, wa_id, texto, id_plataforma)
            return {
                "status": "ok",
                "whatsapp_output": {
                    "texto": texto,
                    "sintesis_visual": "",
                    "diagnostico": "",
                },
            }

        resultado = generar_resumen_completo(registro)
        sintesis = resultado["resumen_visual"] or "Aún no hay datos capturados."
        diagnostico = resultado["diagnostico"]
        texto_final = resultado["texto_completo"]
        if bloques_previos:
            texto_final = "\n\n".join(bloques_previos) + "\n\n" + texto_final

        listo_para_finalizar = resultado["listo_para_finalizar"]

        if id_empresa is not None:
            _enviar_texto(id_empresa, wa_id, texto_final, id_plataforma)

        return {
            "status": "ok",
            "whatsapp_output": {
                "texto": texto_final,
                "sintesis_visual": sintesis,
                "diagnostico": diagnostico,
            },
            "listo_para_finalizar": listo_para_finalizar,
        }
