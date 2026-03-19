"""
Agente Estado 2: listas WhatsApp con id+nombre desde APIs; al responder se guarda en Redis.

Orden: sucursal → centro_costo (solo compra) → forma_pago (LISTAR_FORMAS) → medio_catalogo (LISTAR_MEDIOS).
En venta se omite centro de costo.

Redis: id_sucursal/sucursal, id_centro_costo/centro_costo (compra), id_forma_pago/forma_pago,
id_medio_pago/medio_pago (catálogo LISTAR_MEDIOS). Contado/crédito queda en metodo_pago (extractor), no en medio_pago.
Ya no se usa id_metodo_pago para forma; id_forma_pago e id_medio_pago vienen de sendas APIs n8n.
"""
from __future__ import annotations

import json
from typing import Any

from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository
from repositories.parametros_repository import ParametrosRepository
from services.helpers.opciones_domain import (
    CAMPOS_ESTADO2,
    lista_para_redis,
    normalizar_opciones_actuales,
    siguiente_campo_pendiente,
)

# Clave en Redis para el diccionario temporal de opciones mostradas (matchear mensaje → id)
OPCIONES_ACTUALES_KEY = "opciones_actuales"

# Límite WhatsApp list message: row title 24 caracteres (como test_opciones)
MAX_ROW_TITLE = 24


def _truncar(s: str, max_len: int) -> str:
    if not s or max_len <= 0:
        return (s or "")[:max_len] if max_len > 0 else ""
    return s[:max_len] if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"


def _normalizar_texto(s: str) -> str:
    return (s or "").strip().lower()


def _coincide_nombre(mensaje: str, nombre: str) -> bool:
    return _normalizar_texto(mensaje) == _normalizar_texto(nombre)


def _id_match(op: dict, id_val: Any) -> bool:
    """Compara id de la opción con id_val sin depender de tipo (int vs str)."""
    oid = op.get("id")
    if oid is None and id_val is None:
        return True
    if oid is None or id_val is None:
        return False
    return str(oid) == str(id_val)


def _buscar_opcion_por_substring(mensaje: str, opciones: list[dict]) -> tuple:
    """Si el mensaje está contenido en un nombre (o al revés), devuelve (id, nombre); si no, (None, None)."""
    msg = _normalizar_texto(mensaje)
    if not msg:
        return (None, None)
    for op in opciones:
        nom = (op.get("nombre") or op.get("title") or "").strip()
        nom_low = nom.lower()
        if msg in nom_low or nom_low in msg:
            return (op.get("id"), nom or str(op.get("id")))
    return (None, None)


def _build_prompt_resolver_opcion(mensaje: str, opciones: list[dict]) -> str:
    """Envía opciones_actuales + mensaje a la IA; la IA devuelve solo un id en JSON."""
    lista_txt = json.dumps([{"id": o.get("id"), "nombre": o.get("nombre") or o.get("title")} for o in opciones], ensure_ascii=False)
    return f"""Tienes esta lista de opciones (cada una con "id" y "nombre") y el mensaje del usuario. El usuario está eligiendo UNA opción de la lista.

Lista de opciones:
{lista_txt}

Mensaje del usuario: "{mensaje}"

Devuelve el "id" numérico (o el id tal cual si es texto como "yape") de la opción a la que se refiere el usuario. Si el mensaje no corresponde a ninguna opción, devuelve null.

Responde ÚNICAMENTE con un JSON de una sola clave "id". Ejemplos:
- Si eligió la primera: {{"id": 29}}
- Si no hay coincidencia: {{"id": null}}"""


