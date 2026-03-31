from repositories.base import CacheRepository
from services.whatsapp_sender import enviar_texto as _enviar_texto


class EliminarService:
    def __init__(self, repo: CacheRepository) -> None:
        self._repo = repo

    def ejecutar(self, wa_id: str, id_from: int, *, id_empresa: int | None = None, id_plataforma: int | None = None) -> dict:
        resultado = self._repo.eliminar(wa_id, id_from)
        if resultado.get("success"):
            if getattr(self._repo, "limpiar_debug", None):
                self._repo.limpiar_debug(wa_id, id_from)
            mensaje = "Entendido. He cancelado la operación y limpiado el borrador. ¿Deseas iniciar un registro nuevo?"
            if id_empresa is not None:
                _enviar_texto(id_empresa, wa_id, mensaje, id_plataforma)
            return {"status": "borrado", "mensaje_usuario": mensaje}
        mensaje_err = "No encontré ninguna operación activa para borrar."
        if id_empresa is not None:
            _enviar_texto(id_empresa, wa_id, mensaje_err, id_plataforma)
        return {"status": "error", "mensaje": mensaje_err}
