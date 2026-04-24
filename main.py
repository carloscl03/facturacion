import time
import uuid

from fastapi import FastAPI, Request

from config.logging_config import get_logger, setup_logging

setup_logging()
_log = get_logger("maravia.app")

from api.routes import (
    casual,
    clasificador,
    confirmar_registro,
    eliminar,
    extraccion,
    finalizar,
    identificador,
    informador,
    iniciar,
    opciones,
    preguntador,
    resumen,
)

app = FastAPI(title="MaravIA Bot API")


@app.middleware("http")
async def _request_logger(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    wa_id = request.query_params.get("wa_id", "")
    id_from = request.query_params.get("id_from", "")
    t0 = time.perf_counter()
    _log.info(
        "request_in",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "wa_id": wa_id,
            "id_from": id_from,
        },
    )
    response = await call_next(request)
    ms = round((time.perf_counter() - t0) * 1000)
    _log.info(
        "request_out",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "wa_id": wa_id,
            "status": response.status_code,
            "latency_ms": ms,
        },
    )
    return response


@app.on_event("startup")
async def _on_startup():
    from config import settings
    _log.info(
        "startup",
        extra={
            "cache_backend": settings.CACHE_BACKEND,
            "modelo_ia": settings.MODELO_IA,
        },
    )

app.include_router(extraccion.router)
app.include_router(preguntador.router)
app.include_router(clasificador.router)
app.include_router(confirmar_registro.router)
app.include_router(casual.router)
app.include_router(informador.router)
app.include_router(resumen.router)
app.include_router(identificador.router)
app.include_router(eliminar.router)
app.include_router(finalizar.router)
app.include_router(iniciar.router)
app.include_router(opciones.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
