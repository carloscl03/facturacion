# Configuración

## settings.py — Variables centralizadas

Todas las configuraciones se leen de variables de entorno (con defaults). Se acceden via `from config import settings`.

---

### IA (OpenAI)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | API Key de OpenAI (obligatoria) |
| `MODELO_IA` | `"gpt-4.1-mini"` | Modelo de IA a usar |

### Backend de caché

| Variable | Default | Descripción |
|----------|---------|-------------|
| `CACHE_BACKEND` | `"http"` | `"http"` (API PHP) o `"redis"` (Redis directo) |
| `REDIS_URL` | `"redis://127.0.0.1:6379/0"` | URL de conexión Redis |
| `REDIS_TTL` | `86400` | TTL en segundos (24 horas) |

### Cambiar entre HTTP y Redis

```bash
# Desarrollo (default): usa API PHP como caché
CACHE_BACKEND=http

# Producción: usa Redis directo
CACHE_BACKEND=redis
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_TTL=86400
```

La selección se hace en `api/deps.py`:
```python
def get_cache_repo():
    if settings.CACHE_BACKEND == "redis":
        return RedisCacheRepository(url=settings.REDIS_URL, ttl=settings.REDIS_TTL)
    return HttpCacheRepository()
```

### URLs de APIs PHP

| Variable | Default | Endpoint |
|----------|---------|----------|
| `URL_HISTORIAL_CACHE` | `https://api.maravia.pe/.../ws_historial_cache.php` | Caché HTTP |
| `URL_CLIENTE` | `https://api.maravia.pe/.../ws_cliente.php` | Clientes |
| `URL_PROVEEDOR` | `https://api.maravia.pe/.../ws_proveedor.php` | Proveedores |
| `URL_VENTA_SUNAT` | `https://api.maravia.pe/.../ws_venta.php` | Ventas (N8N) |
| `URL_COMPRA` | `https://api.maravia.pe/.../ws_compra.php` | Compras |
| `URL_INFORMACION` | `https://api.maravia.pe/.../ws_informacion_ia.php` | Sucursales, catálogos |
| `URL_PARAMETROS` | `https://api.maravia.pe/.../ws_parametros.php` | Tablas maestras |
| `URL_FORMA_PAGO` | `https://api.maravia.pe/.../ws_forma_pago.php` | Formas de pago (N8N) |
| `URL_MEDIO_PAGO` | `https://api.maravia.pe/.../ws_medio_pago.php` | Medios de pago (N8N) |
| `URL_LOGIN` | `https://api.maravia.pe/.../ws_login.php` | Login SUNAT |

### URLs de WhatsApp

| Variable | Default | Descripción |
|----------|---------|-------------|
| `URL_SEND_WHATSAPP_OFICIAL` | `https://api.maravia.pe/.../ws_send_whatsapp_oficial.php` | Texto y PDF |
| `URL_SEND_WHATSAPP_LIST` | `https://api.maravia.pe/.../ws_send_whatsapp_list.php` | Listas interactivas |
| `URL_SEND_WHATSAPP_BUTTONS` | `https://api.maravia.pe/.../ws_send_whatsapp_buttons.php` | Botones |

### SUNAT

| Variable | Default | Descripción |
|----------|---------|-------------|
| `MARAVIA_USER` | — | Usuario para login SUNAT |
| `MARAVIA_PASSWORD` | — | Password para login SUNAT |
| `TOKEN_SUNAT` | — | Token Bearer directo (alternativa al login) |

### WhatsApp

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ID_EMPRESA_WHATSAPP` | `None` | ID empresa con credenciales WhatsApp (fallback) |

---

## Ejemplo completo de .env

```env
# === IA ===
OPENAI_API_KEY=sk-...

# === Cache ===
CACHE_BACKEND=redis
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_TTL=86400

# === SUNAT ===
MARAVIA_USER=usuario@empresa.pe
MARAVIA_PASSWORD=contraseña
TOKEN_SUNAT=eyJ...

# === WhatsApp ===
ID_EMPRESA_WHATSAPP=1

# === Modelo IA (opcional) ===
MODELO_IA=gpt-4.1-mini
```

---

## estados.py — DEPRECADO

El archivo `config/estados.py` contiene un enum legacy con constantes como `INICIAL`, `PENDIENTE_ENTIDAD`, etc.

**Ya no se usa.** Fue reemplazado por el campo `estado` (0-5) gestionado en `services/helpers/registro_domain.py`.

No eliminar por compatibilidad histórica, pero no importar ni usar en código nuevo.

---

## Flujo de configuración

```
.env → settings.py → deps.py (Depends) → services/routes
```

1. Variables de entorno se leen en `settings.py` con defaults
2. `deps.py` usa `settings` para construir instancias de repositorios y servicios
3. Las rutas FastAPI reciben las dependencias via `Depends(get_cache_repo)`, etc.
