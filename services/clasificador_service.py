"""
Clasificador: orquestador de intenciones.
- Sin registro en Redis: sin IA — intención clara de venta/compra o mensaje JSON → extraccion; si no → casual.
- Con registro: mensaje + estado vía IA (build_prompt_router) y candados posteriores.
- wa_id e id_from obligatorios: siempre se consulta Redis; el estado devuelto es el leído de Redis (o 4 tras confirmar).
- Transición 3→4: cuando estado es 3 y el mensaje es confirmación, el clasificador escribe estado 4 en Redis y devuelve destino confirmar-registro.
- Con registro, la IA no debe devolver casual (se corrige a actualizar si lo hiciera).
- Salidas: intencion, destino, estado, siguiente_estado, etc.
"""
from __future__ import annotations

from fastapi import HTTPException

from prompts.clasificador import build_prompt_router
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.helpers.registro_domain import (
    obtener_estado,
    operacion_desde_registro,
    opciones_completas,
)


def _intencion_clara_venta_o_compra_sin_registro(mensaje: str) -> bool:
    """
    Sin registro en Redis: True si el usuario quiere iniciar venta/compra o envía datos (JSON).
    Alineado con prompts/clasificador (intención firme) y ExtraccionService._detectar_contexto.
    """
    msg_raw = (mensaje or "").strip()
    if not msg_raw:
        return False
    # JSON de comprobante / datos → extracción (misma regla que el prompt del router).
    if msg_raw.startswith("{") or msg_raw.startswith("["):
        return True
    msg = msg_raw.lower()
    # Frases típicas del prompt del clasificador (intención firme).
    frases = (
        "quiero registrar una venta",
        "quiero hacer una compra",
        "necesito una factura",
        "dame de alta una compra",
        "registrar venta",
        "registrar compra",
    )
    if any(f in msg for f in frases):
        return True
    if any(
        x in msg
        for x in (
            "venta",
            "ventas",
            "vender",
            "vendiendo",
            "es una venta",
            "registrar venta",
        )
    ):
        return True
    if any(
        x in msg
        for x in (
            "compra",
            "compras",
            "gasto",
            "es una compra",
            "registrar compra",
        )
    ):
        return True
    return False


def _op_visible_desde_mensaje_sin_registro(mensaje: str) -> str:
    """Inferencia ligera para op_visible cuando aún no hay registro."""
    msg = (mensaje or "").lower()
    if any(
        x in msg
        for x in (
            "compra",
            "compras",
            "gasto",
            "es una compra",
            "registrar compra",
            "proveedor",
            "dame de alta una compra",
        )
    ):
        return "compra"
    if any(
        x in msg
        for x in (
            "venta",
            "ventas",
            "vender",
            "vendiendo",
            "es una venta",
            "registrar venta",
            "factura",
            "boleta",
            "nota de venta",
        )
    ):
        return "venta"
    return "no definido"


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

        # Sin registro: solo casual (charla) o actualizar (venta/compra clara o JSON). No se llama a la IA.
        if not registro:
            if _intencion_clara_venta_o_compra_sin_registro(mensaje):
                return {
                    "estado": 0,
                    "intencion": "actualizar",
                    "destino": "extraccion",
                    "op_visible": _op_visible_desde_mensaje_sin_registro(mensaje),
                    "opciones_ok": False,
                    "siguiente_estado": False,
                    "necesita_extraccion": True,
                    "confianza": 1.0,
                    "campo_detectado": "ninguno",
                }
            return self._respuesta_casual()

        estado = obtener_estado(registro)
        ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
        operacion = operacion_desde_registro(registro)
        opciones_completo = opciones_completas(registro)

        prompt = build_prompt_router(
            mensaje,
            ultima_pregunta,
            estado,
            operacion,
            opciones_completo=opciones_completo,
            hay_registro_en_redis=True,
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

        # 1. Con registro nunca devolver casual; sin registro sí se puede devolver casual.
        if registro and (intencion == "casual" or destino == "casual"):
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

        # 4. Confirmación 3→4: mensaje de confirmar + estado 3 → el clasificador hace el cambio en Redis (solo si hay registro).
        if registro and siguiente_estado and estado == 3:
            destino = "confirmar-registro"
            intencion = "opciones"
            try:
                payload = {**registro, "estado": 4}
                self._repo.actualizar(wa_id, id_from, payload)
                estado = 4
            except Exception:
                pass

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