class OpcionesService:
    def __init__(
        self,
        cache: CacheRepository,
        informacion: InformacionRepository,
        parametros: ParametrosRepository | None = None,
        ai: Any = None,
    ) -> None:
        self._cache = cache
        self._informacion = informacion
        self._parametros = parametros
        self._ai = ai
        self._last_ai_error: str | None = None

    def get_next(
        self,
        wa_id: str,
        id_from: int,
        id_plataforma: int = 6,
    ) -> dict:
        """
        Devuelve la siguiente lista de opciones en texto y payload para ws_send_whatsapp_list.
        Persiste en Redis opciones_actuales = [{id, nombre}, ...] para matchear después.
        id_plataforma se incluye en payload_whatsapp_list (requerido por la API de lista WhatsApp).
        """
        registro = self._cache.consultar(wa_id, id_from) if wa_id and id_from else None
        debug_agente = {"modo": "get_next", "tiene_registro": registro is not None}
        # Qué se leyó de Redis (campos Estado 2 y opciones_actuales) para diagnosticar.
        if registro is not None:
            opciones_en_redis = normalizar_opciones_actuales(registro.get(OPCIONES_ACTUALES_KEY))
            debug_agente["redis_leido"] = {
                "id_sucursal": registro.get("id_sucursal"),
                "id_centro_costo": registro.get("id_centro_costo"),
                "id_forma_pago": registro.get("id_forma_pago"),
                "forma_pago": (registro.get("forma_pago") or "").strip() or None,
                "id_medio_pago": registro.get("id_medio_pago"),
                "medio_pago_catalogo": (registro.get("medio_pago") or "").strip() or None,
                "metodo_pago": (registro.get("metodo_pago") or "").strip() or None,
            }
            debug_agente["opciones_actuales_de_redis"] = {
                "recuperado": len(opciones_en_redis) > 0,
                "count": len(opciones_en_redis),
            }

        if not registro:
            debug_agente["motivo"] = "no_hay_registro"
            return {
                "listo_estado1": False,
                "mensaje": "No hay registro activo. Complete primero el registro (Estado 1).",
                "campo_pendiente": None,
                "payload_whatsapp_list": None,
                "debug": debug_agente,
            }
        estado = int(registro.get("estado") or 0)
        debug_agente["estado"] = estado
        if estado < 4:
            debug_agente["motivo"] = "estado_menor_4"
            return {
                "listo_estado1": False,
                "mensaje": "Primero confirme el registro (estado 3 → 4) antes de elegir sucursal, centro (si compra), forma y medio de pago.",
                "campo_pendiente": None,
                "payload_whatsapp_list": None,
                "debug": debug_agente,
            }

        campo = siguiente_campo_pendiente(registro, self._parametros is not None)
        debug_agente["campo_pendiente"] = campo
        if not campo:
            debug_agente["motivo"] = "estado2_completo"
            return {
                "listo_estado1": True,
                "estado2_completo": True,
                "campo_pendiente": None,
                "opciones_actuales": None,
                "payload_whatsapp_list": None,
                "mensaje": "Diga 'finalizar registro' para continuar.",
                "debug": debug_agente,
            }

        # Para tablas externas (sucursales / métodos de pago) también se usa id_from como id_empresa.
        opciones_raw = self._obtener_lista_opciones(campo, wa_id, id_from)
        opciones_actuales = lista_para_redis(opciones_raw)
        titulo = self._titulo_campo(campo)
        mensaje = f"{titulo}\n" + self._formatear_texto_lista(opciones_actuales) if opciones_actuales else "No hay opciones disponibles."

        try:
            self._cache.actualizar(wa_id, id_from, {OPCIONES_ACTUALES_KEY: opciones_actuales})
        except Exception:
            pass

        debug_agente["motivo"] = "lista_mostrada"
        debug_agente["opciones_count"] = len(opciones_actuales) if opciones_actuales else 0
        debug_agente["lista_devuelta_origen"] = "api_y_guardada_en_redis"
        payload_list = self._build_payload_whatsapp_list(
            id_empresa=id_from,
            phone=wa_id,
            id_plataforma=id_plataforma,
            campo=campo,
            opciones_actuales=opciones_actuales,
        )
        return {
            "listo_estado1": True,
            "estado2_completo": False,
            "campo_pendiente": campo,
            "opciones_actuales": opciones_actuales,
            "payload_whatsapp_list": payload_list,
            "mensaje": mensaje,
            "debug": debug_agente,
        }

    def submit(
        self,
        wa_id: str,
        id_from: int,
        campo: str,
        valor,
        id_plataforma: int = 6,
    ) -> dict:
        """
        valor puede ser el id (número) o el mensaje del usuario (nombre de la opción).
        Si es texto, se matchea con opciones_actuales en Redis y se guarda el id.
        Tras guardar, se devuelve el siguiente grupo en mensaje para desplegar de inmediato.
        """
        self._last_ai_error = None
        debug: dict = {"ai_llamada": False}

        if campo not in CAMPOS_ESTADO2:
            print(
                "[OpcionesService.submit] Campo no válido",
                {"wa_id": wa_id, "id_from": id_from, "campo": campo},
                flush=True,
            )
            return {"success": False, "mensaje": f"Campo no válido: {campo}", "debug": {"etapa": "validacion_campo"}}

        registro = self._cache.consultar(wa_id, id_from) if wa_id and id_from else None
        if not registro:
            print(
                "[OpcionesService.submit] No hay registro activo",
                {"wa_id": wa_id, "id_from": id_from},
                flush=True,
            )
            return {"success": False, "mensaje": "No hay registro activo.", "debug": {"etapa": "sin_registro"}}

        valor_id = valor
        valor_nombre = None
        opciones_actuales = normalizar_opciones_actuales(registro.get(OPCIONES_ACTUALES_KEY))

        debug["opciones_count"] = len(opciones_actuales) if opciones_actuales else 0
        debug["valor_tipo"] = type(valor).__name__
        debug["ai_inyectado"] = self._ai is not None

        print(
            "[OpcionesService.submit] IN",
            {
                "wa_id": wa_id,
                "id_from": id_from,
                "campo": campo,
                "valor_raw": valor,
                "opciones_actuales": opciones_actuales,
            },
            flush=True,
        )

        if isinstance(valor, str) and opciones_actuales:
            match_etapa = "ninguno"
            for op in opciones_actuales:
                nom = op.get("nombre") or op.get("title") or ""
                if _coincide_nombre(valor, nom):
                    valor_id = op.get("id")
                    valor_nombre = nom
                    match_etapa = "exacto"
                    break
            if match_etapa != "exacto":
                valor_id, valor_nombre = _buscar_opcion_por_substring(valor, opciones_actuales)
                if valor_id is not None:
                    match_etapa = "substring"
            if valor_id is None:
                valor_id, valor_nombre = self._resolver_opcion_ia(valor, opciones_actuales)
                match_etapa = "ia"
                debug["ai_llamada"] = True
                if self._last_ai_error:
                    debug["ai_error"] = self._last_ai_error
            if valor_id is None:
                try:
                    valor_id = int(valor)
                    valor_nombre = next((op.get("nombre") or op.get("title") for op in opciones_actuales if _id_match(op, valor_id)), None)
                    match_etapa = "int"
                except (TypeError, ValueError):
                    print(
                        "[OpcionesService.submit] No se reconoce la opción",
                        {"valor": valor},
                        flush=True,
                    )
                    debug["match_etapa"] = match_etapa
                    return {
                        "success": False,
                        "mensaje": f"No se reconoce la opción '{valor}'. Escriba el nombre de la lista o un texto que lo identifique.",
                        "debug": debug,
                    }
            debug["match_etapa"] = match_etapa
        else:
            if not isinstance(valor, str):
                debug["match_etapa"] = "valor_no_texto"
                debug["mensaje_interno"] = "Se requiere valor como texto para matchear por nombre o IA; si es id numérico, envíalo como número."
            elif not opciones_actuales:
                debug["match_etapa"] = "sin_opciones_actuales"
                debug["mensaje_interno"] = "No hay opciones_actuales en Redis; llame primero a get_next para cargar la lista."

        print(
            "[OpcionesService.submit] Después de resolver valor",
            {"valor_id": valor_id, "valor_nombre": valor_nombre},
            flush=True,
        )

        datos = {}
        # Para sucursales / métodos de pago, id_from se usa como id_empresa de tablas externas.
        id_tablas = id_from
        if campo == "sucursal":
            try:
                id_suc = int(valor_id)
                datos["id_sucursal"] = id_suc
                lista_suc = self._informacion.obtener_sucursales(id_tablas)
                nombre = valor_nombre or next((s.get("nombre") or str(s.get("id")) for s in lista_suc if s.get("id") == id_suc), str(valor_id))
                datos["sucursal"] = nombre
            except (TypeError, ValueError):
                print(
                    "[OpcionesService.submit] Valor de sucursal no válido",
                    {"valor_id": valor_id},
                    flush=True,
                )
                return {"success": False, "mensaje": "Valor de sucursal no válido."}
        elif campo == "centro_costo":
            try:
                id_cc = int(valor_id)
                datos["id_centro_costo"] = id_cc
                centros = self._parametros.obtener_centros_costo(wa_id) if self._parametros else []
                nombre = valor_nombre or next((c.get("nombre") or str(c.get("id")) for c in centros if c.get("id") == id_cc), str(valor_id))
                datos["centro_costo"] = nombre
            except (TypeError, ValueError):
                print(
                    "[OpcionesService.submit] Valor de centro de costo no válido",
                    {"valor_id": valor_id},
                    flush=True,
                )
                return {"success": False, "mensaje": "Valor de centro de costo no válido."}
        elif campo == "forma_pago":
            v = (str(valor_id) or str(valor) or "").strip()
            if not v:
                print(
                    "[OpcionesService.submit] Valor de forma de pago vacío",
                    {"valor_id": valor_id, "valor": valor},
                    flush=True,
                )
                return {"success": False, "mensaje": "Valor de forma de pago vacío."}
            datos["forma_pago"] = valor_nombre or v
            try:
                datos["id_forma_pago"] = int(float(str(valor_id).strip()))
            except (TypeError, ValueError):
                datos["id_forma_pago"] = valor_id
            datos["id_metodo_pago"] = None
        elif campo == "medio_catalogo":
            v = (str(valor_id) or str(valor) or "").strip()
            if not v:
                return {"success": False, "mensaje": "Valor de medio de pago vacío."}
            datos["medio_pago"] = valor_nombre or v
            datos["nombre_medio_pago"] = valor_nombre or v
            try:
                datos["id_medio_pago"] = int(float(str(valor_id).strip()))
            except (TypeError, ValueError):
                datos["id_medio_pago"] = valor_id

        siguiente = self._siguiente_campo_despues_de(registro, datos)
        id_tablas_next = id_from
        opciones_actuales_next = []
        if siguiente:
            opciones_raw = self._obtener_lista_opciones(siguiente, wa_id, id_tablas_next)
            opciones_actuales_next = lista_para_redis(opciones_raw)

        payload = {**datos, OPCIONES_ACTUALES_KEY: opciones_actuales_next}
        try:
            self._cache.actualizar(wa_id, id_from, payload)
        except Exception as e:
            print(
                "[OpcionesService.submit] Error al actualizar cache",
                {"wa_id": wa_id, "id_from": id_from, "error": str(e)},
                flush=True,
            )
            return {"success": False, "mensaje": str(e)}

        titulo_siguiente = self._titulo_campo(siguiente) if siguiente else None
        texto_siguiente = (f"{titulo_siguiente}\n" + self._formatear_texto_lista(opciones_actuales_next)) if opciones_actuales_next else None
        mensaje = "Diga 'finalizar registro' para continuar." if siguiente is None else (texto_siguiente or None)
        payload_list = self._build_payload_whatsapp_list(
            id_empresa=id_from,
            phone=wa_id,
            id_plataforma=id_plataforma,
            campo=siguiente,
            opciones_actuales=opciones_actuales_next,
        ) if siguiente and opciones_actuales_next else None
        resp = {
            "success": True,
            "listo_estado1": True,
            "estado2_completo": siguiente is None,
            "campo_pendiente": siguiente,
            "opciones_actuales": opciones_actuales_next if opciones_actuales_next else None,
            "payload_whatsapp_list": payload_list,
            "mensaje": mensaje,
            "campo_guardado": campo,
            "id_detectada": valor_id,
            "nombre_detectado": valor_nombre,
            "debug": debug,
        }
        print(
            "[OpcionesService.submit] OUT respuesta",
            resp,
            flush=True,
        )
        return resp

    def _resolver_opcion_ia(self, mensaje: str, opciones: list[dict]) -> tuple:
        """Recibe opciones_actuales y mensaje; la IA devuelve el id. Retorna (id, nombre) o (None, None)."""
        self._last_ai_error = None
        if not self._ai:
            self._last_ai_error = "Servicio de IA no inyectado"
            return (None, None)
        if not opciones:
            self._last_ai_error = "Lista de opciones vacía"
            return (None, None)
        if not (mensaje or "").strip():
            self._last_ai_error = "Mensaje vacío"
            return (None, None)
        try:
            prompt = _build_prompt_resolver_opcion(mensaje, opciones)
            out = self._ai.completar_json(prompt)
            id_val = out.get("id")
            if id_val is None:
                self._last_ai_error = "IA devolvió id null"
                return (None, None)
            if isinstance(id_val, str) and id_val.strip().lower() in ("null", ""):
                self._last_ai_error = "IA devolvió id null o vacío"
                return (None, None)
            # Normalizar id: puede venir como float, str "1", etc.
            if isinstance(id_val, float) and id_val.is_integer():
                id_val = int(id_val)
            elif isinstance(id_val, str) and id_val.isdigit():
                id_val = int(id_val)
            # Buscar nombre comparando id sin depender del tipo en opciones
            op_elegida = next((o for o in opciones if _id_match(o, id_val)), None)
            nombre_final = (op_elegida.get("nombre") or op_elegida.get("title")) if op_elegida else str(id_val)
            return (id_val, nombre_final)
        except Exception as e:
            self._last_ai_error = str(e)
            return (None, None)

    def _siguiente_campo_despues_de(self, registro: dict, datos_guardados: dict) -> str | None:
        reg = {**registro, **datos_guardados}
        return siguiente_campo_pendiente(reg, self._parametros is not None)

    def _obtener_lista_opciones(self, campo: str, wa_id: str, id_tablas: int) -> list:
        if campo == "sucursal":
            return self._informacion.obtener_sucursales(id_tablas)
        if campo == "centro_costo" and self._parametros:
            return self._parametros.obtener_centros_costo(wa_id)
        if campo == "forma_pago":
            return self._informacion.obtener_formas_pago()
        if campo == "medio_catalogo":
            return self._informacion.obtener_medios_pago_catalogo()
        return []

    def _lista_para_redis(self, campo: str, raw: list) -> list[dict]:
        """Convierte la lista cruda en [{id, nombre}, ...] para guardar en Redis y matchear."""
        out = []
        for item in raw or []:
            if isinstance(item, dict):
                id_v = item.get("id")
                nom = (item.get("nombre") or item.get("title") or "").strip() or str(id_v)
                out.append({"id": id_v, "nombre": nom})
            elif isinstance(item, (str, int)):
                out.append({"id": item, "nombre": str(item)})
        return out

    def _titulo_campo(self, campo: str) -> str:
        if campo == "sucursal":
            return "Sucursales:"
        if campo == "centro_costo":
            return "Centros de costo:"
        if campo == "forma_pago":
            return "Formas de pago:"
        if campo == "medio_catalogo":
            return "Medios de pago:"
        return "Opciones:"

    def _textos_whatsapp_list(self, campo: str) -> tuple[str, str, str, str, str]:
        """
        Textos para el payload de ws_send_whatsapp_list (mismo formato que test_opciones.py).
        Retorna (body_text, header_text, footer_text, button_text, section_title).
        """
        if campo == "sucursal":
            return (
                "Sucursales disponibles: ",
                "Sucursales",
                "Selecciona una sucursal",
                "Ver sucursales",
                "Sucursales",
            )
        if campo == "centro_costo":
            return (
                "Centros de costo disponibles: ",
                "Centros de costo",
                "Selecciona un centro de costo",
                "Ver centros de costo",
                "Centros de costo",
            )
        if campo == "forma_pago":
            return (
                "Formas de pago disponibles: ",
                "Formas de pago",
                "Selecciona una forma de pago",
                "Ver formas de pago",
                "Formas de pago",
            )
        if campo == "medio_catalogo":
            return (
                "Medios de pago disponibles: ",
                "Medios de pago",
                "Selecciona un medio de pago",
                "Ver medios de pago",
                "Medios de pago",
            )
        return (
            "Opciones disponibles: ",
            "Opciones",
            "Selecciona una opción",
            "Ver opciones",
            "Opciones",
        )

    def _formatear_texto_lista(self, opciones: list[dict]) -> str:
        if not opciones:
            return "No hay opciones disponibles."
        lineas = ["• " + (op.get("nombre") or str(op.get("id")) or "") for op in opciones]
        return "\n".join(lineas)

    def _opciones_a_filas(self, opciones: list[dict]) -> list[dict]:
        """Convierte opciones_actuales [{id, nombre}] en filas para lista WhatsApp (title ≤ MAX_ROW_TITLE)."""
        if not opciones:
            return []
        filas = []
        for op in opciones:
            oid = op.get("id")
            nombre = (op.get("nombre") or op.get("title") or str(oid) or "").strip()
            filas.append({
                "id": str(oid) if oid is not None else "0",
                "title": _truncar(nombre, MAX_ROW_TITLE),
                "description": "",
            })
        return filas

    def _build_payload_whatsapp_list(
        self,
        id_empresa: int,
        phone: str,
        id_plataforma: int,
        campo: str | None,
        opciones_actuales: list[dict],
    ) -> dict | None:
        """
        Arma el payload para ws_send_whatsapp_list.php (mismo formato que test_opciones.py).
        id_plataforma requerido por la API. Si campo es None o no hay opciones, retorna None.
        """
        if not campo or not opciones_actuales:
            return None
        body_text, header_text, footer_text, button_text, section_title = self._textos_whatsapp_list(campo)
        filas = self._opciones_a_filas(opciones_actuales)
        if not filas:
            filas = [{"id": "0", "title": f"Sin {section_title.lower()}", "description": ""}]
        return {
            "id_empresa": id_empresa,
            "id_plataforma": id_plataforma,
            "phone": phone,
            "body_text": body_text,
            "button_text": button_text,
            "header_text": header_text,
            "footer_text": footer_text,
            "sections": [{"title": section_title, "rows": filas}],
        }
