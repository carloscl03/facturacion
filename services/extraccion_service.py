from __future__ import annotations

import json

from prompts.extraccion import build_prompt_extractor
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.identificador_service import IdentificadorService


def _sin_nulos(d: dict) -> dict:
    if not isinstance(d, dict):
        return d
    return {
        k: v
        for k, v in d.items()
        if v is not None and v != "" and v != "null" and (not isinstance(v, str) or v.strip())
    }


class ExtraccionService:
    def __init__(
        self,
        repo: CacheRepository,
        ai: AIService,
        identificador: IdentificadorService | None = None,
        informacion_repo=None,
    ) -> None:
        self._repo = repo
        self._ai = ai
        self._identificador = identificador
        self._informacion_repo = informacion_repo

    # ------------------------------------------------------------------ #
    # Punto de entrada principal
    # ------------------------------------------------------------------ #
    def ejecutar(self, wa_id: str, mensaje: str, id_empresa: int) -> dict:
        lista = self._repo.consultar_lista(wa_id, id_empresa)
        estado_actual = lista[0] if lista else {}
        es_registro_nuevo = len(lista) == 0

        cod_ope = (estado_actual.get("cod_ope") or "").strip().lower()
        if cod_ope not in ("ventas", "compras"):
            cod_ope = None

        contexto_previo = self._detectar_contexto(mensaje, estado_actual)

        ultima_pregunta_bot = (estado_actual.get("ultima_pregunta") or "").strip()
        if len(ultima_pregunta_bot) > 800:
            ultima_pregunta_bot = ultima_pregunta_bot[:800] + "..."

        lista_sucursales = []
        if self._informacion_repo:
            try:
                lista_sucursales = self._informacion_repo.obtener_sucursales_publicas(id_empresa)
            except Exception:
                pass

        prompt = build_prompt_extractor(
            estado_actual=estado_actual,
            ultima_pregunta_bot=ultima_pregunta_bot,
            mensaje=mensaje,
            cod_ope=cod_ope,
            lista_sucursales=lista_sucursales if lista_sucursales else None,
        )

        try:
            output_ia = self._ai.completar_json(prompt)
        except Exception as e:
            return {"status": "error", "detalle": str(e)}

        propuesta = output_ia.get("propuesta_cache", {})

        mensaje_entendimiento = (output_ia.get("mensaje_entendimiento") or "").strip()
        resumen_visual = (output_ia.get("resumen_visual") or "").strip()
        diagnostico = (output_ia.get("diagnostico") or "").strip()
        listo_para_finalizar = bool(output_ia.get("listo_para_finalizar") is True)

        if mensaje_entendimiento:
            resumen_visual = f"{mensaje_entendimiento}\n\n{resumen_visual}".strip()

        # --- Fusionar propuesta con estado actual ---
        payload_base = self._construir_payload(propuesta, estado_actual, contexto_previo)
        payload_db = {k: v for k, v in payload_base.items() if self._es_valor_valido(v)}

        # Regla cod_ope: mantener el existente; si es nuevo, usar el de la IA.
        if cod_ope:
            payload_db["cod_ope"] = cod_ope
        elif es_registro_nuevo and payload_base.get("cod_ope"):
            payload_db["cod_ope"] = str(payload_base["cod_ope"]).strip().lower()
        else:
            payload_db.pop("cod_ope", None)

        # --- Identificacion inline ---
        req_id = output_ia.get("requiere_identificacion") or {}
        requiere_identificacion = {
            "activo": bool(req_id.get("activo")),
            "termino": (req_id.get("termino") or "").strip(),
            "tipo_ope": req_id.get("tipo_ope") or contexto_previo,
            "mensaje": (req_id.get("mensaje") or "").strip(),
        }
        if requiere_identificacion["activo"] and not requiere_identificacion["termino"]:
            requiere_identificacion["activo"] = False

        salida_identificador = None
        if requiere_identificacion["activo"] and self._identificador:
            tipo_busqueda = requiere_identificacion["tipo_ope"] or payload_db.get("cod_ope") or "ventas"
            salida_identificador = self._identificador.buscar(
                tipo_busqueda, requiere_identificacion["termino"], id_empresa,
            )
            if salida_identificador and salida_identificador.get("identificado"):
                campos_entidad = salida_identificador.get("campos_entidad") or {}
                for key in ("entidad_nombre", "entidad_numero_documento", "entidad_id_tipo_documento",
                            "entidad_id_maestro", "persona_id", "cliente_id", "proveedor_id"):
                    val = campos_entidad.get(key)
                    if val is not None and val != "":
                        payload_db[key] = val
                payload_db["identificado"] = True
            else:
                payload_db["identificado"] = False

        # --- Calcular paso_actual ---
        paso = self._calcular_paso(payload_db)
        payload_db["paso_actual"] = paso
        payload_db["is_ready"] = 1 if paso >= 3 else 0

        # --- Construir texto final para ultima_pregunta ---
        texto_completo = resumen_visual
        if diagnostico:
            texto_completo = f"{resumen_visual}\n\n{diagnostico}".strip()
        payload_db["ultima_pregunta"] = (
            texto_completo or "¿Los datos son correctos? Indique si desea confirmar o modificar algo."
        ).strip()

        # --- Persistir (sin metadata_ia) ---
        payload_db.pop("metadata_ia", None)
        db_res = self._repo.upsert(wa_id, id_empresa, payload_db, es_registro_nuevo)

        # --- Respuesta ---
        out: dict = {
            "status": "sincronizado",
            "paso_actual": paso,
            "listo_para_finalizar": listo_para_finalizar,
            "db_res": db_res,
            "whatsapp_output": {"texto": texto_completo},
            "requiere_identificacion": requiere_identificacion,
        }
        if salida_identificador:
            out["salida_identificador"] = salida_identificador
            if salida_identificador.get("identificado"):
                out["datos_entidad"] = salida_identificador.get("datos_identificados")
        elif requiere_identificacion["activo"]:
            out["datos_entidad"] = {
                "termino": requiere_identificacion["termino"],
                "tipo_ope": requiere_identificacion["tipo_ope"],
                "mensaje": requiere_identificacion["mensaje"]
                or f"Buscando '{requiere_identificacion['termino']}' en "
                   f"{'clientes' if requiere_identificacion['tipo_ope'] == 'ventas' else 'proveedores'}...",
            }
        return out

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _es_valor_valido(v) -> bool:
        if v is None:
            return False
        if isinstance(v, str) and v.strip() == "":
            return False
        if v == "null":
            return False
        return True

    @staticmethod
    def _calcular_paso(datos: dict) -> int:
        cod_ope = (datos.get("cod_ope") or "").strip().lower()
        if cod_ope not in ("ventas", "compras"):
            return 0

        tiene_monto = float(datos.get("monto_total") or 0) > 0
        tiene_entidad = bool(datos.get("entidad_nombre")) or bool(datos.get("entidad_id_maestro"))
        tiene_comprobante = bool(datos.get("id_comprobante_tipo"))
        tiene_numero_doc = bool((datos.get("numero_documento") or "").strip())
        tiene_moneda = bool(datos.get("id_moneda"))
        tiene_pago = (datos.get("tipo_operacion") or "") in ("contado", "credito")

        obligatorios = [tiene_monto, tiene_entidad, tiene_comprobante, tiene_numero_doc, tiene_moneda, tiene_pago]
        if all(obligatorios):
            return 3
        if any(obligatorios):
            return 2
        return 1

    @staticmethod
    def _detectar_contexto(mensaje: str, estado_actual: dict) -> str | None:
        msg = (mensaje or "").lower().strip()
        if any(x in msg for x in [" a venta", "a ventas", "cambiar a venta", "cambiarlo a venta",
                                   "cambiar a ventas", "pásalo a venta", "pásalo a ventas"]):
            return "ventas"
        if any(x in msg for x in [" a compra", "a compras", "cambiar a compra", "cambiarlo a compra",
                                   "cambiar a compras", "pásalo a compra"]):
            return "compras"
        if any(x in msg for x in ["venta", "ventas", "vender", "vendiendo",
                                   "es una venta", "registrar venta"]):
            return "ventas"
        if any(x in msg for x in ["compra", "compras", "gasto",
                                   "es una compra", "registrar compra"]):
            return "compras"
        cod = (estado_actual.get("cod_ope") or "").strip().lower()
        return cod if cod else None

    @staticmethod
    def _construir_payload(propuesta: dict, estado_actual: dict, contexto_previo: str | None) -> dict:
        productos_str = json.dumps(propuesta.get("productos_json", []), ensure_ascii=False)

        def obtener(campo, default=None):
            nuevo = propuesta.get(campo)
            viejo = estado_actual.get(campo)
            if nuevo not in [None, "", 0, "null"]:
                return nuevo
            return viejo if viejo not in [None, "", 0, "null"] else default

        return {
            "cod_ope": contexto_previo if contexto_previo else obtener("cod_ope", None),
            "entidad_nombre": obtener("entidad_nombre", ""),
            "entidad_numero_documento": obtener("entidad_numero_documento", ""),
            "entidad_id_tipo_documento": propuesta.get("entidad_id_tipo_documento") or estado_actual.get("entidad_id_tipo_documento"),
            "id_comprobante_tipo": obtener("id_comprobante_tipo", None),
            "numero_documento": obtener("numero_documento", "") or estado_actual.get("numero_documento"),
            "fecha_emision": obtener("fecha_emision", "") or estado_actual.get("fecha_emision"),
            "fecha_pago": obtener("fecha_pago", "") or estado_actual.get("fecha_pago"),
            "id_moneda": obtener("id_moneda", None),
            "tipo_operacion": obtener("tipo_operacion", None),
            "monto_total": float(propuesta.get("monto_total") or estado_actual.get("monto_total") or 0),
            "monto_base": float(propuesta.get("monto_base") or estado_actual.get("monto_base") or 0),
            "monto_impuesto": float(propuesta.get("monto_impuesto") or estado_actual.get("monto_impuesto") or 0),
            "caja_banco": obtener("caja_banco", "") or estado_actual.get("caja_banco"),
            "productos_json": productos_str,
            "id_sucursal": propuesta.get("id_sucursal") or estado_actual.get("id_sucursal"),
            "sucursal_nombre": obtener("sucursal_nombre", "") or obtener("sucursal", ""),
        }
