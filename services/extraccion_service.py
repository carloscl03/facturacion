from __future__ import annotations

import json

from prompts.extraccion import build_prompt_extractor
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.helpers.productos import (
    build_payload_lista_productos,
    enriquecer_producto_con_catalogo,
    normalizar_productos_raw,
    productos_a_str,
)
from services.helpers.registro_domain import (
    calcular_estado,
    normalizar_documento_entidad,
    operacion_desde_registro,
)
from services.identificador_service import IdentificadorService
from services.whatsapp_sender import enviar_lista as _enviar_lista, enviar_texto as _enviar_texto


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

    def ejecutar(self, wa_id: str, mensaje: str, id_from: int, *, url: str | None = None, id_empresa: int | None = None, id_plataforma: int | None = None) -> dict:
        lista = self._repo.consultar_lista(wa_id, id_from)
        estado_actual = lista[0] if lista else {}
        es_registro_nuevo = len(lista) == 0

        # --- Resolver producto_pendiente si el usuario está seleccionando ---
        pendiente = self._resolver_producto_pendiente(estado_actual, mensaje, wa_id, id_from, id_empresa, id_plataforma)
        if pendiente is not None:
            return pendiente

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

        # Proteger tipo_documento ya definido: si Redis ya tiene uno y la IA propone otro
        # diferente sin que el usuario lo haya mencionado explícitamente, preservar el de Redis.
        tipo_doc_redis = (estado_actual.get("tipo_documento") or "").strip().lower()
        tipo_doc_propuesta = (propuesta.get("tipo_documento") or "").strip().lower()
        if tipo_doc_redis and tipo_doc_propuesta and tipo_doc_propuesta != tipo_doc_redis:
            # Solo aceptar el cambio si el usuario mencionó el nuevo tipo en el mensaje
            msg_lower = mensaje.lower()
            tipo_mencionado = any(t in msg_lower for t in (
                "factura", "boleta", "nota de venta", "nota de compra", "nota",
                "honorarios", "recibo por honorarios",
            ))
            if not tipo_mencionado:
                payload_db["tipo_documento"] = estado_actual["tipo_documento"]

        # Limpiar dias_credito y nro_cuotas si metodo_pago cambió a contado
        if payload_db.get("metodo_pago") == "contado":
            payload_db["dias_credito"] = ""
            payload_db["nro_cuotas"] = ""

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

        # --- Calcular estado (una sola asignación; no sobrescribir estado 4 ni 5) ---
        estado_calculado = calcular_estado(payload_db)
        # Estado 4 solo lo pone confirmar_registro; estado 5 solo lo pone clasificador (4→5). Extracción no debe pisarlos.
        if estado_actual.get("estado") in (4, 5):
            estado = estado_actual.get("estado")
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
            linea_identificacion = (salida_identificador.get("mensaje") or "✅ Documento de identidad reconocido.").strip()
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

        # --- URL opcional (persistente; solo se escribe si viene, nunca se borra) ---
        if url:
            payload_db["url"] = url
        elif estado_actual.get("url"):
            payload_db["url"] = estado_actual["url"]

        # --- Búsqueda en catálogo para productos extraídos ---
        catalogo_resultado = self._buscar_productos_en_catalogo(
            payload_db, estado_actual, id_from, wa_id,
            id_empresa, id_plataforma,
        )
        if catalogo_resultado is not None:
            # Hay producto_pendiente: se guardó en Redis y se envió lista WhatsApp.
            # Persistir primero el resto de datos y luego retornar.
            self._repo.upsert(wa_id, id_from, payload_db, es_registro_nuevo)
            return catalogo_resultado

        # Feedback visual: en las líneas de detalle (🔹), agregar ✅ y corregir precio
        # con los datos reales del catálogo (la IA genera el visual antes del enriquecimiento)
        payload_db.pop("_feedback_catalogo", None)
        productos_enriquecidos = normalizar_productos_raw(payload_db.get("productos"))
        for prod in productos_enriquecidos:
            if prod.get("id_catalogo") and texto_completo:
                nombre = (prod.get("nombre") or "").strip()
                precio = float(prod.get("precio_unitario") or prod.get("precio") or 0)
                if not nombre:
                    continue
                # Buscar líneas con el nombre del producto y reemplazar precio + agregar ✅
                lineas = texto_completo.split("\n")
                for idx, linea in enumerate(lineas):
                    if nombre.lower() in linea.lower() and ("Cant" in linea or "🔹" in linea):
                        # Reemplazar nombre sin check por nombre con check
                        if "✅" not in linea:
                            linea = linea.replace(nombre, f"{nombre} ✅")
                        # Corregir precio: buscar "— NUMERO" y reemplazar
                        for sep in ("—", "-", "–"):
                            if sep in linea:
                                partes = linea.rsplit(sep, 1)
                                if len(partes) == 2:
                                    linea = f"{partes[0].rstrip()}{sep} {precio}"
                                    break
                        lineas[idx] = linea
                texto_completo = "\n".join(lineas)

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

        # --- Enviar texto por WhatsApp directamente ---
        whatsapp_enviado = None
        if texto_completo and id_empresa is not None:
            ok, err = _enviar_texto(id_empresa, wa_id, texto_completo, id_plataforma)
            whatsapp_enviado = {"texto": ok, "texto_error": err}

        out: dict = {
            "status": "sincronizado",
            "estado": estado,
            "listo_para_finalizar": listo_para_finalizar,
            "cambiar_estado_a_4": cambiar_estado_a_4,
            "db_res": db_res,
            "whatsapp_output": {"texto": texto_completo},
            "requiere_identificacion": requiere_identificacion,
        }
        if whatsapp_enviado is not None:
            out["whatsapp_enviado"] = whatsapp_enviado
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
    # Catálogo de productos
    # ------------------------------------------------------------------ #

    def _resolver_producto_pendiente(
        self, estado_actual: dict, mensaje: str, wa_id: str, id_from: int,
        id_empresa: int | None, id_plataforma: int | None,
    ) -> dict | None:
        """
        Si hay producto_pendiente en Redis, intenta resolver la selección del usuario.
        - Si matchea un candidato: enriquece el producto, limpia pendiente, retorna None
          para que el flujo normal continúe (la IA generará resumen + preguntas).
        - Si no matchea: es un mensaje nuevo → limpiar pendiente y dejar que el flujo
          normal lo procese (podría ser otro producto, más datos, etc.).
        Retorna None siempre (nunca corta el flujo).
        """
        pendiente_raw = estado_actual.get("producto_pendiente")
        if not pendiente_raw:
            return None
        try:
            pendiente = json.loads(pendiente_raw) if isinstance(pendiente_raw, str) else pendiente_raw
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(pendiente, dict) or not pendiente.get("candidatos"):
            return None

        candidatos = pendiente["candidatos"]
        indice = pendiente.get("indice", 0)
        cantidad = float(pendiente.get("cantidad", 1))
        msg = mensaje.strip()
        msg_lower = msg.lower()

        print(f"[producto_pendiente] mensaje recibido: {repr(msg)}", flush=True)
        print(f"[producto_pendiente] candidatos: {[c.get('nombre') for c in candidatos]}", flush=True)

        # Estrategia de match (del más específico al más agresivo):
        seleccionado = None

        # 1. Id exacto (WhatsApp puede enviar el id de la fila)
        for c in candidatos:
            if str(c.get("id_catalogo")) == msg:
                seleccionado = c
                break

        # 2. Nombre del candidato dentro del mensaje (más largo primero)
        if not seleccionado:
            candidatos_ordenados = sorted(candidatos, key=lambda x: len(x.get("nombre") or ""), reverse=True)
            for c in candidatos_ordenados:
                nombre_c = (c.get("nombre") or "").strip().lower()
                if nombre_c and nombre_c in msg_lower:
                    seleccionado = c
                    break

        # 3. Alguna palabra significativa del mensaje coincide con un candidato
        if not seleccionado:
            palabras_msg = [p for p in msg_lower.split() if len(p) > 2 and not p.startswith("s/")]
            for c in candidatos:
                nombre_c = (c.get("nombre") or "").strip().lower()
                for palabra in palabras_msg:
                    if palabra in nombre_c:
                        seleccionado = c
                        break
                if seleccionado:
                    break

        if seleccionado:
            print(f"[producto_pendiente] match: {seleccionado.get('nombre')}", flush=True)
        else:
            print(f"[producto_pendiente] SIN match, limpiando pendiente", flush=True)
            # No matchea: limpiar pendiente y dejar que el flujo normal procese
            self._repo.actualizar(wa_id, id_from, {"producto_pendiente": ""})
            estado_actual.pop("producto_pendiente", None)
            return None

        # Enriquecer producto con datos del catálogo
        productos_actuales = normalizar_productos_raw(estado_actual.get("productos"))
        producto_base = productos_actuales[indice] if indice < len(productos_actuales) else {"cantidad": cantidad}
        producto_base["cantidad"] = cantidad
        producto_enriquecido = enriquecer_producto_con_catalogo(producto_base, seleccionado)

        if indice < len(productos_actuales):
            productos_actuales[indice] = producto_enriquecido
        else:
            productos_actuales.append(producto_enriquecido)

        # Recalcular monto_total desde productos
        monto_total = sum(float(p.get("total_item") or 0) for p in productos_actuales)

        # Persistir en Redis y actualizar estado_actual para que el flujo normal
        # vea los productos enriquecidos
        update = {
            "productos": productos_a_str(productos_actuales),
            "monto_total": round(monto_total, 2),
            "producto_pendiente": "",
        }
        self._repo.actualizar(wa_id, id_from, update)
        estado_actual["productos"] = update["productos"]
        estado_actual["monto_total"] = update["monto_total"]
        estado_actual.pop("producto_pendiente", None)

        # Retornar None para que el flujo normal continúe:
        # la IA generará resumen visual con el producto enriquecido + preguntas faltantes
        return None

    def _buscar_productos_en_catalogo(
        self, payload_db: dict, estado_actual: dict, id_from: int, wa_id: str,
        id_empresa: int | None, id_plataforma: int | None,
    ) -> dict | None:
        """
        Busca cada producto extraído en el catálogo.
        - Ya enriquecido (id_catalogo en estado_actual): copiar datos, no re-buscar.
        - 1 match: auto-fill y agrega línea de feedback a texto_completo.
        - N matches: guarda producto_pendiente y envía lista WhatsApp. Retorna dict.
        - 0 matches: no hace nada.
        Retorna dict si se envió lista (flujo interrumpido), None si no.
        """
        if not self._informacion_repo:
            return None

        productos_str = payload_db.get("productos")
        productos = normalizar_productos_raw(productos_str)
        if not productos:
            return None

        # Productos ya enriquecidos en estado_actual (por selección previa)
        productos_estado = normalizar_productos_raw(estado_actual.get("productos"))
        estado_por_nombre: dict[str, dict] = {}
        for p in productos_estado:
            if p.get("id_catalogo"):
                nombre_lower = (p.get("nombre") or "").strip().lower()
                if nombre_lower:
                    estado_por_nombre[nombre_lower] = p

        hubo_cambio = False
        lineas_feedback: list[str] = []
        for i, prod in enumerate(productos):
            if prod.get("id_catalogo"):
                continue
            nombre = (prod.get("nombre") or "").strip()
            if not nombre:
                continue

            # Si ya fue enriquecido en una selección anterior, reutilizar
            enriched = estado_por_nombre.get(nombre.lower())
            if enriched:
                productos[i] = enriquecer_producto_con_catalogo(prod, enriched)
                hubo_cambio = True
                continue

            candidatos = self._informacion_repo.buscar_catalogo(id_from, nombre)
            if not candidatos:
                continue

            if len(candidatos) == 1:
                productos[i] = enriquecer_producto_con_catalogo(prod, candidatos[0])
                hubo_cambio = True
                c = candidatos[0]
                lineas_feedback.append(f"✅ *{c['nombre']}* — S/ {c['precio_unitario']:.2f}")
            else:
                # Múltiples: guardar pendiente y enviar lista
                pendiente = {
                    "indice": i,
                    "cantidad": float(prod.get("cantidad", 1)),
                    "nombre_buscado": nombre,
                    "candidatos": candidatos,
                }
                payload_db["producto_pendiente"] = json.dumps(pendiente, ensure_ascii=False)
                payload_db["productos"] = productos_a_str(productos)

                if id_empresa is not None:
                    payload_lista = build_payload_lista_productos(
                        id_empresa, wa_id, id_plataforma or 6, candidatos, nombre,
                    )
                    _enviar_lista(payload_lista)

                return {
                    "status": "producto_pendiente",
                    "candidatos": candidatos,
                    "whatsapp_output": {"texto": f"Selecciona un producto de la lista."},
                }

        if hubo_cambio:
            payload_db["productos"] = productos_a_str(productos)
            # Recalcular monto_total si los productos cambiaron
            monto_total = sum(float(p.get("total_item") or 0) for p in productos)
            if monto_total > 0:
                payload_db["monto_total"] = round(monto_total, 2)
            # Guardar feedback para concatenar al texto_completo
            payload_db["_feedback_catalogo"] = "\n".join(lineas_feedback)

        return None

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
            "tipo_documento",
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
            "url",
            "observacion",
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
        # Productos: mergear nuevos (propuesta) con existentes (estado_actual).
        # Si la propuesta trae productos, son NUEVOS a agregar; los de Redis se preservan.
        productos_nuevos = propuesta.get("productos") or propuesta.get("productos_json") or None
        productos_existentes = normalizar_productos_raw(estado_actual.get("productos"))
        if productos_nuevos:
            nuevos = normalizar_productos_raw(productos_nuevos)
            # Agregar solo los que no estén ya (por nombre, case-insensitive)
            nombres_existentes = {(p.get("nombre") or "").strip().lower() for p in productos_existentes}
            for n in nuevos:
                nombre_n = (n.get("nombre") or "").strip().lower()
                if nombre_n and nombre_n not in nombres_existentes:
                    productos_existentes.append(n)
                elif nombre_n in nombres_existentes:
                    # Producto repetido: actualizar cantidad si cambió
                    for i, e in enumerate(productos_existentes):
                        if (e.get("nombre") or "").strip().lower() == nombre_n:
                            productos_existentes[i] = {**e, **{k: v for k, v in n.items() if v}}
                            break
        productos_str = productos_a_str(productos_existentes)

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

        # Si metodo_pago cambió a contado, limpiar dias_credito y nro_cuotas
        if metodo_pago == "contado":
            dias_credito = None
            nro_cuotas = None
        else:
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
        # Evitar que serie-número de comprobante (p. ej. EB01-4) quede como RUC/DNI de la entidad.
        entidad_numero = normalizar_documento_entidad(entidad_numero)
        tipo_doc_raw = str(
            propuesta.get("tipo_documento")
            or estado_actual.get("tipo_documento")
            or ""
        ).strip().lower()
        es_nota = tipo_doc_raw in ("nota de venta", "nota de compra")
        es_honorarios = tipo_doc_raw == "recibo por honorarios"

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
        if es_nota or es_honorarios:
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
            "entidad_numero": entidad_numero,
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
            "observacion": obtener("observacion", default=None),
        }
