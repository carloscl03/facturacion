"""
Clasificador: mensaje + estado Redis entran a la IA.
Salidas: (1) intencion (prioridad actualizar|opciones|resumen|finalizar|casual|eliminar), (2) siguiente_estado (bool 3→4).
Actualizar solo cuando estado < 3; estado >= 4 → opciones. Finalizar reutiliza la lógica con otros estados.
"""
from __future__ import annotations

from fastapi import HTTPException

from prompts.clasificador import build_prompt_router
from repositories.base import CacheRepository
from services.ai_service import AIService


def _obtener_estado(registro: dict | None) -> int:
    if not registro:
        return 0
    return int(registro.get("estado") or 0)


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
                    return {
                        "intencion": "casual",
                        "destino": "casual",
                        "op_visible": "no definido",
                        "opciones_ok": False,
                        "siguiente_estado": False,
                        "necesita_extraccion": False,
                        "confianza": 1.0,
                        "campo_detectado": "ninguno",
                    }
                ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
                estado = _obtener_estado(registro)
                op = (registro.get("operacion") or registro.get("cod_ope") or "").strip().lower()
                operacion = "venta" if op == "ventas" else "compra" if op == "compras" else (op if op in ("venta", "compra") else None)
            except Exception:
                registro = None

        opciones_completo = _opciones_completo(registro) if registro else False

        prompt = build_prompt_router(
            mensaje, ultima_pregunta, estado, operacion, opciones_completo=opciones_completo
        )

        try:
            resultado = self._ai.completar_json(prompt)

            intencion = (resultado.get("intencion") or "").strip().lower()
            op_visible = (resultado.get("op_visible") or "no definido").strip().lower()
            if op_visible not in ("venta", "compra", "no definido"):
                op_visible = "no definido"
            opciones_ok = bool(resultado.get("opciones_ok") is True)
            siguiente_estado = bool(resultado.get("siguiente_estado") is True)

            # Mapeo intención → destino
            mapeo_destino = {
                "actualizar": "extraccion",
                "opciones": "opciones",
                "resumen": "generar-resumen",
                "finalizar": "finalizar-operacion",
                "casual": "casual",
                "eliminar": "eliminar-operacion",
            }
            destino = mapeo_destino.get(intencion, "extraccion")

            # Actualizar solo cuando estado < 3; estado >= 4 → opciones
            if estado >= 4 and intencion == "actualizar":
                destino = "opciones"
                intencion = "opciones"
            if estado < 3 and intencion == "opciones":
                destino = "extraccion"
                intencion = "actualizar"

            # Finalizar: misma lógica que opciones pero para emitir — solo estado >= 4 y opciones_ok
            if destino == "finalizar-operacion" and (estado < 4 or not opciones_completo):
                destino = "generar-resumen"
                intencion = "resumen"

            # Con registro activo no ir a casual
            if registro is not None and destino == "casual":
                destino = "extraccion"
                intencion = "actualizar"

            # Cuando siguiente_estado = true (estado 3 + confirmación), destino = confirmar-registro para cambiar 3→4
            if siguiente_estado and estado == 3:
                destino = "confirmar-registro"

            necesidad_extraccion = intencion == "actualizar"

            return {
                "intencion": intencion,
                "destino": destino,
                "op_visible": op_visible,
                "opciones_ok": opciones_ok,
                "siguiente_estado": siguiente_estado,
                "necesita_extraccion": necesidad_extraccion,
                "confianza": float(resultado.get("confianza") or 0.9),
                "campo_detectado": (resultado.get("campo_detectado") or "ninguno").strip().lower(),
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
