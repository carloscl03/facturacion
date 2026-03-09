import json

from config.estados import PENDIENTE_IDENTIFICACION
from prompts.plantillas import formatear_ficha_identificacion
from repositories.base import CacheRepository
from repositories.entity_repository import EntityRepository


def _sin_nulos(d: dict) -> dict:
    """Retorna un dict sin claves con valor None, vacío o 'null'."""
    if not isinstance(d, dict):
        return d
    return {
        k: v
        for k, v in d.items()
        if v is not None and v != "" and v != "null" and (not isinstance(v, str) or v.strip())
    }


def _parsear_metadata(raw) -> dict:
    """Parsea metadata_ia si llega como str o dict (API puede devolverlo ya parseado)."""
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


class IdentificadorService:
    def __init__(self, cache_repo: CacheRepository, entity_repo: EntityRepository) -> None:
        self._cache = cache_repo
        self._entities = entity_repo

    def ejecutar(self, wa_id: str, tipo_ope: str, termino: str, id_empresa: int) -> dict:
        try:
            data_cli = self._entities.buscar_cliente(id_empresa, termino)
            data_prov = self._entities.buscar_proveedor(id_empresa, termino)

            if not data_cli and not data_prov:
                rol = "cliente" if (tipo_ope or "").lower() == "ventas" else "proveedor"
                mensaje = (
                    f"❌ No encontré ese RUC/DNI o nombre en la base de {rol}es.\n\n"
                    f"Puedes *llenar el campo sin identificar*: indícame el **nombre o razón social** y el **número de documento** (RUC o DNI) "
                    f"y lo anotaré para continuar. Al finalizar la operación podré registrarlo si es necesario.\n\n"
                    f"Ejemplo: «Razón Social SAC, RUC 20123456789» o «Juan Pérez, DNI 12345678»."
                )
                return {
                    "identificado": False,
                    "mensaje": mensaje,
                    "resumen_confirmacion": mensaje,
                    "datos_identificados": None,
                    "sugiere_llenar_sin_identificar": True,
                }

            base = data_prov if (tipo_ope == "compras" and data_prov) else (data_cli if data_cli else data_prov)

            def clean(val):
                return str(val).strip() if val and str(val).strip() not in ["None", "null", ""] else "_No registrado_"

            nombre_entidad = clean(base.get("razon_social") or base.get("nombre_completo"))
            doc_identidad = clean(base.get("ruc") or base.get("numero_documento"))
            tipo_doc_txt = clean(
                base.get("tipo_documento_nombre")
                or ("RUC" if len(str(doc_identidad).replace("_No registrado_", "")) == 11 else "DNI")
            )
            correo_ent = clean(base.get("correo"))
            telf_ent = clean(base.get("telefono"))
            dir_ent = clean(base.get("direccion"))
            comercial = clean(base.get("nombre_comercial"))

            roles = []
            if data_cli:
                roles.append("Cliente")
            if data_prov:
                roles.append("Proveedor")
            rol_txt = " / ".join(roles)

            mensaje_bot = formatear_ficha_identificacion(
                nombre_entidad, doc_identidad, tipo_doc_txt, comercial,
                correo_ent, telf_ent, dir_ent, rol_txt, tipo_ope,
            )
            datos_identificados = {
                "nombre_entidad": nombre_entidad,
                "doc_identidad": doc_identidad,
                "tipo_doc_txt": tipo_doc_txt,
                "comercial": comercial,
                "correo": correo_ent,
                "telefono": telf_ent,
                "direccion": dir_ent,
                "rol_txt": rol_txt,
                "tipo_ope": tipo_ope,
            }

            tipo_ope_norm = (tipo_ope or "").lower().strip()
            p_id = (data_cli or data_prov).get("persona_id")
            c_id = data_cli.get("cliente_id") if data_cli else None
            pr_id = data_prov.get("proveedor_id") if data_prov else None
            entidad_id_maestro = (
                (c_id if tipo_ope_norm == "ventas" else None)
                or (pr_id if tipo_ope_norm == "compras" else None)
                or p_id
            )

            doc_raw = base.get("ruc") or base.get("numero_documento") or ""
            entidad_id_tipo_documento = 6 if len(str(doc_raw).strip()) == 11 else 1
            nombre_entidad_limpio = (base.get("razon_social") or base.get("nombre_completo") or "").strip() or None
            doc_limpio = (doc_raw and str(doc_raw).strip()) or None
            if nombre_entidad_limpio is None and nombre_entidad != "_No registrado_":
                nombre_entidad_limpio = nombre_entidad
            if doc_limpio is None and doc_identidad != "_No registrado_":
                doc_limpio = doc_identidad

            propuesta_identidad = _sin_nulos({
                "cod_ope": tipo_ope_norm or None,
                "entidad_nombre": nombre_entidad_limpio,
                "entidad_numero_documento": doc_limpio,
                "entidad_id_tipo_documento": entidad_id_tipo_documento,
                "entidad_id_maestro": entidad_id_maestro,
                "persona_id": p_id,
                "cliente_id": c_id,
                "proveedor_id": pr_id,
            })

            registro_actual = self._cache.consultar(wa_id, id_empresa) or {}
            metadata_ia = _parsear_metadata(registro_actual.get("metadata_ia"))

            dato_registrado = metadata_ia.get("dato_registrado") or {}
            if not dato_registrado and registro_actual:
                prod = registro_actual.get("productos_json")
                if isinstance(prod, str):
                    try:
                        prod = json.loads(prod) if (prod or "").strip() else []
                    except Exception:
                        prod = []
                else:
                    prod = prod if isinstance(prod, list) else []
                dato_registrado = _sin_nulos({
                    "cod_ope": registro_actual.get("cod_ope"),
                    "entidad_nombre": registro_actual.get("entidad_nombre"),
                    "entidad_numero_documento": registro_actual.get("entidad_numero_documento"),
                    "entidad_id_tipo_documento": registro_actual.get("entidad_id_tipo_documento"),
                    "id_moneda": registro_actual.get("id_moneda"),
                    "id_comprobante_tipo": registro_actual.get("id_comprobante_tipo"),
                    "tipo_operacion": registro_actual.get("tipo_operacion"),
                    "monto_total": registro_actual.get("monto_total"),
                    "monto_base": registro_actual.get("monto_base"),
                    "monto_impuesto": registro_actual.get("monto_impuesto"),
                    "productos_json": prod,
                })

            metadata_ia["dato_identificado"] = _sin_nulos(propuesta_identidad)
            metadata_ia["dato_registrado"] = dato_registrado
            metadata_ia["estado_flujo"] = PENDIENTE_IDENTIFICACION

            campos_cache = {"metadata_ia": json.dumps(metadata_ia, ensure_ascii=False), "ultima_pregunta": "IDENTIFICACION PENDIENTE"}
            for key in ("cod_ope", "entidad_nombre", "entidad_numero_documento", "entidad_id_tipo_documento",
                        "entidad_id_maestro", "persona_id", "cliente_id", "proveedor_id"):
                val = propuesta_identidad.get(key)
                if val is not None and val != "" and (not isinstance(val, str) or val.strip()):
                    campos_cache[key] = val

            self._cache.actualizar(wa_id, id_empresa, campos_cache)

            return {
                "identificado": True,
                "mensaje": mensaje_bot,
                "resumen_confirmacion": mensaje_bot,
                "datos_identificados": datos_identificados,
                "ids": {"p_id": p_id, "c_id": c_id, "pr_id": pr_id},
                "metadata_ia": metadata_ia,
            }

        except Exception as e:
            err = str(e)
            return {
                "identificado": False,
                "mensaje": f"💥 Error técnico: {err}",
                "resumen_confirmacion": f"💥 Error técnico: {err}",
                "datos_identificados": None,
            }
