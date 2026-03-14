"""
Estado 2: opciones (sucursal → centro de costo → método de pago).
Solo aplica con estado >= 4. Opciones se devuelven en mensaje; el usuario responde con el nombre y se matchea por opciones_actuales en Redis.
Cuando hay payload_whatsapp_list, se envía a ws_send_whatsapp_list para mostrar la lista en WhatsApp.
"""
from __future__ import annotations

import requests

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from api.deps import get_ai_service, get_cache_repo, get_informacion_repo, get_parametros_repo
from config import settings
from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository
from repositories.parametros_repository import ParametrosRepository
from services.ai_service import AIService
from services.helpers.opciones_domain import normalizar_opciones_actuales, siguiente_campo_pendiente
from services.opciones_service import OpcionesService

# Clave Redis: si ya hay lista cargada, el mensaje es selección; si no, es primer mensaje (solo cargar lista).
OPCIONES_ACTUALES_KEY = "opciones_actuales"

router = APIRouter()


class OpcionesBody(BaseModel):
    action: str = "get"
    campo: str | None = None
    valor: str | int | None = None
    mensaje: str | None = None
    id_plataforma: int | None = None
    id_empresa_whatsapp: int | None = None


@router.post("/opciones")
async def opciones(
    wa_id: str,
    id_from: int,
    mensaje: str | None = None,
    action: str | None = None,
    campo: str | None = None,
    valor: str | int | None = None,
    id_plataforma: int | None = None,
    id_empresa_whatsapp: int | None = None,
    body: OpcionesBody | None = Body(None),
    cache: CacheRepository = Depends(get_cache_repo),
    informacion: InformacionRepository = Depends(get_informacion_repo),
    parametros: ParametrosRepository = Depends(get_parametros_repo),
    ai: AIService = Depends(get_ai_service),
):
    """
    Query:
      - wa_id, id_from (cache y id de tablas para sucursales/métodos).
      - id_empresa_whatsapp: opcional; id de empresa con credenciales WhatsApp para enviar la lista.
        Si no se envía, se usa id_from. Si el envío falla con "No se encontraron credenciales", pasar el id que sí tenga credenciales (ej. 1).
      - id_plataforma: opcional; para payload_whatsapp_list (default 6). Query o body.
      - mensaje: texto libre (se usa como selección solo a partir del segundo mensaje).
      - action, campo, valor: opcionales; si vienen en query tienen prioridad sobre el body.

    Flujo: Primer mensaje se ignora (solo se cargan opciones con wa_id e id_from). Segundo mensaje
    es la selección del usuario; se matchea con opciones_actuales y se guarda. Modo GET devuelve
    lista; modo SUBMIT (o inferido) guarda la elección y devuelve siguiente lista o mensaje.
    """
    b = body or OpcionesBody()
    id_plataforma_final: int = id_plataforma if id_plataforma is not None else (b.id_plataforma if b.id_plataforma is not None else 6)
    id_empresa_wa_final: int | None = id_empresa_whatsapp if id_empresa_whatsapp is not None else (b.id_empresa_whatsapp if b.id_empresa_whatsapp is not None else None)

    # DEBUG: traza de entrada a /opciones
    print(
        "[/opciones] IN:",
        {
            "wa_id": wa_id,
            "id_from": id_from,
            "id_empresa_whatsapp": id_empresa_wa_final,
            "id_plataforma": id_plataforma_final,
            "mensaje": mensaje,
            "q_action": action,
            "q_campo": campo,
            "q_valor": valor,
            "body": body.model_dump() if body else None,
        },
        flush=True,
    )

    # Prioridad de origen:
    # 1) Query param (action/campo/valor) si vienen.
    # 2) Body OpcionesBody.
    # 3) Defaults (action="get").
    action_final = (action or b.action or "get").strip().lower()
    campo_final = campo or b.campo

    # Valor: prioridad query.valor → body.valor → query mensaje → body.mensaje.
    if valor is not None:
        valor_final = valor
    elif b.valor is not None:
        valor_final = b.valor
    elif mensaje is not None:
        valor_final = mensaje
    else:
        valor_final = b.mensaje

    # Primer mensaje se ignora: solo sirve para cargar la lista (get_next con wa_id e id_from).
    # Si ya hay opciones_actuales en Redis, el mensaje es la selección del usuario → submit.
    if action_final == "get" and valor_final is not None and campo_final is None and wa_id and id_from:
        registro = cache.consultar(wa_id, id_from)
        if registro and int(registro.get("estado") or 0) >= 4:
            campo_inferido = siguiente_campo_pendiente(registro, parametros is not None)
            opciones_ya_cargadas = len(normalizar_opciones_actuales(registro.get(OPCIONES_ACTUALES_KEY))) > 0
            if campo_inferido and opciones_ya_cargadas:
                action_final = "submit"
                campo_final = campo_inferido
            # Si no hay opciones_actuales: primer mensaje → no inferir submit; se hará get_next y se ignorará valor_final

    # Debug para el nodo: qué recibió la API (diagnóstico).
    debug_request = {
        "action_final": action_final,
        "campo_final": campo_final,
        "valor_final": valor_final,
        "mensaje_query": mensaje,
        "body_mensaje": b.mensaje,
        "wa_id": wa_id,
        "id_from": id_from,
        "id_empresa_whatsapp": id_empresa_wa_final,
        "id_plataforma": id_plataforma_final,
    }
    if action_final == "get" and valor_final is not None and campo_final is None:
        debug_request["primer_mensaje_ignorado"] = True
        debug_request["motivo"] = "Sin opciones_actuales en Redis; se devuelve lista (get_next). El siguiente mensaje será la selección."

    def _respuesta_con_debug(resp: dict) -> dict:
        agente = resp.pop("debug", None) or {}
        resp["debug"] = {"request": debug_request, "agente": agente}
        return resp

    def _enviar_lista_whatsapp(payload_list: dict) -> tuple[bool, str | None, dict]:
        """
        Envía payload_whatsapp_list a ws_send_whatsapp_list.
        Retorna (éxito, mensaje_error, debug_whatsapp) con datos para diagnosticar fallos.
        """
        url = settings.URL_SEND_WHATSAPP_LIST
        debug_whatsapp = {
            "url_llamada": url,
            "status_code": None,
            "response_body_preview": None,
            "donde_arreglar": "Ver url_llamada: si 404, la URL no existe o cambió en el backend. Revisar config (URL_SEND_WHATSAPP_LIST) o .env.",
        }
        try:
            r = requests.post(
                url,
                json=payload_list,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            debug_whatsapp["status_code"] = r.status_code
            # Preview del body (útil si la API devuelve error en JSON)
            try:
                if r.text:
                    preview = r.text[:500] if len(r.text) <= 500 else r.text[:500] + "..."
                    debug_whatsapp["response_body_preview"] = preview
                body_lower = (r.text or "").lower()
                if r.status_code == 404:
                    if "credenciales" in body_lower and "whatsapp" in body_lower:
                        debug_whatsapp["donde_arreglar"] = (
                            "404: No hay credenciales de WhatsApp para el id_empresa enviado. "
                            "Pasar id_empresa_whatsapp (query o body) con el id de la empresa que sí tenga credenciales (ej. 1). "
                            "id_from sigue usándose para cache y tablas; id_empresa_whatsapp solo para enviar la lista."
                        )
                    else:
                        debug_whatsapp["donde_arreglar"] = (
                            "404 Not Found: la URL del servicio de lista WhatsApp no existe. "
                            "Comprobar URL_SEND_WHATSAPP_LIST en config/settings.py o variable de entorno. "
                            f"URL usada: {url}"
                        )
                elif r.status_code >= 500:
                    debug_whatsapp["donde_arreglar"] = "Error del servidor (5xx): fallo en el backend de envío; revisar logs del servicio ws_send_whatsapp_list."
                elif r.status_code == 400:
                    debug_whatsapp["donde_arreglar"] = "400 Bad Request: el payload puede tener campos incorrectos; revisar response_body_preview."
            except Exception:
                pass
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}", debug_whatsapp
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if not data.get("success", True):
                err = data.get("error") or data.get("message") or "API error"
                debug_whatsapp["donde_arreglar"] = f"API devolvió success=false: {err}. Revisar credenciales (id_empresa) o formato del payload."
                return False, err, debug_whatsapp
            debug_whatsapp["donde_arreglar"] = None  # Éxito
            return True, None, debug_whatsapp
        except requests.RequestException as e:
            debug_whatsapp["donde_arreglar"] = f"Error de conexión/timeout: {e}. Comprobar que la URL sea accesible desde este servidor: {url}"
            return False, str(e), debug_whatsapp

    service = OpcionesService(cache, informacion, parametros, ai=ai)
    if action_final == "submit":
        print(
            "[/opciones] MODO submit:",
            {"action_final": action_final, "campo_final": campo_final, "valor_final": valor_final},
            flush=True,
        )
        if campo_final is None:
            return _respuesta_con_debug({"success": False, "mensaje": "Se requiere campo para action=submit.", "debug": {"etapa": "falta_campo"}})
        if valor_final is None and campo_final:
            return _respuesta_con_debug({
                "success": False,
                "mensaje": "Se requiere valor (id o texto con el nombre de la opción) ya sea en el body, en el query param 'valor' o en el query param 'mensaje'.",
                "debug": {"etapa": "falta_valor"},
            })
        out = service.submit(wa_id, id_from, campo_final, valor_final, id_plataforma_final)
        payload_list = out.get("payload_whatsapp_list")
        if payload_list:
            if id_empresa_wa_final is not None:
                payload_list = {**payload_list, "id_empresa": id_empresa_wa_final}
            enviado, error, debug_wa = _enviar_lista_whatsapp(payload_list)
            out["whatsapp_list_enviado"] = enviado
            if error:
                out["whatsapp_list_error"] = error
            out["whatsapp_list_debug"] = debug_wa
            if id_empresa_wa_final is not None:
                out["whatsapp_list_debug"]["id_empresa_usado_en_envio"] = payload_list["id_empresa"]
        return _respuesta_con_debug(out)

    print(
        "[/opciones] MODO get_next:",
        {"action_final": action_final},
        flush=True,
    )
    out = service.get_next(wa_id, id_from, id_plataforma_final)
    payload_list = out.get("payload_whatsapp_list")
    if payload_list:
        if id_empresa_wa_final is not None:
            payload_list = {**payload_list, "id_empresa": id_empresa_wa_final}
        enviado, error, debug_wa = _enviar_lista_whatsapp(payload_list)
        out["whatsapp_list_enviado"] = enviado
        if error:
            out["whatsapp_list_error"] = error
        out["whatsapp_list_debug"] = debug_wa
        if id_empresa_wa_final is not None:
            out["whatsapp_list_debug"]["id_empresa_usado_en_envio"] = payload_list["id_empresa"]
    return _respuesta_con_debug(out)
