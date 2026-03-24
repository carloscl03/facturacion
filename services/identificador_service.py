from __future__ import annotations

from prompts.plantillas import formatear_ficha_identificacion
from repositories.base import CacheRepository
from repositories.entity_repository import EntityRepository


def _sin_nulos(d: dict) -> dict:
    if not isinstance(d, dict):
        return d
    return {
        k: v
        for k, v in d.items()
        if v is not None and v != "" and v != "null" and (not isinstance(v, str) or v.strip())
    }


def _solo_digitos(valor: str | None) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


class IdentificadorService:
    def __init__(self, cache_repo: CacheRepository, entity_repo: EntityRepository) -> None:
        self._cache = cache_repo
        self._entities = entity_repo

    # -------------------------------------------------------------- #
    # buscar(): solo lectura, NO toca cache ni metadata_ia.
    # Retorna IDs, ficha visual y campos para que el caller persista.
    # -------------------------------------------------------------- #
    def buscar(self, tipo_ope: str, termino: str, id_from: int) -> dict:
        try:
            data_cli = self._entities.buscar_cliente(id_from, termino)
            data_prov = self._entities.buscar_proveedor(id_from, termino)

            if not data_cli and not data_prov:
                rol = "cliente" if (tipo_ope or "").lower() in ("ventas", "venta") else "proveedor"
                termino_limpio = "".join(c for c in str(termino or "") if c.isdigit())
                if len(termino_limpio) == 11:
                    mensaje = f"❌ Ese RUC no figura como {rol}. ¿Está bien digitado o me pasas el nombre para anotarlo?"
                elif len(termino_limpio) == 8:
                    mensaje = f"❌ Ese DNI no figura como {rol}. ¿Está bien digitado o me pasas el nombre para anotarlo?"
                else:
                    mensaje = f"❌ No está registrado como {rol}. Indícame nombre y documento para anotarlo."
                return {
                    "identificado": False,
                    "mensaje": mensaje,
                    "datos_identificados": None,
                    "campos_entidad": {},
                }

            base = data_prov if (tipo_ope == "compras" and data_prov) else (data_cli if data_cli else data_prov)

            def clean(val):
                return str(val).strip() if val and str(val).strip() not in ["None", "null", ""] else "_No registrado_"

            # Nombre: para proveedor persona natural viene nombres + apellidos; para cliente/jurídico razon_social o nombre_completo
            def _nombre_entidad_desde_base(b: dict) -> str:
                rs = (b.get("razon_social") or "").strip()
                if rs:
                    return clean(rs)
                nc = (b.get("nombre_completo") or "").strip()
                if nc:
                    return clean(nc)
                partes = [
                    (b.get("nombres") or "").strip(),
                    (b.get("apellido_paterno") or "").strip(),
                    (b.get("apellido_materno") or "").strip(),
                ]
                nombre_armado = " ".join(p for p in partes if p)
                return clean(nombre_armado) if nombre_armado else "_No registrado_"

            nombre_entidad = _nombre_entidad_desde_base(base)
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

            tipo_ope_norm = (tipo_ope or "").lower().strip()
            p_id = (data_cli or data_prov).get("persona_id")
            c_id = data_cli.get("cliente_id") if data_cli else None
            pr_id = data_prov.get("proveedor_id") if data_prov else None
            es_compra = tipo_ope_norm in ("compras", "compra")
            es_venta = tipo_ope_norm in ("ventas", "venta")
            entidad_id_maestro = (
                (c_id if es_venta else None)
                or (pr_id if es_compra else None)
                or p_id
            )

            doc_raw = base.get("ruc") or base.get("numero_documento") or ""
            entidad_id_tipo_documento = 6 if len(str(doc_raw).strip()) == 11 else 1
            # Nombre para Redis: mismo que nombre_entidad (ya construido para persona natural / jurídica)
            nombre_entidad_limpio = nombre_entidad if nombre_entidad != "_No registrado_" else None
            doc_limpio = (doc_raw and str(doc_raw).strip()) or None
            if doc_limpio is None and doc_identidad != "_No registrado_":
                doc_limpio = doc_identidad

            campos_entidad = _sin_nulos({
                "entidad_nombre": nombre_entidad_limpio,
                "entidad_numero": doc_limpio,
                "entidad_id": entidad_id_maestro,
                "identificado": True,
                "persona_id": p_id,
                "cliente_id": c_id,
                "proveedor_id": pr_id,
            })

            return {
                "identificado": True,
                "mensaje": mensaje_bot,
                "datos_identificados": {
                    "nombre_entidad": nombre_entidad,
                    "doc_identidad": doc_identidad,
                    "tipo_doc_txt": tipo_doc_txt,
                    "comercial": comercial,
                    "correo": correo_ent,
                    "telefono": telf_ent,
                    "direccion": dir_ent,
                    "rol_txt": rol_txt,
                    "tipo_ope": tipo_ope,
                },
                "campos_entidad": campos_entidad,
            }

        except Exception as e:
            return {
                "identificado": False,
                "mensaje": f"💥 Error técnico: {e}",
                "datos_identificados": None,
                "campos_entidad": {},
            }

    def buscar_o_crear(self, tipo_ope: str, termino: str, id_from: int, nombre_entidad: str | None = None) -> dict:
        """
        Bifurcación según tipo de operación:

        COMPRA → flujo proveedor:
            1. Busca en API de proveedores.
            2. Si existe  → "Proveedor encontrado" + proveedor_id.
            3. Si no existe → registra como proveedor → "Proveedor registrado" + nuevo proveedor_id.

        VENTA → flujo cliente (idéntico pero con API de clientes):
            1. Busca en API de clientes.
            2. Si existe  → "Cliente encontrado" + cliente_id.
            3. Si no existe → registra como cliente → "Cliente registrado" + nuevo cliente_id.
        """
        tipo_norm = (tipo_ope or "").lower().strip()
        es_compra = tipo_norm in ("compra", "compras")
        es_venta  = tipo_norm in ("venta", "ventas")

        if not es_compra and not es_venta:
            return {
                "identificado": False,
                "created": False,
                "mensaje": "Tipo de operación no reconocido (debe ser compra o venta).",
                "datos_identificados": None,
                "campos_entidad": {},
            }

        termino_doc = _solo_digitos(termino)
        nombre_limpio = (nombre_entidad or "").strip() or f"Entidad {termino_doc[-4:]}" if termino_doc else "Sin nombre"

        # ── COMPRA: flujo proveedor ──────────────────────────────────────
        if es_compra:
            proveedor = self._entities.buscar_proveedor(id_from, termino)
            if proveedor:
                pr_id  = proveedor.get("proveedor_id")
                p_id   = proveedor.get("persona_id")
                nombre = (proveedor.get("razon_social") or proveedor.get("nombres") or nombre_limpio).strip()
                doc    = (proveedor.get("ruc") or proveedor.get("numero_documento") or termino_doc).strip()
                return {
                    "identificado": True,
                    "created": False,
                    "mensaje": f"✅ Proveedor encontrado: {nombre} ({doc}).",
                    "datos_identificados": {"nombre_entidad": nombre, "doc_identidad": doc, "rol_txt": "Proveedor", "tipo_ope": tipo_ope},
                    "campos_entidad": _sin_nulos({
                        "entidad_nombre": nombre,
                        "entidad_numero": doc,
                        "entidad_id": pr_id or p_id,
                        "identificado": True,
                        "persona_id": p_id,
                        "proveedor_id": pr_id,
                    }),
                }

            # No existe → registrar
            if len(termino_doc) not in (8, 11):
                return {
                    "identificado": False,
                    "created": False,
                    "mensaje": "❌ El número indicado no corresponde a un DNI (8 dígitos) ni a un RUC (11 dígitos). ¿Puedes verificar el documento?",
                    "datos_identificados": None,
                    "campos_entidad": {},
                }
            alta = self._entities.registrar_proveedor(
                {"entidad_nombre": nombre_limpio, "entidad_numero": termino_doc}, id_from
            )
            if not alta.get("success"):
                err = alta.get("message") or alta.get("error") or "Error al registrar"
                return {
                    "identificado": False,
                    "created": False,
                    "mensaje": f"❌ No pude registrar el proveedor: {err}",
                    "datos_identificados": None,
                    "campos_entidad": {},
                }
            pr_id = alta.get("proveedor_id")
            p_id  = alta.get("persona_id")
            return {
                "identificado": True,
                "created": True,
                "mensaje": f"✅ Proveedor registrado: {nombre_limpio} ({termino_doc}).",
                "datos_identificados": {"nombre_entidad": nombre_limpio, "doc_identidad": termino_doc, "rol_txt": "Proveedor", "tipo_ope": tipo_ope},
                "campos_entidad": _sin_nulos({
                    "entidad_nombre": nombre_limpio,
                    "entidad_numero": termino_doc,
                    "entidad_id": pr_id or p_id,
                    "identificado": True,
                    "persona_id": p_id,
                    "proveedor_id": pr_id,
                }),
            }

        # ── VENTA: flujo cliente ─────────────────────────────────────────
        cliente = self._entities.buscar_cliente(id_from, termino)
        if cliente:
            c_id   = cliente.get("cliente_id")
            p_id   = cliente.get("persona_id")
            nombre = (cliente.get("razon_social") or cliente.get("nombre_completo") or cliente.get("nombres") or nombre_limpio).strip()
            doc    = (cliente.get("ruc") or cliente.get("numero_documento") or termino_doc).strip()
            return {
                "identificado": True,
                "created": False,
                "mensaje": f"✅ Cliente encontrado: {nombre} ({doc}).",
                "datos_identificados": {"nombre_entidad": nombre, "doc_identidad": doc, "rol_txt": "Cliente", "tipo_ope": tipo_ope},
                "campos_entidad": _sin_nulos({
                    "entidad_nombre": nombre,
                    "entidad_numero": doc,
                    "entidad_id": c_id or p_id,
                    "identificado": True,
                    "persona_id": p_id,
                    "cliente_id": c_id,
                }),
            }

        # No existe → registrar
        if len(termino_doc) not in (8, 11):
            return {
                "identificado": False,
                "created": False,
                "mensaje": "❌ El número indicado no corresponde a un DNI (8 dígitos) ni a un RUC (11 dígitos). ¿Puedes verificar el documento?",
                "datos_identificados": None,
                "campos_entidad": {},
            }
        alta = self._entities.registrar_cliente(
            {"entidad_nombre": nombre_limpio, "entidad_numero": termino_doc}, id_from
        )
        if not alta.get("success"):
            err = alta.get("message") or alta.get("error") or "Error al registrar"
            return {
                "identificado": False,
                "created": False,
                "mensaje": f"❌ No pude registrar el cliente: {err}",
                "datos_identificados": None,
                "campos_entidad": {},
            }
        c_id = alta.get("cliente_id")
        p_id = alta.get("persona_id")
        return {
            "identificado": True,
            "created": True,
            "mensaje": f"✅ Cliente registrado: {nombre_limpio} ({termino_doc}).",
            "datos_identificados": {"nombre_entidad": nombre_limpio, "doc_identidad": termino_doc, "rol_txt": "Cliente", "tipo_ope": tipo_ope},
            "campos_entidad": _sin_nulos({
                "entidad_nombre": nombre_limpio,
                "entidad_numero": termino_doc,
                "entidad_id": c_id or p_id,
                "identificado": True,
                "persona_id": p_id,
                "cliente_id": c_id,
            }),
        }

    # -------------------------------------------------------------- #
    # ejecutar(): wrapper legacy que busca + persiste en cache.
    # Se mantiene por compatibilidad con rutas/servicios existentes.
    # -------------------------------------------------------------- #
    def ejecutar(self, wa_id: str, tipo_ope: str, termino: str, id_from: int) -> dict:
        resultado = self.buscar_o_crear(tipo_ope, termino, id_from)

        if not resultado.get("identificado"):
            return {
                "identificado": False,
                "mensaje": resultado.get("mensaje", ""),
                "resumen_confirmacion": resultado.get("mensaje", ""),
                "datos_identificados": None,
                "sugiere_llenar_sin_identificar": True,
            }

        campos = resultado.get("campos_entidad") or {}
        campos_cache: dict = {}
        for key in ("entidad_nombre", "entidad_numero", "entidad_id", "identificado"):
            val = campos.get(key)
            if val is not None and val != "" and (not isinstance(val, str) or val.strip()):
                campos_cache[key] = val

        if campos_cache:
            self._cache.actualizar(wa_id, id_from, campos_cache)

        return {
            "identificado": True,
            "mensaje": resultado["mensaje"],
            "resumen_confirmacion": resultado["mensaje"],
            "datos_identificados": resultado.get("datos_identificados"),
            "ids": {
                "p_id": campos.get("persona_id"),
                "c_id": campos.get("cliente_id"),
                "pr_id": campos.get("proveedor_id"),
            },
        }
