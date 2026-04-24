"""
Estado 2: listas WhatsApp (sucursal → centro solo compra → forma LISTAR_FORMAS → medio LISTAR_MEDIOS).
Solo aplica con estado >= 4. **forma_pago** / **medio_pago** + ids vienen aquí. **metodo_pago** (contado/crédito) lo llena el extractor y no se pisa.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from api.deps import get_ai_service, get_cache_repo, get_informacion_repo, get_parametros_repo
from config import settings
from config.logging_config import get_logger
from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository
from repositories.parametros_repository import ParametrosRepository
from services.ai_service import AIService
from services.helpers.opciones_domain import normalizar_opciones_actuales, siguiente_campo_pendiente
from services.opciones_service import OpcionesService
from services.whatsapp_sender import enviar_lista as _enviar_lista_whatsapp_shared, enviar_texto as _enviar_texto_shared

# Clave Redis: si ya hay lista cargada, el mensaje es selección; si no, es primer mensaje (solo cargar lista).
OPCIONES_ACTUALES_KEY = "opciones_actuales"
# Mensaje de finalizar que se envía por ws_send_whatsapp_oficial
MENSAJE_FINALIZAR = "Por favor, bríndame una confirmación para continuar"

router = APIRouter()
_log = get_logger("maravia.routes.opciones")


class OpcionesBody(BaseModel):
    action: str = "get"
    campo: str | None = None
    valor: str | int | None = None
    mensaje: str | None = None
    id_plataforma: int | None = None
    id_empresa: int | None = None  # solo para enviar la lista a WhatsApp
    id_empresa_whatsapp: int | None = None  # alias de id_empresa


@router.post("/opciones")
async def opciones(
    wa_id: str,
    id_from: int,
    mensaje: str | None = None,
    action: str | None = None,
    campo: str | None = None,
    valor: str | int | None = None,
    id_plataforma: int | None = None,
    id_empresa: int | None = None,
    body: OpcionesBody | None = Body(None),
    cache: CacheRepository = Depends(get_cache_repo),
    informacion: InformacionRepository = Depends(get_informacion_repo),
    parametros: ParametrosRepository = Depends(get_parametros_repo),
    ai: AIService = Depends(get_ai_service),
):
    """
    Entrada: mensaje, id_from, id_empresa, id_plataforma (y wa_id).
      - id_from: cache, Redis y tablas (sucursales, métodos de pago, etc.).
      - id_empresa: solo para enviar la lista a WhatsApp (credenciales). Si no se envía, se usa ID_EMPRESA_WHATSAPP en .env o id_from.
      - id_plataforma: para payload_whatsapp_list (default 6).
      - mensaje, action, campo, valor: opcionales; action/campo/valor en query tienen prioridad sobre body.

    Flujo: Primer mensaje se ignora (solo se cargan opciones con wa_id e id_from). Segundo mensaje
    es la selección del usuario; se matchea con opciones_actuales y se guarda. Modo GET devuelve
    lista; modo SUBMIT (o inferido) guarda la elección y devuelve siguiente lista o mensaje.
    """
    b = body or OpcionesBody()
    id_plataforma_final: int = id_plataforma if id_plataforma is not None else (b.id_plataforma if b.id_plataforma is not None else 6)
    # id_empresa: solo para enviar mensaje a WhatsApp. Origen: query id_empresa > body id_empresa > body id_empresa_whatsapp > env ID_EMPRESA_WHATSAPP > None (se usa id_from)
    id_empresa_wa_final: int | None = (
        id_empresa if id_empresa is not None
        else (b.id_empresa if b.id_empresa is not None else (b.id_empresa_whatsapp if b.id_empresa_whatsapp is not None else settings.ID_EMPRESA_WHATSAPP))
    )

    _log.debug("opciones_request", extra={
        "wa_id": wa_id, "id_from": id_from,
        "id_empresa": id_empresa_wa_final, "id_plataforma": id_plataforma_final,
        "action": action, "campo": campo,
    })

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
        "id_empresa": id_empresa_wa_final,
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
        return _enviar_lista_whatsapp_shared(payload_list)

    def _enviar_mensaje_oficial(
        id_empresa: int, phone: str, id_plataforma: int, mensaje: str
    ) -> tuple[bool, str | None, dict]:
        ok, err = _enviar_texto_shared(id_empresa, phone, mensaje, id_plataforma)
        debug_oficial = {"envio_directo": True, "ok": ok, "error": err}
        return ok, err, debug_oficial

    service = OpcionesService(cache, informacion, parametros, ai=ai)
    if action_final == "submit":
        _log.debug("opciones_modo_submit", extra={"wa_id": wa_id, "id_from": id_from, "campo": campo_final})
        if campo_final is None:
            return _respuesta_con_debug({"success": False, "mensaje": "Se requiere campo para action=submit.", "debug": {"etapa": "falta_campo"}})
        if valor_final is None and campo_final:
            return _respuesta_con_debug({
                "success": False,
                "mensaje": "Se requiere valor (id o texto con el nombre de la opción) ya sea en el body, en el query param 'valor' o en el query param 'mensaje'.",
                "debug": {"etapa": "falta_valor"},
            })
        out = service.submit(wa_id, id_from, campo_final, valor_final, id_plataforma_final)

        # Si no matcheó la opción: enviar mensaje amigable y reenviar la lista
        if out.get("success") is False and not out.get("payload_whatsapp_list"):
            id_emp = id_empresa_wa_final if id_empresa_wa_final is not None else (settings.ID_EMPRESA_WHATSAPP or id_from)
            _enviar_texto_shared(id_emp, wa_id, "Por favor, selecciona una opción de la lista que te envié.", id_plataforma_final)
            # Reenviar la lista actual
            out_reenvio = service.get_next(wa_id, id_from, id_plataforma_final)
            payload_reenvio = out_reenvio.get("payload_whatsapp_list")
            if payload_reenvio:
                if id_empresa_wa_final is not None:
                    payload_reenvio = {**payload_reenvio, "id_empresa": id_empresa_wa_final}
                _enviar_lista_whatsapp(payload_reenvio)

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
        if out.get("estado2_completo") and (out.get("mensaje") or "").strip() == MENSAJE_FINALIZAR:
            id_empresa_envio = id_empresa_wa_final if id_empresa_wa_final is not None else (settings.ID_EMPRESA_WHATSAPP or id_from)
            enviado_of, error_of, debug_of = _enviar_mensaje_oficial(id_empresa_envio, wa_id, id_plataforma_final, MENSAJE_FINALIZAR)
            out["whatsapp_oficial_enviado"] = enviado_of
            if error_of:
                out["whatsapp_oficial_error"] = error_of
            out["whatsapp_oficial_debug"] = debug_of
        return _respuesta_con_debug(out)

    _log.debug("opciones_modo_get_next", extra={"wa_id": wa_id, "id_from": id_from})
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
    if out.get("estado2_completo") and (out.get("mensaje") or "").strip() == MENSAJE_FINALIZAR:
        id_empresa_envio = id_empresa_wa_final if id_empresa_wa_final is not None else (settings.ID_EMPRESA_WHATSAPP or id_from)
        enviado_of, error_of, debug_of = _enviar_mensaje_oficial(id_empresa_envio, wa_id, id_plataforma_final, MENSAJE_FINALIZAR)
        out["whatsapp_oficial_enviado"] = enviado_of
        if error_of:
            out["whatsapp_oficial_error"] = error_of
        out["whatsapp_oficial_debug"] = debug_of
    return _respuesta_con_debug(out)
