"""
Clasificador: mensaje + estado Redis entran a la IA.
- wa_id e id_from obligatorios: siempre se consulta Redis; el estado devuelto es el leído de Redis cuando existe registro.
- Casual: solo cuando no hay registro en Redis; con registro nunca se devuelve casual.
- Salidas: intencion, siguiente_estado (bool 3→4), estado (siempre de Redis; 0 si no hay registro).
Actualizar solo cuando estado < 3; estado >= 4 → opciones. Finalizar reutiliza la lógica con otros estados.
"""
from __future__ import annotations

from fastapi import HTTPException

from prompts.clasificador import build_prompt_router
from repositories.base import CacheRepository
from services.ai_service import AIService


def _obtener_estado(registro: dict | None) -> int:
    """Lee estado del registro en Redis/caché. 0 si no hay registro o no viene el campo."""
    if not registro:
        return 0
    try:
        v = registro.get("estado") or registro.get("paso_actual")  # paso_actual por compatibilidad
        if v is None or v == "":
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0


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

    def _respuesta_casual(self) -> dict:
        """Respuesta cuando no hay registro (o no se puede consultar Redis). Estado 0, destino casual."""
        return {
            "estado": 0,
            "intencion": "casual",
            "destino": "casual",
            "op_visible": "no definido",
            "opciones_ok": False,
            "siguiente_estado": False,
            "necesita_extraccion": False,
            "confianza": 1.0,
            "campo_detectado": "ninguno",
        }

    def ejecutar(self, mensaje: str, wa_id: str | None, id_from: int | None) -> dict:
        # wa_id e id_from obligatorios: siempre se consulta Redis para obtener el estado real.
        if wa_id is None or id_from is None:
            raise HTTPException(
                status_code=400,
                detail="wa_id e id_from son obligatorios para consultar el estado en Redis.",
            )

        estado = 0
        registro = None
        try:
            registro = self._repo.consultar(wa_id, id_from)
        except Exception:
            registro = None

        if not registro:
            return self._respuesta_casual()

        # Estado siempre leído de Redis cuando existe el registro.
        estado = _obtener_estado(registro)

        ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
        op = (registro.get("operacion") or registro.get("cod_ope") or "").strip().lower()
        operacion = "venta" if op == "ventas" else "compra" if op == "compras" else (op if op in ("venta", "compra") else None)
        opciones_completo = _opciones_completo(registro)

        prompt = build_prompt_router(
            mensaje, ultima_pregunta, estado, operacion, opciones_completo=opciones_completo
        )

        try:
            resultado = self._ai.completar_json(prompt)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        intencion = (resultado.get("intencion") or "").strip().lower()
        op_visible = (resultado.get("op_visible") or "no definido").strip().lower()
        if op_visible not in ("venta", "compra", "no definido"):
            op_visible = "no definido"
        opciones_ok = bool(resultado.get("opciones_ok") is True)
        siguiente_estado = bool(resultado.get("siguiente_estado") is True)

        mapeo_destino = {
            "actualizar": "extraccion",
            "opciones": "opciones",
            "resumen": "generar-resumen",
            "finalizar": "finalizar-operacion",
            "casual": "casual",
            "eliminar": "eliminar-operacion",
        }
        destino = mapeo_destino.get(intencion, "extraccion")

        # --- Orquestación: candados en orden (estado siempre el leído de Redis) ---

        # 1. Casual solo sin registro; con registro nunca devolver casual.
        if intencion == "casual" or destino == "casual":
            destino = "extraccion"
            intencion = "actualizar"

        # 2. Estado >= 4: "actualizar" del comprobante no aplica; es elegir opciones.
        if estado >= 4 and intencion == "actualizar":
            destino = "opciones"
            intencion = "opciones"
        # Estado < 3: opciones (sucursal/forma/medio) aún no disponible.
        if estado < 3 and (intencion == "opciones" or destino == "opciones"):
            destino = "extraccion"
            intencion = "actualizar"

        # 3. Finalizar solo con estado >= 4 y opciones completas; si no, a resumen.
        if destino == "finalizar-operacion" and (estado < 4 or not opciones_completo):
            destino = "generar-resumen"
            intencion = "resumen"

        # 4. Confirmación 3→4: mensaje de confirmar + estado 3 → confirmar-registro.
        if siguiente_estado and estado == 3:
            destino = "confirmar-registro"
            intencion = "opciones"

        necesidad_extraccion = intencion == "actualizar"

        return {
            "estado": estado,
            "intencion": intencion,
            "destino": destino,
            "op_visible": op_visible,
            "opciones_ok": opciones_ok,
            "siguiente_estado": siguiente_estado,
            "necesita_extraccion": necesidad_extraccion,
            "confianza": float(resultado.get("confianza") or 0.9),
            "campo_detectado": (resultado.get("campo_detectado") or "ninguno").strip().lower(),
        }
