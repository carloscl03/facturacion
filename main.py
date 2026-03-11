from fastapi import FastAPI

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
