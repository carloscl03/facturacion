import asyncio
import uvicorn
from fastapi import FastAPI, Request
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END

# 1. Definimos el Estado con los 3 campos que pides
class AgentState(TypedDict):
    id_usuario: str
    texto: str
    tipo: str

# 2. Nodo de Procesamiento
def procesar_mensaje(state: AgentState):
    # Aquí es donde LangGraph "entiende" los datos
    print("\n" + "═"*30)
    print(f"🆔 ID: {state['id_usuario']}")
    print(f"📝 TEXTO: {state['texto']}")
    print(f"📂 TIPO: {state['tipo']}")
    print("═"*30)
    
    # Retornamos el estado para finalizar
    return state

# 3. Construcción del Grafo
workflow = StateGraph(AgentState)
workflow.add_node("receptor", procesar_mensaje)
workflow.set_entry_point("receptor")
workflow.add_edge("receptor", END)
app_langgraph = workflow.compile()

# 4. Servidor FastAPI para recibir de n8n
app = FastAPI()

@app.post("/procesar_desde_n8n")
async def recibir_de_n8n(request: Request):
    data = await request.json()
    
    # Extraemos solo lo que pides
    inputs = {
        "id_usuario": data.get("usuario_id"),
        "texto": data.get("texto"),
        "tipo": data.get("tipo")
    }
    
    # Ejecutamos LangGraph
    await app_langgraph.ainvoke(inputs)
    
    # Devolvemos confirmación a n8n
    return {
        "status": "recibido",
        "datos": inputs
    }

if __name__ == "__main__":
    print("🚀 Esperando ID, Texto y Tipo en el puerto 5000...")
    uvicorn.run(app, host="0.0.0.0", port=3000)