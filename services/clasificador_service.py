import re

from fastapi import HTTPException

from prompts.clasificador import build_prompt_router
from repositories.base import CacheRepository
from services.ai_service import AIService


def _obtener_estado(registro: dict | None) -> int:
    if not registro:
        return 0
    return int(registro.get("estado") or 0)


def _datos_obligatorios_completos(registro: dict | None) -> bool:
    """True si monto/detalle, entidad, tipo_documento y moneda están definidos (equivalente a estado 3)."""
    if not registro:
        return False
    tiene_monto = float(registro.get("monto_total") or 0) > 0
    prod = registro.get("productos")
    tiene_productos = isinstance(prod, list) and len(prod) > 0
    if isinstance(prod, str) and prod.strip() and prod.strip() != "[]":
        tiene_productos = True
    tiene_entidad = bool(registro.get("entidad_nombre") or registro.get("entidad_numero") or registro.get("entidad_id"))
    tiene_doc = bool(registro.get("tipo_documento"))
    tiene_moneda = bool(registro.get("moneda"))
    return (tiene_monto or tiene_productos) and tiene_entidad and tiene_doc and tiene_moneda


# Frases que indican solo confirmación (sin aportar datos). Mensaje normalizado: minúsculas, sin puntuación fuerte.
_CONFIRMACIONES = re.compile(
    r"^(s[ií]|confirmo?|dale|correcto|listo|ok|vale|confirmar|de\s+acuerdo|va|perfecto|"
    r"adelante|acepto|est[aá]\s+bien|procede?|confirmado|de\s+una|bueno|genial|"
    r"claro|por\s+supuesto|seguro|as[ií]\s+est[aá]|todo\s+bien)[\s\.\!]*$",
    re.IGNORECASE,
)


def _es_solo_confirmacion(mensaje: str) -> bool:
    """True si el mensaje es solo una afirmación de confirmación, sin datos nuevos."""
    if not mensaje or not isinstance(mensaje, str):
        return False
    txt = mensaje.strip()
    if len(txt) > 80:
        return False
    # Quitar puntuación final y normalizar espacios
    txt_norm = re.sub(r"[\.,;:\!]+$", "", txt).strip().lower()
    if _CONFIRMACIONES.match(txt_norm):
        return True
    # Frases cortas muy típicas
    if txt_norm in ("si", "sí", "sip", "yep", "yes", "confirmar", "confirmo", "dale", "ok", "listo"):
        return True
    return False


def _opciones_completo(registro: dict | None) -> bool:
    """True si sucursal, forma de pago y medio de pago ya están definidos (Estado 2 completo)."""
    if not registro:
        return False
    has_suc = bool(registro.get("id_sucursal"))
    has_fp = bool((registro.get("forma_pago") or "").strip())
    mp = (registro.get("medio_pago") or "").strip().lower()
    has_mp = mp in ("contado", "credito")
    return has_suc and has_fp and has_mp


class ClasificadorService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, mensaje: str, wa_id: str | None, id_from: int | None) -> dict:
        ultima_pregunta = ""
        estado = 0
        operacion = None
        registro = None
        if wa_id is not None and id_from is not None:
            try:
                registro = self._repo.consultar(wa_id, id_from)
                if not registro:
                    # Sin registro: solo entonces casual (sistema de botones; POST /casual).
                    return {
                        "intencion": "casual",
                        "destino": "casual",
                        "confianza": 1.0,
                        "urgencia": "baja",
                        "necesita_extraccion": False,
                        "campo_detectado": "ninguno",
                        "explicacion_soporte": "",
                    }
                ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
                estado = _obtener_estado(registro)
                op = (registro.get("operacion") or registro.get("cod_ope") or "").strip().lower()
                operacion = "venta" if op == "ventas" else "compra" if op == "compras" else (op if op in ("venta", "compra") else None)
            except Exception:
                registro = None

        opciones_completo = _opciones_completo(registro) if registro else False
        # Estado efectivo: si el cache no tiene "estado" pero los datos obligatorios están completos, tratar como 3
        datos_completos = _datos_obligatorios_completos(registro) if registro else False
        estado_efectivo = estado if estado > 0 else (3 if datos_completos else estado)
        mensaje_es_confirmacion = _es_solo_confirmacion(mensaje)

        prompt = build_prompt_router(
            mensaje, ultima_pregunta, estado_efectivo, operacion, opciones_completo=opciones_completo
        )

        try:
            resultado = self._ai.completar_json(prompt)

            intencion = resultado.get("intencion", "")
            resultado["necesita_extraccion"] = intencion == "actualizar"

            if not resultado.get("destino"):
                mapeo = {
                    "actualizar": "extraccion",
                    "confirmar_registro": "confirmar-registro",
                    "opciones": "opciones",
                    "resumen": "generar-resumen",
                    "finalizar": "finalizar-operacion",
                    "eliminar": "eliminar-operacion",
                    "informacion": "informador",
                    "casual": "casual",
                }
                resultado["destino"] = mapeo.get(intencion, "extraccion")

            if resultado.get("destino") in ("analizador", "registrador"):
                resultado["destino"] = "extraccion"

            # Heurística: si el mensaje es solo confirmación y los datos están completos (estado 3 o equivalente),
            # forzar confirmar_registro para cerrar actualizar y permitir el paso a opciones.
            if mensaje_es_confirmacion and (estado_efectivo == 3 or datos_completos):
                resultado["intencion"] = "confirmar_registro"
                resultado["destino"] = "confirmar-registro"
                resultado["necesita_extraccion"] = False

            # Opciones solo desde estado 4 (tras confirmar registro)
            if resultado.get("destino") == "opciones" and estado_efectivo < 4:
                resultado["destino"] = "extraccion"
                resultado["intencion"] = intencion if intencion != "opciones" else "actualizar"

            # Confirmar registro: permitir solo cuando estado efectivo = 3 (o datos completos). No redirigir a extracción.
            if resultado.get("destino") == "confirmar-registro" and estado_efectivo != 3 and not datos_completos:
                resultado["destino"] = "extraccion"
                resultado["intencion"] = intencion if intencion != "confirmar_registro" else "actualizar"

            # Finalizar solo con estado >= 4 y opciones (Estado 2) completas
            if resultado.get("destino") == "finalizar-operacion" and (estado < 4 or not opciones_completo):
                resultado["destino"] = "generar-resumen"
                resultado["intencion"] = "resumen"

            # Con registro activo es imposible ir a casual (solo sin registro se usa POST /casual)
            if registro is not None and resultado.get("destino") == "casual":
                resultado["destino"] = "extraccion"
                resultado["intencion"] = "actualizar"
                resultado["necesita_extraccion"] = True

            # La transición 3 → 4 la hace ConfirmarRegistroService (única fuente de verdad).
            # El clasificador solo enruta; no muta el estado.

            return resultado

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
