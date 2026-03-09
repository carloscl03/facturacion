from fastapi import FastAPI

from api.routes import (
    analizador,
    clasificador,
    eliminar,
    extraccion,
    finalizar,
    identificacion,
    informador,
    iniciar,
    preguntador,
    registrador,
    resumen,
    unificado,
)

app = FastAPI(title="MaravIA Bot API")

app.include_router(extraccion.router)
app.include_router(preguntador.router)
app.include_router(clasificador.router)
app.include_router(informador.router)
app.include_router(resumen.router)
app.include_router(identificacion.router)
app.include_router(eliminar.router)
app.include_router(finalizar.router)
app.include_router(unificado.router)
app.include_router(analizador.router)
app.include_router(registrador.router)
app.include_router(iniciar.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
