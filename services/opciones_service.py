"""
Agente Estado 2: opciones (sucursal → centro de costo → método de pago).
Solo actúa cuando el registro está confirmado (estado >= 4).
El cambio de estado 3 → 4 se hace en el Clasificador con la confirmación del usuario; este agente
nunca escribe estado 4, solo lo exige para mostrar listas y guardar elecciones.
Opciones se presentan como lista de texto; el usuario responde con el nombre y se guarda el id.
Reconocimiento: primero match exacto (normalizado); si no hay match, se usa IA para identificar la opción.
Se guarda en Redis según el tipo: id_sucursal, id_centro_costo, id_metodo_pago (y nombre en sucursal, centro_costo, forma_pago). Orden: sucursal → centro_costo → forma_pago → medio_pago.
"""
from __future__ import annotations

import json
from typing import Any

from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository
from repositories.parametros_repository import ParametrosRepository

# Orden: primero sucursal, luego centro de costo, por último método de pago (forma + medio)
CAMPOS_ESTADO2 = ("sucursal", "centro_costo", "forma_pago", "medio_pago")

# Clave en Redis para el diccionario temporal de opciones mostradas (matchear mensaje → id)
OPCIONES_ACTUALES_KEY = "opciones_actuales"


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


def _parse_opciones_actuales(raw: Any) -> list[dict]:
    """Convierte opciones_actuales (puede venir como str desde Redis) en lista de dicts."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, json.JSONDecodeError):
            return []
    return []


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

    def get_next(
        self,
        wa_id: str,
        id_from: int,
        id_empresa_tablas: int | None = None,
        id_empresa: int | None = None,
        phone: str = "",
    ) -> dict:
        """
        Devuelve la siguiente lista de opciones en texto (no API WhatsApp).
        Persiste en Redis opciones_actuales = [{id, nombre}, ...] para matchear después.
        """
        registro = self._cache.consultar(wa_id, id_from) if wa_id and id_from else None
        if not registro:
            return {
                "listo_estado1": False,
                "mensaje": "No hay registro activo. Complete primero el registro (Estado 1).",
                "texto_lista": None,
                "campo_pendiente": None,
                "payload_whatsapp_list": None,
            }
        estado = int(registro.get("estado") or 0)
        if estado < 4:
            return {
                "listo_estado1": False,
                "mensaje": "Primero confirme el registro (estado 3 → 4) antes de elegir sucursal, centro de costo y método de pago.",
                "texto_lista": None,
                "campo_pendiente": None,
                "payload_whatsapp_list": None,
            }

        campo = self._siguiente_campo_pendiente(registro)
        if not campo:
            return {
                "listo_estado1": True,
                "estado2_completo": True,
                "campo_pendiente": None,
                "texto_lista": None,
                "opciones_actuales": None,
                "payload_whatsapp_list": None,
                "mensaje_siguiente": "Diga 'finalizar registro' para continuar.",
            }

        id_tablas = id_empresa_tablas if id_empresa_tablas is not None else (id_empresa or id_from)
        opciones_raw = self._obtener_lista_opciones(campo, wa_id, id_tablas)
        opciones_actuales = self._lista_para_redis(campo, opciones_raw)
        titulo = self._titulo_campo(campo)
        texto_lista = f"{titulo}\n" + self._formatear_texto_lista(opciones_actuales) if opciones_actuales else "No hay opciones disponibles."

        try:
            self._cache.actualizar(wa_id, id_from, {OPCIONES_ACTUALES_KEY: opciones_actuales})
        except Exception:
            pass

        return {
            "listo_estado1": True,
            "estado2_completo": False,
            "campo_pendiente": campo,
            "texto_lista": texto_lista,
            "opciones_actuales": opciones_actuales,
            "payload_whatsapp_list": None,
        }

    def submit(
        self,
        wa_id: str,
        id_from: int,
        campo: str,
        valor,
        id_empresa_tablas: int | None = None,
    ) -> dict:
        """
        valor puede ser el id (número) o el mensaje del usuario (nombre de la opción).
        Si es texto, se matchea con opciones_actuales en Redis y se guarda el id.
        Tras guardar, se devuelve el siguiente grupo (texto_lista) para desplegar de inmediato.
        """
        if campo not in CAMPOS_ESTADO2:
            return {"success": False, "mensaje": f"Campo no válido: {campo}"}

        registro = self._cache.consultar(wa_id, id_from) if wa_id and id_from else None
        if not registro:
            return {"success": False, "mensaje": "No hay registro activo."}

        valor_id = valor
        valor_nombre = None
        opciones_actuales = _parse_opciones_actuales(registro.get(OPCIONES_ACTUALES_KEY))

        if isinstance(valor, str) and opciones_actuales:
            for op in opciones_actuales:
                nom = op.get("nombre") or op.get("title") or ""
                if _coincide_nombre(valor, nom):
                    valor_id = op.get("id")
                    valor_nombre = nom
                    break
            else:
                # Match por substring (ej. "Lima" en "Sucursal Lima")
                valor_id, valor_nombre = _buscar_opcion_por_substring(valor, opciones_actuales)
                if valor_id is None:
                    # Reconocimiento por IA: opciones_actuales + mensaje → id
                    valor_id, valor_nombre = self._resolver_opcion_ia(valor, opciones_actuales)
                if valor_id is None:
                    try:
                        valor_id = int(valor)
                        valor_nombre = next((op.get("nombre") or op.get("title") for op in opciones_actuales if _id_match(op, valor_id)), None)
                    except (TypeError, ValueError):
                        return {"success": False, "mensaje": f"No se reconoce la opción '{valor}'. Escriba el nombre de la lista o un texto que lo identifique."}

        datos = {}
        id_tablas = id_empresa_tablas if id_empresa_tablas is not None else id_from
        if campo == "sucursal":
            try:
                id_suc = int(valor_id)
                datos["id_sucursal"] = id_suc
                lista_suc = self._informacion.obtener_sucursales(id_tablas)
                nombre = valor_nombre or next((s.get("nombre") or str(s.get("id")) for s in lista_suc if s.get("id") == id_suc), str(valor_id))
                datos["sucursal"] = nombre
            except (TypeError, ValueError):
                return {"success": False, "mensaje": "Valor de sucursal no válido."}
        elif campo == "centro_costo":
            try:
                id_cc = int(valor_id)
                datos["id_centro_costo"] = id_cc
                centros = self._parametros.obtener_centros_costo(wa_id) if self._parametros else []
                nombre = valor_nombre or next((c.get("nombre") or str(c.get("id")) for c in centros if c.get("id") == id_cc), str(valor_id))
                datos["centro_costo"] = nombre
            except (TypeError, ValueError):
                return {"success": False, "mensaje": "Valor de centro de costo no válido."}
        elif campo == "forma_pago":
            v = (str(valor_id) or str(valor) or "").strip()
            if not v:
                return {"success": False, "mensaje": "Valor de forma de pago vacío."}
            datos["id_metodo_pago"] = valor_id
            datos["forma_pago"] = valor_nombre or v
        elif campo == "medio_pago":
            v = (str(valor_id) or str(valor) or "").strip().lower()
            if v not in ("contado", "credito"):
                return {"success": False, "mensaje": "Valor debe ser contado o crédito."}
            datos["medio_pago"] = v

        siguiente = self._siguiente_campo_despues_de(registro, datos)
        id_tablas_next = id_empresa_tablas if id_empresa_tablas is not None else id_from
        opciones_actuales_next = []
        if siguiente:
            opciones_raw = self._obtener_lista_opciones(siguiente, wa_id, id_tablas_next)
            opciones_actuales_next = self._lista_para_redis(siguiente, opciones_raw)

        payload = {**datos, OPCIONES_ACTUALES_KEY: opciones_actuales_next}
        try:
            self._cache.actualizar(wa_id, id_from, payload)
        except Exception as e:
            return {"success": False, "mensaje": str(e)}

        titulo_siguiente = self._titulo_campo(siguiente) if siguiente else None
        texto_siguiente = (f"{titulo_siguiente}\n" + self._formatear_texto_lista(opciones_actuales_next)) if opciones_actuales_next else None
        mensaje_siguiente = "Diga 'finalizar registro' para continuar." if siguiente is None else None
        return {
            "success": True,
            "campo_guardado": campo,
            "siguiente": siguiente,
            "estado2_completo": siguiente is None,
            "texto_lista_siguiente": texto_siguiente,
            "opciones_actuales": opciones_actuales_next if opciones_actuales_next else None,
            "mensaje_siguiente": mensaje_siguiente,
        }

    def _resolver_opcion_ia(self, mensaje: str, opciones: list[dict]) -> tuple:
        """Recibe opciones_actuales y mensaje; la IA devuelve el id. Retorna (id, nombre) o (None, None)."""
        if not self._ai or not opciones or not (mensaje or "").strip():
            return (None, None)
        try:
            prompt = _build_prompt_resolver_opcion(mensaje, opciones)
            out = self._ai.completar_json(prompt)
            id_val = out.get("id")
            if id_val is None:
                return (None, None)
            if isinstance(id_val, str) and id_val.strip().lower() in ("null", ""):
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
        except Exception:
            return (None, None)

    def _siguiente_campo_pendiente(self, registro: dict) -> str | None:
        if not registro.get("id_sucursal"):
            return "sucursal"
        if self._parametros and not registro.get("id_centro_costo"):
            return "centro_costo"
        if not (registro.get("forma_pago") or "").strip():
            return "forma_pago"
        if (registro.get("medio_pago") or "").strip().lower() not in ("contado", "credito"):
            return "medio_pago"
        return None

    def _siguiente_campo_despues_de(self, registro: dict, datos_guardados: dict) -> str | None:
        reg = {**registro, **datos_guardados}
        return self._siguiente_campo_pendiente(reg)

    def _obtener_lista_opciones(self, campo: str, wa_id: str, id_tablas: int) -> list:
        if campo == "sucursal":
            return self._informacion.obtener_sucursales(id_tablas)
        if campo == "centro_costo" and self._parametros:
            return self._parametros.obtener_centros_costo(wa_id)
        if campo == "forma_pago":
            return self._informacion.obtener_metodos_pago(id_tablas)
        if campo == "medio_pago":
            return [{"id": "contado", "nombre": "Contado"}, {"id": "credito", "nombre": "Crédito"}]
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
            return "Métodos de pago:"
        if campo == "medio_pago":
            return "Medio de pago (contado o crédito):"
        return "Opciones:"

    def _formatear_texto_lista(self, opciones: list[dict]) -> str:
        if not opciones:
            return "No hay opciones disponibles."
        lineas = ["• " + (op.get("nombre") or str(op.get("id")) or "") for op in opciones]
        return "\n".join(lineas)
