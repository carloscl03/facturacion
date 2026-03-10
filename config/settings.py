import os
from dotenv import load_dotenv

load_dotenv()

# --- IA ---
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
MODELO_IA: str = "gpt-4.1-mini"

# --- APIs externas ---
URL_API: str = "https://api.maravia.pe/servicio/n8n/ws_historial_cache.php"
URL_CLIENTE: str = "https://api.maravia.pe/servicio/n8n/ws_cliente.php"
URL_PROVEEDOR: str = "https://api.maravia.pe/servicio/n8n_asistente/ws_proveedor.php"
URL_VENTA_SUNAT: str = "https://api.maravia.pe/servicio/ws_ventas.php"
URL_INFORMACION_IA: str = "https://api.maravia.pe/servicio/ws_informacion_ia.php"

# --- Tokens ---
TOKEN_SUNAT: str = os.getenv("TOKEN_SUNAT", "")

# --- Redis (cache alternativo) ---
# Por defecto "http" para desarrollo local sin Redis; en producción usar CACHE_BACKEND=redis en .env
CACHE_BACKEND: str = os.getenv("CACHE_BACKEND", "http")  # "http" | "redis"
# Por defecto localhost para desarrollo local; en Docker/producción definir REDIS_URL en .env
REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_TTL: int = int(os.getenv("REDIS_TTL", "86400"))
