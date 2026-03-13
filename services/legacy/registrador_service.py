"""DEPRECATED: Reemplazado por services.extraccion_service.ExtraccionService (flujo unificado sin metadata_ia)."""

from __future__ import annotations

import json
import re

from config.estados import PENDIENTE_DATOS, PENDIENTE_IDENTIFICACION
from repositories.base import CacheRepository
from services.identificador_service import IdentificadorService

CAMPOS_IDENTIFICABLES = ["entidad_numero_documento", "entidad_nombre"]


def _safe_str(val) -> str:
    """Convierte a string de forma segura; si es dict/list retorna ''."""
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return ""
    return str(val).strip()


class RegistradorService:
    def __init__(self, repo: CacheRepository, identificador: IdentificadorService | None = None) -> None:
        self._repo = repo
        self._identificador = identificador

    def ejecutar(self, wa_id: str, id_from: int) -> dict:
        try:
            registro_pendiente = self._repo.consultar(wa_id, id_from)

            if not registro_pendiente:
                return {"status": "error", "mensaje": "No hay una propuesta pendiente para confirmar."}

            # --- 1. Leer metadata_ia (puede venir como str o dict) ---
            metadata_ia = self._parsear_metadata(registro_pendiente.get("metadata_ia"))

            dato_registrado = metadata_ia.get("dato_registrado") or {}
            dato_identificado = metadata_ia.get("dato_identificado") or {}
            if not isinstance(dato_registrado, dict):
                dato_registrado = {}
            if not isinstance(dato_identificado, dict):
                dato_identificado = {}

            payload_analizado = {**dato_registrado, **dato_identificado}

            cod_ope_metadata = self._extraer_cod_ope(dato_registrado, dato_identificado, metadata_ia)
            if cod_ope_metadata in ("ventas", "compras"):
                payload_analizado["cod_ope"] = cod_ope_metadata

            if not payload_analizado and registro_pendiente:
                payload_analizado = self._fallback_desde_registro(registro_pendiente)

            ultima_pregunta_antes = (registro_pendiente.get("ultima_pregunta") or "").strip()
            estado_flujo_antes = (metadata_ia.get("estado_flujo") or "").strip()
            venia_de_identificacion = (
                estado_flujo_antes == PENDIENTE_IDENTIFICACION
                or "IDENTIFICACION PENDIENTE" in (ultima_pregunta_antes or "").upper()
            )
            venia_de_pendiente_datos = (
                estado_flujo_antes == PENDIENTE_DATOS
                or "pendiente datos" in (ultima_pregunta_antes or "").lower()
            )

            cod_ope_tabla = _safe_str(registro_pendiente.get("cod_ope")).lower()
            cod_ope_meta = _safe_str(payload_analizado.get("cod_ope")).lower()
            cod_ope_final = (
                cod_ope_meta
                if cod_ope_meta in ("ventas", "compras")
                else cod_ope_tabla
                if cod_ope_tabla in ("ventas", "compras")
                else "ventas"
            )

            productos = payload_analizado.get("productos_json", [])
            productos_str = (
                json.dumps(productos, ensure_ascii=False)
                if isinstance(productos, list)
                else (productos or "[]")
            )

            payload_db = {
                "cod_ope": cod_ope_final,
                "entidad_nombre": _safe_str(payload_analizado.get("entidad_nombre")),
                "entidad_numero_documento": _safe_str(
                    payload_analizado.get("entidad_numero_documento")
                ),
                "entidad_id_tipo_documento": payload_analizado.get("entidad_id_tipo_documento"),
                "id_moneda": payload_analizado.get("id_moneda"),
                "id_comprobante_tipo": payload_analizado.get("id_comprobante_tipo"),
                "tipo_operacion": _safe_str(payload_analizado.get("tipo_operacion")) or None,
                "monto_total": float(payload_analizado.get("monto_total") or 0),
                "monto_base": float(payload_analizado.get("monto_base") or 0),
                "monto_impuesto": float(payload_analizado.get("monto_impuesto") or 0),
                "productos_json": productos_str,
                "paso_actual": 3,
                "is_ready": 1,
                "ultima_pregunta": "CONFIRMADO",
                "metadata_ia": json.dumps(
                    {"dato_registrado": {}, "dato_identificado": {}, "estado_flujo": PENDIENTE_DATOS},
                    ensure_ascii=False,
                ),
            }
            for key in ("persona_id", "cliente_id", "proveedor_id", "entidad_id_maestro"):
                if payload_analizado.get(key) is not None:
                    payload_db[key] = payload_analizado[key]

            res_json = self._repo.actualizar(wa_id, id_from, payload_db)

            if not res_json.get("success"):
                return {"status": "error", "detalle": res_json.get("error", "Error desconocido en DB")}

            datos_registrados = {
                "cod_ope": cod_ope_final,
                "entidad_nombre": payload_analizado.get("entidad_nombre"),
                "entidad_numero_documento": payload_analizado.get("entidad_numero_documento"),
                "entidad_id_tipo_documento": payload_analizado.get("entidad_id_tipo_documento"),
                "monto_total": payload_analizado.get("monto_total"),
                "monto_base": payload_analizado.get("monto_base"),
                "monto_impuesto": payload_analizado.get("monto_impuesto"),
                "productos_json": productos,
                "id_comprobante_tipo": payload_analizado.get("id_comprobante_tipo"),
                "tipo_operacion": payload_analizado.get("tipo_operacion"),
                "id_moneda": payload_analizado.get("id_moneda"),
            }

            out: dict = {
                "status": "exito",
                "mensaje": "Operación registrada correctamente.",
                "db_res": res_json,
                "datos_registrados": datos_registrados,
            }

            tiene_id = (
                payload_analizado.get("entidad_id_maestro")
                or payload_analizado.get("cliente_id")
                or payload_analizado.get("proveedor_id")
            )
            tiene_entidad_en_metadata = self._tiene_dato_identificable(payload_analizado)
            cuando_pendiente_datos_solo_si_entidad = (
                not venia_de_pendiente_datos or tiene_entidad_en_metadata
            )
            if (
                self._identificador
                and not tiene_id
                and cod_ope_final in ("ventas", "compras")
                and tiene_entidad_en_metadata
                and not venia_de_identificacion
                and cuando_pendiente_datos_solo_si_entidad
            ):
                termino = self._termino_identificable(payload_analizado)
                salida_id = self._identificador.ejecutar(wa_id, cod_ope_final, termino, id_from)
                out["salida_identificador"] = salida_id
                if salida_id.get("identificado") and salida_id.get("resumen_confirmacion"):
                    out["texto_para_preguntador"] = salida_id["resumen_confirmacion"]

            return out

        except Exception as e:
            return {"status": "error", "mensaje": str(e)}

    @staticmethod
    def _parsear_metadata(raw) -> dict:
        """Parsea metadata_ia independientemente de si llega como str o dict."""
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

    def _termino_identificable(self, payload: dict) -> str:
        for key in CAMPOS_IDENTIFICABLES:
            val = _safe_str(payload.get(key))
            if val:
                return val
        return ""

    def _tiene_dato_identificable(self, payload: dict) -> bool:
        return bool(self._termino_identificable(payload))

    @staticmethod
    def _extraer_cod_ope(dato_registrado: dict, dato_identificado: dict, metadata_ia: dict) -> str | None:
        def _from_dict(d: dict) -> str | None:
            if not isinstance(d, dict):
                return None
            v = next((d[k] for k in d if str(k).lower() == "cod_ope"), None)
            if v is not None and _safe_str(v).lower() in ("ventas", "compras"):
                return _safe_str(v).lower()
            return None

        resultado = _from_dict(dato_registrado) or _from_dict(dato_identificado)
        if not resultado:
            raw_fallback = json.dumps(metadata_ia, ensure_ascii=False) if metadata_ia else ""
            if "ventas" in raw_fallback.lower() or "compras" in raw_fallback.lower():
                m = re.search(r'"cod_ope\"\\s*:\\s*\"(ventas|compras)\"', raw_fallback, re.I)
                if m:
                    resultado = m.group(1).lower()
        return resultado

    @staticmethod
    def _fallback_desde_registro(registro: dict) -> dict:
        prod = registro.get("productos_json")
        if isinstance(prod, str):
            try:
                prod = json.loads(prod) if prod.strip() else []
            except Exception:
                prod = []
        data = {
            "cod_ope": registro.get("cod_ope"),
            "entidad_nombre": registro.get("entidad_nombre"),
            "entidad_numero_documento": registro.get("entidad_numero_documento"),
            "entidad_id_tipo_documento": registro.get("entidad_id_tipo_documento"),
            "id_moneda": registro.get("id_moneda"),
            "id_comprobante_tipo": registro.get("id_comprobante_tipo"),
            "tipo_operacion": registro.get("tipo_operacion"),
            "monto_total": registro.get("monto_total"),
            "monto_base": registro.get("monto_base"),
            "monto_impuesto": registro.get("monto_impuesto"),
            "productos_json": prod,
            "persona_id": registro.get("persona_id"),
            "cliente_id": registro.get("cliente_id"),
            "proveedor_id": registro.get("proveedor_id"),
            "entidad_id_maestro": registro.get("entidad_id_maestro"),
        }
        return {k: v for k, v in data.items() if v is not None and v != ""}

