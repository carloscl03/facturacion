import json

from fastapi import HTTPException

from prompts.clasificador import build_prompt_router
from repositories.base import CacheRepository
from services.ai_service import AIService

MENSAJE_CASUAL_SIN_REGISTRO = (
    "Para comenzar, indique si desea registrar una *compra* o una *venta*."
)


def _obtener_paso_actual(registro: dict | None) -> int:
    if not registro:
        return 0
    return int(registro.get("paso_actual") or 0)


def _indica_compra_o_venta(mensaje: str) -> bool:
    """True si el mensaje menciona de forma clara compra o venta."""
    if not mensaje or not isinstance(mensaje, str):
        return False
    msg = mensaje.lower().strip()
    if not msg:
        return False
    # Palabras/frases que indican tipo de operación
    indicios = [
        "compra", "compras", "comprar", "compré", "quiero comprar",
        "venta", "ventas", "vender", "vendí", "quiero vender",
        "registrar una compra", "registrar una venta",
        "es una compra", "es una venta", "hacer una compra", "hacer una venta",
    ]
    return any(indicio in msg for indicio in indicios)


def _tiene_json_valido(mensaje: str) -> bool:
    """True si el mensaje contiene un JSON válido (objeto o array)."""
    if not mensaje or not isinstance(mensaje, str):
        return False
    msg = mensaje.strip()
    # Intentar parsear el mensaje completo
    try:
        parsed = json.loads(msg)
        return isinstance(parsed, (dict, list))
    except (json.JSONDecodeError, TypeError):
        pass
    # Buscar un fragmento que parezca JSON (empieza con { o [)
    inicio_obj = msg.find("{")
    inicio_arr = msg.find("[")
    for start in (inicio_obj, inicio_arr):
        if start == -1:
            continue
        try:
            parsed = json.loads(msg[start:])
            return isinstance(parsed, (dict, list))
        except (json.JSONDecodeError, TypeError):
            continue
    return False


class ClasificadorService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, mensaje: str, wa_id: str | None, id_empresa: int | None) -> dict:
        ultima_pregunta = ""
        paso_actual = 0
        cod_ope = None
        if wa_id is not None and id_empresa is not None:
            try:
                registro = self._repo.consultar(wa_id, id_empresa)
                if not registro:
                    # Sin registro en Redis: solo casual si no indica compra/venta ni trae JSON
                    if not _indica_compra_o_venta(mensaje) and not _tiene_json_valido(mensaje):
                        return {
                            "intencion": "casual",
                            "destino": "casual",
                            "confianza": 1.0,
                            "urgencia": "baja",
                            "necesita_extraccion": False,
                            "campo_detectado": "ninguno",
                            "explicacion_soporte": "",
                            "mensaje_casual_sugerido": MENSAJE_CASUAL_SIN_REGISTRO,
                        }
                    # Indica compra/venta o tiene JSON: seguir con clasificador (paso_actual=0, cod_ope=None)
                else:
                    ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
                    paso_actual = _obtener_paso_actual(registro)
                    cod_ope = (registro.get("cod_ope") or "").strip() or None
            except Exception:
                pass

        prompt = build_prompt_router(mensaje, ultima_pregunta, paso_actual, cod_ope)

        try:
            resultado = self._ai.completar_json(prompt)

            intencion = resultado.get("intencion", "")
            resultado["necesita_extraccion"] = intencion == "actualizar"

            if not resultado.get("destino"):
                mapeo = {
                    "actualizar": "extraccion",
                    "resumen": "generar-resumen",
                    "finalizar": "finalizar-operacion",
                    "eliminar": "eliminar-operacion",
                    "informacion": "informador",
                    "casual": "casual",
                }
                resultado["destino"] = mapeo.get(intencion, "extraccion")

            if resultado.get("destino") in ("analizador", "registrador"):
                resultado["destino"] = "extraccion"

            return resultado

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
