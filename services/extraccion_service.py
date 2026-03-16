from __future__ import annotations

import json

from prompts.extraccion import build_prompt_extractor
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.helpers.productos import productos_a_str
from services.helpers.registro_domain import calcular_estado, operacion_desde_registro
from services.identificador_service import IdentificadorService


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

    def ejecutar(self, wa_id: str, mensaje: str, id_from: int) -> dict:
        lista = self._repo.consultar_lista(wa_id, id_from)
        estado_actual = lista[0] if lista else {}
        es_registro_nuevo = len(lista) == 0

        # Leer operación de registro (operacion o cod_ope por compatibilidad con backend)
        operacion = operacion_desde_registro(estado_actual)

        contexto_previo = self._detectar_contexto(mensaje, estado_actual)

        ultima_kw = (estado_actual.get("ultima_pregunta") or "").strip()

        prompt = build_prompt_extractor(
            estado_actual=estado_actual,
            ultima_pregunta_bot=ultima_kw,
            mensaje=mensaje,
            operacion=operacion,
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
        cambiar_estado_a_4 = bool(output_ia.get("cambiar_estado_a_4") is True)
        ultima_pregunta_keyword = (output_ia.get("ultima_pregunta_keyword") or "").strip()

        if mensaje_entendimiento:
            resumen_visual = f"{mensaje_entendimiento}\n\n{resumen_visual}".strip()

        payload_base = self._construir_payload(propuesta, estado_actual, contexto_previo)
        payload_db = {k: v for k, v in payload_base.items() if self._es_valor_valido(v)}

        # Fijar operación (compra/venta): solo persistir "operacion" en Redis (sin cod_ope)
        op_val = operacion or (str(payload_base.get("operacion") or "").strip().lower())
        if op_val == "compras":
            op_val = "compra"
        elif op_val == "ventas":
            op_val = "venta"
        if op_val in ("venta", "compra"):
            payload_db["operacion"] = op_val
        else:
            # Preservar la que ya tenía el registro (re-persistir para no perderla)
            if estado_actual.get("operacion") in ("venta", "compra"):
                payload_db["operacion"] = estado_actual["operacion"]
            elif estado_actual.get("cod_ope") in ("ventas", "compras"):
                payload_db["operacion"] = "venta" if estado_actual["cod_ope"] == "ventas" else "compra"
            else:
                payload_db.pop("operacion", None)
        payload_db.pop("cod_ope", None)  # no guardar cod_ope; solo operacion

        # --- Identificación inline (estricta cuando hay RUC/DNI) ---
        req_id = output_ia.get("requiere_identificacion") or {}
        requiere_identificacion = {
            "activo": bool(req_id.get("activo")),
            "termino": (req_id.get("termino") or "").strip(),
            "tipo_ope": req_id.get("tipo_ope") or contexto_previo,
            "mensaje": (req_id.get("mensaje") or "").strip(),
        }
        # Forzar identificación si hay entidad_numero de 8 o 11 dígitos y aún no tenemos entidad_id
        # Incluir payload_base por si el número vino en propuesta como "ruc"/"dni" y ya se normalizó ahí
        num_doc = (
            payload_db.get("entidad_numero")
            or payload_base.get("entidad_numero")
            or estado_actual.get("entidad_numero")
            or ""
        ).strip()
        num_solo_digitos = "".join(c for c in str(num_doc) if c.isdigit())
        if len(num_solo_digitos) in (8, 11) and not (payload_db.get("entidad_id") or estado_actual.get("entidad_id")):
            requiere_identificacion["activo"] = True
            if not requiere_identificacion["termino"]:
                requiere_identificacion["termino"] = num_solo_digitos
            requiere_identificacion["tipo_ope"] = requiere_identificacion["tipo_ope"] or payload_db.get("operacion") or "venta"
        if requiere_identificacion["activo"] and not requiere_identificacion["termino"]:
            requiere_identificacion["activo"] = False

        salida_identificador = None
        if requiere_identificacion["activo"] and self._identificador:
            tipo_raw = requiere_identificacion["tipo_ope"] or payload_db.get("operacion") or "venta"
            tipo_busqueda = "ventas" if (tipo_raw or "").lower().strip() == "venta" else "compras" if (tipo_raw or "").lower().strip() == "compra" else tipo_raw
            salida_identificador = self._identificador.buscar(
                tipo_busqueda, requiere_identificacion["termino"], id_from,
            )
            if salida_identificador and salida_identificador.get("identificado"):
                campos_entidad = salida_identificador.get("campos_entidad") or {}
                # Siempre usar nombre exacto e id del servicio de identificación
                if campos_entidad.get("entidad_nombre"):
                    payload_db["entidad_nombre"] = campos_entidad["entidad_nombre"]
                doc = campos_entidad.get("entidad_numero_documento") or campos_entidad.get("entidad_numero")
                if doc:
                    payload_db["entidad_numero"] = doc
                maestro = (
                    campos_entidad.get("entidad_id")
                    or campos_entidad.get("entidad_id_maestro")
                    or campos_entidad.get("cliente_id")
                    or campos_entidad.get("proveedor_id")
                )
                if maestro:
                    payload_db["entidad_id"] = maestro
                    payload_db["id_identificado"] = maestro
                    payload_db["identificado"] = True

        # --- Calcular estado (una sola asignación; no sobrescribir estado 4) ---
        estado_calculado = calcular_estado(payload_db)
        # Estado 4 solo lo pone confirmar_registro; extracción no debe pisarlo
        if estado_actual.get("estado") == 4:
            estado = 4
        else:
            estado = estado_calculado
        payload_db["estado"] = estado

        # --- ultima_pregunta como keyword ---
        texto_completo = resumen_visual
        if diagnostico:
            texto_completo = f"{resumen_visual}\n\n{diagnostico}".strip()
        payload_db["ultima_pregunta"] = ultima_pregunta_keyword or "inicio"

        # --- Persistir ---
        db_res = self._repo.upsert(wa_id, id_from, payload_db, es_registro_nuevo)

        # La transición 3 → 4 la hace exclusivamente el flujo confirmar-registro (clasificador devuelve siguiente_estado y el orquestador llama a confirmar-registro).

        out: dict = {
            "status": "sincronizado",
            "estado": estado,
            "listo_para_finalizar": listo_para_finalizar,
            "cambiar_estado_a_4": cambiar_estado_a_4,
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
                   f"{'clientes' if requiere_identificacion['tipo_ope'] == 'venta' else 'proveedores'}...",
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
    def _calcular_estado(datos: dict) -> int:
        op = (datos.get("operacion") or "").strip().lower()
        if op not in ("venta", "compra"):
            return 0

        tiene_monto = float(datos.get("monto_total") or 0) > 0
        tiene_productos = False
        prod = datos.get("productos")
        if isinstance(prod, list) and len(prod) > 0:
            tiene_productos = True
        elif isinstance(prod, str) and prod.strip() and prod.strip() != "[]":
            tiene_productos = True

        tiene_entidad = bool(datos.get("entidad_nombre")) or bool(datos.get("entidad_id"))
        tiene_documento = bool(datos.get("tipo_documento"))
        tiene_moneda = bool(datos.get("moneda"))

        obligatorios = [
            tiene_monto or tiene_productos,
            tiene_entidad,
            tiene_documento,
            tiene_moneda,
        ]
        if all(obligatorios):
            return 3
        if any(obligatorios):
            return 2
        return 1

    @staticmethod
    def _detectar_contexto(mensaje: str, estado_actual: dict) -> str | None:
        msg = (mensaje or "").lower().strip()
        if any(x in msg for x in ["venta", "ventas", "vender", "vendiendo",
                                   "es una venta", "registrar venta"]):
            return "venta"
        if any(x in msg for x in ["compra", "compras", "gasto",
                                   "es una compra", "registrar compra"]):
            return "compra"
        op = (estado_actual.get("operacion") or "").strip().lower()
        return op if op else None

    @staticmethod
    def _construir_payload(propuesta: dict, estado_actual: dict, contexto_previo: str | None) -> dict:
        productos_raw = propuesta.get("productos") or propuesta.get("productos_json") or []
        productos_str = productos_a_str(productos_raw)

        def obtener(campo_nuevo, campo_viejo=None, default=None):
            nuevo = propuesta.get(campo_nuevo)
            viejo = estado_actual.get(campo_nuevo)
            if campo_viejo and nuevo in [None, "", 0, "null"]:
                nuevo = propuesta.get(campo_viejo)
            if nuevo not in [None, "", 0, "null"]:
                return nuevo
            if campo_viejo and viejo in [None, "", 0, "null"]:
                viejo = estado_actual.get(campo_viejo)
            return viejo if viejo not in [None, "", 0, "null"] else default

        medio_pago = obtener("medio_pago", "tipo_operacion", None)
        if medio_pago and str(medio_pago).strip().lower() not in ("contado", "credito"):
            medio_pago = None
        elif medio_pago:
            medio_pago = str(medio_pago).strip().lower()

        dias_credito_raw = propuesta.get("dias_credito") or estado_actual.get("dias_credito")
        dias_credito = None
        if dias_credito_raw is not None and str(dias_credito_raw).strip() != "":
            try:
                dias_credito = int(float(dias_credito_raw))
            except (TypeError, ValueError):
                pass

        nro_cuotas_raw = propuesta.get("nro_cuotas") or estado_actual.get("nro_cuotas")
        nro_cuotas = None
        if nro_cuotas_raw is not None and str(nro_cuotas_raw).strip() != "":
            try:
                nro_cuotas = int(float(nro_cuotas_raw))
            except (TypeError, ValueError):
                pass

        entidad_numero = obtener("entidad_numero", "entidad_numero_documento", "")
        if not (entidad_numero and str(entidad_numero).strip()):
            for key in ("ruc", "dni", "documento"):
                v = propuesta.get(key)
                if v is not None and str(v).strip():
                    entidad_numero = str(v).strip()
                    break
        return {
            "operacion": contexto_previo if contexto_previo else obtener("operacion", "cod_ope", None),
            "entidad_nombre": obtener("entidad_nombre", default=""),
            "entidad_numero": entidad_numero or "",
            "tipo_documento": obtener("tipo_documento", default=None),
            "numero_documento": obtener("numero_documento", default=None),
            "moneda": obtener("moneda", default=None),
            "medio_pago": medio_pago,
            "dias_credito": dias_credito,
            "nro_cuotas": nro_cuotas,
            "monto_total": float(propuesta.get("monto_total") or estado_actual.get("monto_total") or 0),
            "monto_sin_igv": float(propuesta.get("monto_sin_igv") or estado_actual.get("monto_sin_igv") or estado_actual.get("monto_base") or 0),
            "igv": float(propuesta.get("igv") or estado_actual.get("igv") or estado_actual.get("monto_impuesto") or 0),
            "productos": productos_str,
            "fecha_emision": obtener("fecha_emision", default=None),
            "fecha_pago": obtener("fecha_pago", default=None),
        }
