"""DEPRECATED: Reemplazado por services/extraccion_service.py (flujo unificado sin metadata_ia)."""

import json

from config.estados import PENDIENTE_CONFIRMACION, PENDIENTE_TIPO_OPERACION
from prompts.analizador import build_prompt_analisis
from repositories.base import CacheRepository
from services.ai_service import AIService


def _parsear_metadata(raw) -> dict:
    """Parsea metadata_ia (str o dict) para pasarlo al prompt del analizador."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    raw_str = str(raw).strip()
    if not raw_str:
        return {}
    try:
        parsed = json.loads(raw_str)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _sin_nulos(d: dict) -> dict:
    if not isinstance(d, dict):
        return d
    return {
        k: v
        for k, v in d.items()
        if v is not None and v != "" and v != "null" and (not isinstance(v, str) or v.strip())
    }


class AnalizadorService:
    def __init__(
        self,
        repo: CacheRepository,
        ai: AIService,
        informacion_repo=None,
    ) -> None:
        self._repo = repo
        self._ai = ai
        self._informacion_repo = informacion_repo

    def ejecutar(self, wa_id: str, mensaje: str, id_from: int) -> dict:
        lista = self._repo.consultar_lista(wa_id, id_from)
        estado_actual = lista[0] if lista else {}
        es_registro_nuevo = len(lista) == 0

        # cod_ope para escritura: solo el que ya tiene el registro (inspirado en unificado).
        # Si es nuevo, lo fijamos después desde la IA; si ya existe, usamos el de BD.
        cod_ope_para_escribir = (estado_actual.get("cod_ope") or "").strip().lower()
        if cod_ope_para_escribir not in ("ventas", "compras"):
            cod_ope_para_escribir = None

        contexto_previo = self._detectar_contexto(mensaje, estado_actual)
        ultima_pregunta_enviada = estado_actual.get("ultima_pregunta") or ""
        if len(ultima_pregunta_enviada) > 800:
            ultima_pregunta_enviada = ultima_pregunta_enviada[:800] + "..."

        metadata_ia = _parsear_metadata(estado_actual.get("metadata_ia"))

        lista_sucursales = []
        if self._informacion_repo:
            try:
                lista_sucursales = self._informacion_repo.obtener_sucursales_publicas(id_from)
            except Exception:
                pass

        prompt = build_prompt_analisis(
            ultima_pregunta_enviada,
            mensaje,
            cod_ope_para_escribir,
            metadata_registro=metadata_ia,
            lista_sucursales=lista_sucursales if lista_sucursales else None,
        )

        try:
            output_ia = self._ai.completar_json(prompt)
            propuesta = output_ia.get("propuesta_cache", {})
            mensaje_entendimiento = (output_ia.get("mensaje_entendimiento") or "").strip()
            resumen_visual = output_ia.get("resumen_visual", "")
            if mensaje_entendimiento:
                resumen_visual = f"{mensaje_entendimiento}\n\n{resumen_visual}".strip()

            req_id = output_ia.get("requiere_identificacion") or {}
            requiere_identificacion = {
                "activo": bool(req_id.get("activo")),
                "termino": (req_id.get("termino") or "").strip(),
                "tipo_ope": req_id.get("tipo_ope") or contexto_previo,
                "mensaje": (req_id.get("mensaje") or "").strip(),
            }
            if requiere_identificacion["activo"] and not requiere_identificacion["termino"]:
                requiere_identificacion["activo"] = False

            payload_base = self._construir_payload(propuesta, estado_actual, contexto_previo)

            def es_valor_no_nulo(v):
                if v is None:
                    return False
                if isinstance(v, str) and v.strip() == "":
                    return False
                if v == "null":
                    return False
                return True

            payload_db = {k: v for k, v in payload_base.items() if es_valor_no_nulo(v)}

            # Regla de cod_ope (como en unificado: un solo criterio para lo que se escribe).
            # Solo escribir cod_ope si el registro ya lo tenía; si es nuevo, usar el que devolvió la IA.
            if cod_ope_para_escribir:
                payload_db["cod_ope"] = cod_ope_para_escribir
            elif es_registro_nuevo and payload_base.get("cod_ope"):
                payload_db["cod_ope"] = str(payload_base["cod_ope"]).strip().lower()
            else:
                payload_db.pop("cod_ope", None)

            metadata_ia = self._construir_metadata(
                propuesta, estado_actual, payload_base, cod_ope_para_escribir
            )
            payload_db["metadata_ia"] = json.dumps(metadata_ia, ensure_ascii=False)

            # ultima_pregunta = lo que el usuario vio (estado REGISTRADO): resumen + pregunta de confirmación
            texto_registrado = (resumen_visual or "¿Los datos son correctos? Indique si desea confirmar o modificar algo.").strip()
            payload_db["ultima_pregunta"] = texto_registrado
            payload_db["paso_actual"] = 2
            payload_db["is_ready"] = 0

            db_res = self._repo.upsert(wa_id, id_from, payload_db, es_registro_nuevo)

            out = {
                "status": "analizado_y_guardado",
                "db_res": db_res,
                "whatsapp_output": {"texto": resumen_visual},
                "requiere_identificacion": requiere_identificacion,
            }
            if requiere_identificacion["activo"]:
                out["datos_entidad"] = {
                    "termino": requiere_identificacion["termino"],
                    "tipo_ope": requiere_identificacion["tipo_ope"],
                    "mensaje": requiere_identificacion["mensaje"]
                    or f"Buscando '{requiere_identificacion['termino']}' en {'clientes' if requiere_identificacion['tipo_ope'] == 'ventas' else 'proveedores'}...",
                }
            return out

        except Exception as e:
            return {"status": "error", "detalle": str(e)}

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _detectar_contexto(self, mensaje: str, estado_actual: dict) -> str | None:
        mensaje_lower = (mensaje or "").lower().strip()
        if any(x in mensaje_lower for x in [" a venta", "a ventas", "cambiar a venta", "cambiarlo a venta", "cambiar a ventas", "pásalo a venta", "pásalo a ventas"]):
            return "ventas"
        if any(x in mensaje_lower for x in [" a compra", "a compras", "cambiar a compra", "cambiarlo a compra", "cambiar a compras", "pásalo a compra"]):
            return "compras"
        if any(x in mensaje_lower for x in ["venta", "ventas", "vender", "vendiendo", "es una venta", "registrar venta"]):
            return "ventas"
        if any(x in mensaje_lower for x in ["compra", "compras", "gasto", "es una compra", "registrar compra"]):
            return "compras"
        cod = (estado_actual.get("cod_ope") or "").strip().lower()
        return cod if cod else None

    def _construir_payload(self, propuesta: dict, estado_actual: dict, contexto_previo: str | None) -> dict:
        productos_str = json.dumps(propuesta.get("productos_json", []), ensure_ascii=False)

        def obtener_valor(campo, default=None):
            nuevo = propuesta.get(campo)
            viejo = estado_actual.get(campo)
            if nuevo not in [None, "", 0, "null"]:
                return nuevo
            return viejo if viejo not in [None, "", 0, "null"] else default

        return {
            "cod_ope": contexto_previo if contexto_previo else obtener_valor("cod_ope", None),
            "entidad_nombre": obtener_valor("entidad_nombre", ""),
            "entidad_numero_documento": obtener_valor("entidad_numero_documento", ""),
            "entidad_id_tipo_documento": propuesta.get("entidad_id_tipo_documento") or estado_actual.get("entidad_id_tipo_documento"),
            "id_moneda": obtener_valor("id_moneda", None),
            "id_comprobante_tipo": obtener_valor("id_comprobante_tipo", None),
            "tipo_operacion": obtener_valor("tipo_operacion", None),
            "monto_total": float(propuesta.get("monto_total") or estado_actual.get("monto_total") or 0),
            "monto_base": float(propuesta.get("monto_base") or estado_actual.get("monto_base") or 0),
            "monto_impuesto": float(propuesta.get("monto_impuesto") or estado_actual.get("monto_impuesto") or 0),
            "productos_json": productos_str,
            "id_sucursal": propuesta.get("id_sucursal") or estado_actual.get("id_sucursal"),
            "sucursal_nombre": obtener_valor("sucursal_nombre", "") or obtener_valor("sucursal", ""),
            "paso_actual": 2,
            "is_ready": 0,
        }

    def _construir_metadata(
        self,
        propuesta: dict,
        estado_actual: dict,
        payload_base: dict,
        cod_ope_para_escribir: str | None,
    ) -> dict:
        try:
            metadata_prev = json.loads(estado_actual.get("metadata_ia") or "{}")
            dato_identificado_existente = metadata_prev.get("dato_identificado") or {}
            dato_registrado_prev = metadata_prev.get("dato_registrado") or {}
        except Exception:
            dato_identificado_existente = {}
            dato_registrado_prev = {}

        productos_propuesta = propuesta.get("productos_json") or []
        tiene_productos_nuevos = isinstance(productos_propuesta, list) and len(productos_propuesta) > 0

        # Piso: columnas reales ya persistidas en BD (excluye cod_ope para no almacenarlo)
        prod_estado = estado_actual.get("productos_json")
        if isinstance(prod_estado, str):
            try:
                prod_estado = json.loads(prod_estado) if (prod_estado or "").strip() else []
            except Exception:
                prod_estado = []
        base_estado = _sin_nulos({
            "entidad_nombre": estado_actual.get("entidad_nombre"),
            "entidad_numero_documento": estado_actual.get("entidad_numero_documento"),
            "entidad_id_tipo_documento": estado_actual.get("entidad_id_tipo_documento"),
            "id_moneda": estado_actual.get("id_moneda"),
            "id_comprobante_tipo": estado_actual.get("id_comprobante_tipo"),
            "tipo_operacion": estado_actual.get("tipo_operacion"),
            "id_sucursal": estado_actual.get("id_sucursal"),
            "sucursal_nombre": estado_actual.get("sucursal_nombre") or estado_actual.get("sucursal"),
            **({"monto_total": estado_actual.get("monto_total")} if estado_actual.get("monto_total") and float(estado_actual.get("monto_total") or 0) > 0 else {}),
            **({"monto_base": estado_actual.get("monto_base")} if estado_actual.get("monto_base") and float(estado_actual.get("monto_base") or 0) > 0 else {}),
            **({"monto_impuesto": estado_actual.get("monto_impuesto")} if estado_actual.get("monto_impuesto") and float(estado_actual.get("monto_impuesto") or 0) > 0 else {}),
            **({"productos_json": prod_estado} if prod_estado else {}),
        })

        # Nuevos valores del mensaje actual: excluir cod_ope y excluir ceros (no sobreescribir datos reales)
        monto_total_nuevo = payload_base.get("monto_total")
        monto_base_nuevo = payload_base.get("monto_base")
        monto_impuesto_nuevo = payload_base.get("monto_impuesto")
        nuevo_parcial = _sin_nulos({
            "entidad_nombre": payload_base.get("entidad_nombre"),
            "entidad_numero_documento": payload_base.get("entidad_numero_documento"),
            "entidad_id_tipo_documento": payload_base.get("entidad_id_tipo_documento"),
            "id_moneda": payload_base.get("id_moneda"),
            "id_comprobante_tipo": payload_base.get("id_comprobante_tipo"),
            "tipo_operacion": payload_base.get("tipo_operacion"),
            "id_sucursal": payload_base.get("id_sucursal"),
            "sucursal_nombre": payload_base.get("sucursal_nombre"),
            **({"monto_total": monto_total_nuevo} if monto_total_nuevo and float(monto_total_nuevo) > 0 else {}),
            **({"monto_base": monto_base_nuevo} if monto_base_nuevo and float(monto_base_nuevo) > 0 else {}),
            **({"monto_impuesto": monto_impuesto_nuevo} if monto_impuesto_nuevo and float(monto_impuesto_nuevo) > 0 else {}),
            **({"productos_json": productos_propuesta} if tiene_productos_nuevos else {}),
        })

        # Fusión: BD → metadata previa → nuevos valores del mensaje (cada capa sobreescribe la anterior)
        dato_registrado = _sin_nulos({**base_estado, **dato_registrado_prev, **nuevo_parcial})

        # Escribir cod_ope en el JSON solo si el registro ya lo tenía (misma regla que el payload).
        if cod_ope_para_escribir:
            dato_registrado["cod_ope"] = cod_ope_para_escribir

        cod_ope_final = (dato_registrado.get("cod_ope") or "").strip().lower()
        if cod_ope_final not in ("ventas", "compras"):
            estado_flujo = PENDIENTE_TIPO_OPERACION
        else:
            estado_flujo = PENDIENTE_CONFIRMACION

        return {
            "dato_registrado": dato_registrado,
            "dato_identificado": dato_identificado_existente,
            "estado_flujo": estado_flujo,
        }
