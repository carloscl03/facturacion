import json
import re

from repositories.base import CacheRepository


class RegistradorService:
    def __init__(self, repo: CacheRepository) -> None:
        self._repo = repo

    def ejecutar(self, wa_id: str, id_empresa: int) -> dict:
        try:
            registro_pendiente = self._repo.consultar(wa_id, id_empresa)

            if not registro_pendiente:
                return {"status": "error", "mensaje": "No hay una propuesta pendiente para confirmar."}

            raw_metadata = (registro_pendiente.get("metadata_ia") or "{}").strip()
            metadata_ia = {}
            try:
                if raw_metadata:
                    metadata_ia = json.loads(raw_metadata)
            except Exception:
                pass

            def _norm(d):
                if not isinstance(d, dict):
                    return {}
                return {str(k).lower(): v for k, v in d.items()}

            meta_norm = _norm(metadata_ia)
            dato_registrado = meta_norm.get("dato_registrado") or metadata_ia.get("dato_registrado") or {}
            dato_identificado = meta_norm.get("dato_identificado") or metadata_ia.get("dato_identificado") or {}
            if not isinstance(dato_registrado, dict):
                dato_registrado = {}
            if not isinstance(dato_identificado, dict):
                dato_identificado = {}

            payload_analizado = {**dato_registrado, **dato_identificado}

            cod_ope_metadata = self._extraer_cod_ope(dato_registrado, dato_identificado, raw_metadata)
            if cod_ope_metadata in ("ventas", "compras"):
                payload_analizado["cod_ope"] = cod_ope_metadata

            if not payload_analizado and registro_pendiente:
                payload_analizado = self._fallback_desde_registro(registro_pendiente)

            cod_ope_tabla = (registro_pendiente.get("cod_ope") or "").strip().lower()
            cod_ope_meta = (payload_analizado.get("cod_ope") or "").strip().lower()
            cod_ope_final = (
                cod_ope_meta if cod_ope_meta in ("ventas", "compras")
                else cod_ope_tabla if cod_ope_tabla in ("ventas", "compras")
                else "ventas"
            )

            productos = payload_analizado.get("productos_json", [])
            productos_str = json.dumps(productos, ensure_ascii=False) if isinstance(productos, list) else (productos or "[]")

            payload_db = {
                "cod_ope": cod_ope_final,
                "entidad_nombre": payload_analizado.get("entidad_nombre", ""),
                "entidad_numero_documento": payload_analizado.get("entidad_numero_documento", ""),
                "entidad_id_tipo_documento": payload_analizado.get("entidad_id_tipo_documento"),
                "id_moneda": payload_analizado.get("id_moneda", 1),
                "id_comprobante_tipo": payload_analizado.get("id_comprobante_tipo", 2),
                "tipo_operacion": payload_analizado.get("tipo_operacion", "contado"),
                "monto_total": float(payload_analizado.get("monto_total", 0)),
                "monto_base": float(payload_analizado.get("monto_base", 0)),
                "monto_impuesto": float(payload_analizado.get("monto_impuesto", 0)),
                "productos_json": productos_str,
                "paso_actual": 3,
                "is_ready": 1,
                "ultima_pregunta": "CONFIRMADO",
                "metadata_ia": json.dumps({"dato_registrado": {}, "dato_identificado": {}}, ensure_ascii=False),
            }
            for key in ("persona_id", "cliente_id", "proveedor_id", "entidad_id_maestro"):
                if payload_analizado.get(key) is not None:
                    payload_db[key] = payload_analizado[key]

            res_json = self._repo.actualizar(wa_id, id_empresa, payload_db)

            if res_json.get("success"):
                return {
                    "status": "exito",
                    "mensaje": "✅ ¡Excelente! He registrado la operación correctamente.",
                    "db_res": res_json,
                }
            return {"status": "error", "detalle": res_json.get("error", "Error desconocido en DB")}

        except Exception as e:
            return {"status": "error", "mensaje": str(e)}

    def _extraer_cod_ope(self, dato_registrado: dict, dato_identificado: dict, raw_metadata: str) -> str | None:
        def _from_dict(d):
            if not isinstance(d, dict):
                return None
            v = next((d[k] for k in d if str(k).lower() == "cod_ope"), None)
            if v is not None and str(v).strip().lower() in ("ventas", "compras"):
                return str(v).strip().lower()
            return None

        resultado = _from_dict(dato_registrado) or _from_dict(dato_identificado)
        if not resultado and raw_metadata and ("ventas" in raw_metadata.lower() or "compras" in raw_metadata.lower()):
            m = re.search(r'"cod_ope"\s*:\s*"(ventas|compras)"', raw_metadata, re.I)
            if m:
                resultado = m.group(1).lower()
        return resultado

    def _fallback_desde_registro(self, registro: dict) -> dict:
        prod = registro.get("productos_json")
        if isinstance(prod, str):
            try:
                prod = json.loads(prod) if (prod or "").strip() else []
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
