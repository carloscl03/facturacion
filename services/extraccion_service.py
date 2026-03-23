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
        self._preservar_campos_opciones_y_catalogo(estado_actual, payload_db)

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
            nombre_para_registro = (
                payload_db.get("entidad_nombre")
                or payload_base.get("entidad_nombre")
                or estado_actual.get("entidad_nombre")
                or None
            )
            salida_identificador = self._identificador.buscar_o_crear(
                tipo_busqueda,
                requiere_identificacion["termino"],
                id_from,
                nombre_entidad=nombre_para_registro,
            )
            if salida_identificador and salida_identificador.get("identificado"):
                campos_entidad = salida_identificador.get("campos_entidad") or {}
                # Guardar de inmediato en campos oficiales de Redis (sin variable intermedia ni confirmación)
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
            elif salida_identificador and not salida_identificador.get("identificado"):
                # No encontrado: el mensaje del identificador se mostrará al usuario (más abajo)
                pass

        # --- Calcular estado (una sola asignación; no sobrescribir estado 4) ---
        estado_calculado = calcular_estado(payload_db)
        # Estado 4 solo lo pone confirmar_registro; extracción no debe pisarlo
        if estado_actual.get("estado") == 4:
            estado = 4
        else:
            estado = estado_calculado
        payload_db["estado"] = estado

        # --- Si el identificador no encontró al proveedor/cliente, mostrar su mensaje (¿DNI/RUC correcto?) ---
        texto_completo = resumen_visual
        if diagnostico:
            texto_completo = f"{resumen_visual}\n\n{diagnostico}".strip()
        linea_identificacion = ""
        # Si el identificador SÍ encontró el documento, preparar una línea corta
        # para que el usuario entienda claramente qué número quedó reconocido.
        if salida_identificador and salida_identificador.get("identificado"):
            campos_entidad = salida_identificador.get("campos_entidad") or {}
            doc_id = (
                campos_entidad.get("entidad_numero_documento")
                or campos_entidad.get("entidad_numero")
                or payload_db.get("entidad_numero")
                or ""
            )
            nombre_ent = (campos_entidad.get("entidad_nombre") or payload_db.get("entidad_nombre") or "").strip()
            doc_id = str(doc_id).strip()
            if doc_id and nombre_ent:
                linea_identificacion = f"✅ Documento de identidad reconocido: {doc_id} ({nombre_ent})."
            elif doc_id:
                linea_identificacion = f"✅ Documento de identidad reconocido: {doc_id}."
            elif nombre_ent:
                linea_identificacion = f"✅ Identidad reconocida: {nombre_ent}."
            else:
                linea_identificacion = "✅ Documento de identidad reconocido."
        msg_identificacion_no_encontrado = ""
        if salida_identificador and not salida_identificador.get("identificado"):
            msg_identificacion_no_encontrado = (salida_identificador.get("mensaje") or "").strip()

        # --- Validación: fecha_pago >= fecha_emision (si no cumple, preguntar revisión y no persistir fecha_pago inválida) ---
        diagnostico_fechas = self._validar_fechas_pago_emision(payload_db)
        if diagnostico_fechas:
            payload_db["fecha_pago"] = None
            texto_completo = f"{texto_completo}\n\n{diagnostico_fechas}".strip() if texto_completo else diagnostico_fechas
        if msg_identificacion_no_encontrado:
            texto_completo = (
                f"{texto_completo}\n\n{msg_identificacion_no_encontrado}".strip()
                if texto_completo else msg_identificacion_no_encontrado
            )
        if linea_identificacion:
            texto_completo = f"{texto_completo}\n\n{linea_identificacion}".strip() if texto_completo else linea_identificacion

        payload_db["ultima_pregunta"] = ultima_pregunta_keyword or "inicio"

        # --- Persistir ---
        db_res = self._repo.upsert(wa_id, id_from, payload_db, es_registro_nuevo)

        # --- Debug para el informador: resumen de estado en lenguaje útil ---
        _debug_extraccion = {
            "estado": estado,
            "listo_para_finalizar": listo_para_finalizar,
            "resumen": (resumen_visual or "").strip() or None,
            "que_falta": (diagnostico or "").strip() or None,
            "identificacion_no_encontrado": None,
            "aviso_fechas": None,
        }
        if salida_identificador and not salida_identificador.get("identificado"):
            _debug_extraccion["identificacion_no_encontrado"] = (
                (salida_identificador.get("mensaje") or "").strip() or "El documento indicado no se encontró en el sistema."
            )
        if diagnostico_fechas:
            _debug_extraccion["aviso_fechas"] = diagnostico_fechas
        if getattr(self._repo, "guardar_debug", None):
            self._repo.guardar_debug(wa_id, id_from, "extraccion", _debug_extraccion)

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
    def _parsear_fecha_ddmmyyyy(val: str | None) -> tuple[int, int, int] | None:
        """Convierte DD-MM-YYYY a (año, mes, día) o None si no es válida."""
        if not val or not isinstance(val, str):
            return None
        s = val.strip()
        if not s:
            return None
        partes = s.replace("-", " ").replace("/", " ").split()
        if len(partes) != 3:
            return None
        try:
            d, m, a = int(partes[0]), int(partes[1]), int(partes[2])
            if a < 100:
                a += 2000
            if 1 <= m <= 12 and 1 <= d <= 31 and 1900 <= a <= 2100:
                return (a, m, d)
        except (ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _validar_fechas_pago_emision(payload: dict) -> str | None:
        """Si fecha_pago < fecha_emision, devuelve mensaje para revisión; si no, None."""
        fe = payload.get("fecha_emision")
        fp = payload.get("fecha_pago")
        if not fe or not fp:
            return None
        pe = ExtraccionService._parsear_fecha_ddmmyyyy(fe)
        pp = ExtraccionService._parsear_fecha_ddmmyyyy(fp)
        if not pe or not pp:
            return None
        if pp < pe:
            return "⚠️ La fecha de pago no puede ser anterior a la fecha de emisión. ¿Puedes revisar las fechas e indicar la correcta?"
        return None

    @staticmethod
    def _preservar_campos_opciones_y_catalogo(estado_actual: dict, payload_db: dict) -> None:
        """Tras extracción, no borrar lo ya elegido en Estado 2 (forma/medio catálogo, sucursal, etc.)."""
        if not estado_actual:
            return
        passthrough = (
            "forma_pago",
            "id_forma_pago",
            "id_medio_pago",
            "id_sucursal",
            "sucursal",
            "centro_costo",
            "id_centro_costo",
            "id_metodo_pago",
            "nombre_medio_pago",
            "opciones_actuales",
        )
        for k in passthrough:
            if k not in payload_db and estado_actual.get(k) is not None:
                v = estado_actual.get(k)
                if ExtraccionService._es_valor_valido(v):
                    payload_db[k] = v
        mp = estado_actual.get("medio_pago")
        if mp is not None and str(mp).strip() != "":
            low = str(mp).strip().lower()
            if low not in ("contado", "credito") and "medio_pago" not in payload_db:
                payload_db["medio_pago"] = mp

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

        # Contado/crédito → metodo_pago (extractor). Legado: medio_pago o tipo_operacion en propuesta/estado.
        metodo_raw = obtener("metodo_pago", None, None)
        if metodo_raw in [None, "", 0, "null"]:
            metodo_raw = propuesta.get("medio_pago")
        if metodo_raw in [None, "", 0, "null"]:
            metodo_raw = estado_actual.get("metodo_pago")
        if metodo_raw in [None, "", 0, "null"]:
            metodo_raw = obtener("medio_pago", "tipo_operacion", None)
            if metodo_raw and str(metodo_raw).strip().lower() not in ("contado", "credito"):
                metodo_raw = None
        metodo_pago = None
        if metodo_raw not in [None, "", 0, "null"]:
            s = str(metodo_raw).strip().lower()
            if s in ("contado", "credito"):
                metodo_pago = s

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
                nro_cuotas = max(1, min(24, nro_cuotas))
            except (TypeError, ValueError):
                pass

        entidad_numero = obtener("entidad_numero", "entidad_numero_documento", "")
        if not (entidad_numero and str(entidad_numero).strip()):
            for key in ("ruc", "dni", "documento"):
                v = propuesta.get(key)
                if v is not None and str(v).strip():
                    entidad_numero = str(v).strip()
                    break
        tipo_doc_raw = str(
            propuesta.get("tipo_documento")
            or estado_actual.get("tipo_documento")
            or ""
        ).strip().lower()
        es_nota = tipo_doc_raw in ("nota de venta", "nota de compra")

        # --- IGV coherente (fallback determinístico) ---
        # Si el extractor/IA no llenó igv/base con exactitud, lo calculamos con IGV 18%.
        # Para notas (venta/compra), no se calcula IGV.
        monto_total = float(propuesta.get("monto_total") or estado_actual.get("monto_total") or 0)
        monto_sin_igv = float(
            propuesta.get("monto_sin_igv")
            or estado_actual.get("monto_sin_igv")
            or estado_actual.get("monto_base")
            or 0
        )
        igv_val = float(
            propuesta.get("igv")
            or estado_actual.get("igv")
            or estado_actual.get("monto_impuesto")
            or 0
        )
        if es_nota:
            monto_sin_igv = 0.0
            igv_val = 0.0
        elif monto_total > 0:
            # Si faltó base, la inferimos desde monto_total.
            if monto_sin_igv == 0:
                monto_sin_igv = monto_total / 1.18
            # Si faltó IGV, la inferimos como diferencia.
            if igv_val == 0:
                igv_val = monto_total - monto_sin_igv

        monto_sin_igv = round(float(monto_sin_igv or 0), 2)
        igv_val = round(float(igv_val or 0), 2)

        return {
            "operacion": contexto_previo if contexto_previo else obtener("operacion", "cod_ope", None),
            "entidad_nombre": obtener("entidad_nombre", default=""),
            "entidad_numero": entidad_numero or "",
            "tipo_documento": obtener("tipo_documento", default=None),
            "numero_documento": obtener("numero_documento", default=None),
            "moneda": obtener("moneda", default=None),
            "metodo_pago": metodo_pago,
            "dias_credito": dias_credito,
            "nro_cuotas": nro_cuotas,
            "monto_total": round(float(monto_total or 0), 2),
            "monto_sin_igv": monto_sin_igv,
            # Compatibilidad histórica (el resto del sistema suele usar monto_impuesto / monto_base)
            "monto_base": monto_sin_igv,
            "monto_impuesto": igv_val,
            # Alias para componentes nuevos (venta_mapper/productos usan `igv`)
            "igv": igv_val,
            "productos": productos_str,
            "fecha_emision": obtener("fecha_emision", default=None),
            "fecha_pago": obtener("fecha_pago", default=None),
        }
