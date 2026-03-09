import os
from dotenv import load_dotenv

load_dotenv()

# --- IA ---
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
MODELO_IA: str = "gpt-4o-mini"

# --- APIs externas ---
URL_API: str = "https://api.maravia.pe/servicio/n8n/ws_historial_cache.php"
URL_CLIENTE: str = "https://api.maravia.pe/servicio/n8n/ws_cliente.php"
URL_PROVEEDOR: str = "https://api.maravia.pe/servicio/n8n_asistente/ws_proveedor.php"
URL_VENTA_SUNAT: str = "https://api.maravia.pe/servicio/ws_ventas.php"

# --- Tokens ---
TOKEN_SUNAT: str = os.getenv("TOKEN_SUNAT", "")
