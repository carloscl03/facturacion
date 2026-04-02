# Repositorios — Acceso a Datos

Capa de abstracción que encapsula toda comunicación con almacenamiento (Redis/HTTP) y APIs PHP externas.

---

## Arquitectura

```
CacheRepository (ABC)
    ├── HttpCacheRepository    → ws_historial_cache.php (dev)
    └── RedisCacheRepository   → Redis directo (producción)

EntityRepository               → ws_cliente.php, ws_proveedor.php, ws_compra.php
InformacionRepository          → ws_informacion_ia.php, ws_forma_pago.php, ws_medio_pago.php
ParametrosRepository           → ws_parametros.php
```

La selección del backend de caché se hace con la variable `CACHE_BACKEND` (`http` o `redis`).

---

## base.py — CacheRepository (ABC)

Interfaz abstracta que define el contrato para almacenamiento temporal de registros.

### Métodos abstractos

| Método | Firma | Descripción |
|--------|-------|-------------|
| `consultar` | `(wa_id, id_from) → dict \| None` | Lee un registro |
| `consultar_lista` | `(wa_id, id_from) → list` | Lee como lista (para ExtraccionService) |
| `insertar` | `(wa_id, id_from, data) → dict` | Crea registro nuevo |
| `actualizar` | `(wa_id, id_from, data) → dict` | Actualiza campos existentes |
| `eliminar` | `(wa_id, id_from) → dict` | Borra registro completo |
| `upsert` | `(wa_id, id_from, data, es_nuevo) → dict` | Inserta o actualiza |

### Métodos opcionales (debug)

| Método | Descripción |
|--------|-------------|
| `guardar_debug(wa_id, id_from, clave, data)` | Guarda info de debug por clave |
| `consultar_debug(wa_id, id_from)` | Lee toda la info de debug |
| `limpiar_debug(wa_id, id_from)` | Borra info de debug |

---

## cache_repository.py — HttpCacheRepository

Backend de desarrollo. Comunica con la API PHP `ws_historial_cache.php`.

### Operaciones (codOpe)

| codOpe | Método | Descripción |
|--------|--------|-------------|
| `CONSULTAR_CACHE` | `consultar()` | Busca por wa_id + id_from |
| `INSERTAR_CACHE` | `insertar()` | Crea nuevo registro |
| `ACTUALIZAR_CACHE` | `actualizar()` | Actualiza campos |
| `ELIMINAR_CACHE` | `eliminar()` | Borra registro |

### Payload de ejemplo

```json
{
    "codOpe": "CONSULTAR_CACHE",
    "wa_id": "51999999999",
    "id_from": 2
}
```

---

## redis_cache_repository.py — RedisCacheRepository

Backend de producción. Usa Redis Hash directamente.

### Almacenamiento

- **Clave Redis:** `cache:{wa_id}:{id_from}`
- **Tipo:** Hash (cada campo del registro es un field del hash)
- **TTL:** configurable (default: 86400s = 24h)

### Serialización

- **Escritura:** listas y dicts se serializan a JSON string; otros valores como string
- **Lectura:** intenta parsear JSON, luego float, luego int; si falla, deja como string

### Debug

- **Clave debug:** `debug:{wa_id}:{id_from}`
- Almacena info de extracción y registro como JSON en fields del hash

---

## Selección del backend (deps.py)

```python
def get_cache_repo():
    if settings.CACHE_BACKEND == "redis":
        return RedisCacheRepository(url=settings.REDIS_URL, ttl=settings.REDIS_TTL)
    return HttpCacheRepository()
```

Variable de entorno: `CACHE_BACKEND=redis` (producción) o `CACHE_BACKEND=http` (desarrollo, default).

---

## entity_repository.py — EntityRepository

Gestiona clientes y proveedores via APIs PHP.

### Métodos

| Método | API | codOpe | Descripción |
|--------|-----|--------|-------------|
| `buscar_cliente(id_from, termino)` | `ws_cliente.php` | `BUSCAR_CLIENTE` | Busca por RUC/DNI/nombre |
| `buscar_proveedor(id_from, termino)` | `ws_proveedor.php` | `BUSCAR_PROVEEDOR` | Busca por RUC/DNI/nombre |
| `registrar_cliente(datos, id_from)` | `ws_cliente.php` | `REGISTRAR_CLIENTE` | Alta de cliente |
| `registrar_proveedor(datos, id_from)` | `ws_proveedor.php` | `REGISTRAR_PROVEEDOR_SIMPLE` | Alta de proveedor |
| `registrar_compra(payload)` | `ws_compra.php` | `REGISTRAR_COMPRA` | Registra compra completa |

### Lógica de id_tipo_documento (fallback)

Al registrar cliente/proveedor, se determina el tipo de documento:

```
DNI (8 dígitos)  → intenta id_tipo_documento = 1
                   si falla → intenta id_tipo_documento = 4 (fallback)

RUC (11 dígitos) → intenta id_tipo_documento = 6
                   si falla → intenta id_tipo_documento = 4 (fallback)

Otro             → id_tipo_documento = 4
```

---

## informacion_repository.py — InformacionRepository

Catálogos de información para el flujo de opciones.

### Métodos

| Método | API | codOpe / Endpoint | Descripción |
|--------|-----|--------|-------------|
| `obtener_sucursales(id_from)` | `ws_informacion_ia.php` | `OBTENER_SUCURSALES` | Lista sucursales de la empresa |
| `obtener_sucursales_publicas()` | `ws_informacion_ia.php` | `OBTENER_SUCURSALES_PUBLICAS` | Sucursales públicas |
| `obtener_formas_pago()` | `ws_forma_pago.php` | `LISTAR_FORMAS_PAGO` | Formas de pago (N8N) |
| `obtener_medios_pago_catalogo()` | `ws_medio_pago.php` | `LISTAR_MEDIOS_PAGO` | Medios de pago (N8N) |
| `buscar_catalogo(id_empresa, nombre)` | `ws_obtenerCatalogo.php` | GET con params | Busca productos por nombre. Retorna id, nombre, sku, precio, unidad, stock |

---

## parametros_repository.py — ParametrosRepository

Tablas maestras adicionales.

### Métodos

| Método | API | codOpe | Descripción |
|--------|-----|--------|-------------|
| `obtener_centros_costo(wa_id)` | `ws_parametros.php` | `OBTENER_TABLAS_MAESTRAS` | Centros de costo (solo compras) |

---

## Repositorio → Servicio

| Repositorio | Servicios que lo usan |
|-------------|----------------------|
| `CacheRepository` | ExtraccionService, ClasificadorService, OpcionesService, ConfirmarRegistroService, FinalizarService, ResumenService, InformadorService, PreguntadorService, IniciarService, EliminarService, IdentificadorService |
| `EntityRepository` | IdentificadorService, FinalizarService |
| `InformacionRepository` | OpcionesService, ExtraccionService (catálogo de productos) |
| `ParametrosRepository` | OpcionesService |
