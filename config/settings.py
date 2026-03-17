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
# Endpoint N8N ventas (REGISTRAR_VENTA / REGISTRAR_VENTA_N8N)
URL_VENTA_SUNAT: str = "https://api.maravia.pe/servicio/n8n/ws_venta.php"
URL_INFORMACION_IA: str = "https://api.maravia.pe/servicio/ws_informacion_ia.php"
URL_PARAMETROS: str = "https://api.maravia.pe/servicio/n8n/ws_parametros.php"
URL_COMPRA: str = "https://api.maravia.pe/servicio/n8n/ws_compra.php"
URL_SEND_WHATSAPP_LIST: str = "https://api.maravia.pe/servicio/n8n/ws_send_whatsapp_list.php"
URL_SEND_WHATSAPP_OFICIAL: str = "https://api.maravia.pe/servicio/n8n/ws_send_whatsapp_oficial.php"
# Id de empresa con credenciales WhatsApp para enviar listas (opcional). Si no se envía id_empresa_whatsapp en la request, se usa este.
_ID_EMPRESA_WA = os.getenv("ID_EMPRESA_WHATSAPP", "")
ID_EMPRESA_WHATSAPP: int | None = int(_ID_EMPRESA_WA) if _ID_EMPRESA_WA.isdigit() else None

# --- SUNAT / Login (token para CREAR_VENTA; no se usa token fijo en env) ---
URL_LOGIN: str = os.getenv("MARAVIA_URL_LOGIN", "https://api.maravia.pe/servicio/ws_login.php")
MARAVIA_USER: str = os.getenv("MARAVIA_USER", "")
MARAVIA_PASSWORD: str = os.getenv("MARAVIA_PASSWORD", "")

# --- Redis (cache alternativo) ---
# Por defecto "http" para desarrollo local sin Redis; en producción usar CACHE_BACKEND=redis en .env
CACHE_BACKEND: str = os.getenv("CACHE_BACKEND", "http")  # "http" | "redis"
# Por defecto localhost para desarrollo local; en Docker/producción definir REDIS_URL en .env
REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_TTL: int = int(os.getenv("REDIS_TTL", "86400"))
