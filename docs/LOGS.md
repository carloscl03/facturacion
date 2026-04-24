# Sistema de logs del bot

El bot tiene **dos sistemas de logs complementarios**. Este documento lista todos los comandos listos para copiar y pegar.

- [1. Logs stdout (efímeros)](#1-logs-stdout-efímeros) — pasos internos del bot, `docker logs`
- [2. bot_api_log (persistentes)](#2-bot_api_log-persistentes) — llamadas a venta/compra/SUNAT, CLI `ver_logs.py`
- [3. Cuándo usar cada uno](#3-cuándo-usar-cada-uno)

---

## 1. Logs stdout (efímeros)

Salen por stdout del contenedor en formato JSON (una línea por evento). Viven mientras el contenedor corre — se pierden al reiniciar.

### 1.1 Ver logs desde el panel de EasyPanel (más común)

En el panel web de EasyPanel:
1. Entra al proyecto del bot
2. Clic en el servicio
3. Pestaña **"Logs"**

Ahí se ven en vivo, sin necesidad de saber el `container_id`.

### 1.2 Ver logs por Docker (SOLO desde el HOST de EasyPanel)

> ⚠️ **Importante:** estos comandos NO funcionan desde dentro del contenedor (cuando ves `root@f4db0e9faf0b:/app#` estás DENTRO y no tienes acceso al daemon Docker). Tienen que ejecutarse por SSH en el **servidor físico** donde corre EasyPanel.
>
> Si solo tienes acceso al contenedor, **usa el panel web** (sección 1.1) o el **CLI persistente** (sección 2).

Primero, conectándote por SSH al host, obtén el nombre del contenedor:

```bash
docker ps | grep maravia
```

El nombre del contenedor del bot es **`maravia/facturacion`** (o similar — verifica con `docker ps`). Comandos hardcodeados:

```bash
# Últimas 200 líneas
docker logs --tail 200 maravia/facturacion

# Seguir en vivo (tail -f)
docker logs -f maravia/facturacion

# Con timestamps del sistema
docker logs -f -t maravia/facturacion

# Últimos 15 minutos
docker logs --since 15m maravia/facturacion

# Desde una fecha específica
docker logs --since 2026-04-24T10:00:00 maravia/facturacion
```

### 1.3 Filtros con `grep` y `jq` (desde el HOST, no desde dentro)

```bash
# Solo errores
docker logs maravia/facturacion 2>&1 | grep '"level": "ERROR"'

# Solo warnings
docker logs maravia/facturacion 2>&1 | grep '"level": "WARNING"'

# Todo lo de un usuario específico
docker logs maravia/facturacion 2>&1 | grep '"wa_id": "51987654321"'

# Solo eventos de finalización (SUNAT/compra)
docker logs maravia/facturacion 2>&1 | grep '"logger": "maravia.finalizar"'

# Solo eventos de extracción IA
docker logs maravia/facturacion 2>&1 | grep '"logger": "maravia.extraccion"'

# Errores de un usuario específico (combinando)
docker logs maravia/facturacion 2>&1 | grep '"wa_id": "51987654321"' | grep '"level": "ERROR"'

# Pretty-print con jq
docker logs maravia/facturacion 2>&1 | grep '"level": "ERROR"' | jq .

# Solo el mensaje + wa_id + error
docker logs maravia/facturacion 2>&1 | grep '"level": "ERROR"' | jq '{ts, msg, wa_id, error}'

# Contar errores por tipo
docker logs maravia/facturacion 2>&1 | grep '"level": "ERROR"' | jq -r .msg | sort | uniq -c | sort -rn
```

### 1.4 Eventos clave que puedes filtrar

| Logger | Evento | Significa |
|---|---|---|
| `maravia.finalizar` | `sunat_ok`, `sunat_error` | Resultado del POST a ws_venta.php |
| `maravia.finalizar` | `compra_ok`, `compra_error` | Resultado del POST a ws_compra.php |
| `maravia.extraccion` | `extraccion_resultado` | Qué extrajo la IA del mensaje |
| `maravia.extraccion` | `ia_extraccion_error` | Fallo de OpenAI |
| `maravia.clasificador` | `clasificador_decision` | Qué destino eligió el clasificador |
| `maravia.clasificador` | `transicion_estado` | Cambios de estado (3→4, 4→5) |
| `maravia.opciones` | `opciones_campo_guardado` | Sucursal/forma de pago confirmada |
| `maravia.identificador` | `identificador_ok` | Cliente/proveedor identificado |
| `maravia.iniciar` | `iniciar_error_backend` | Fallo al iniciar nueva operación |
| `maravia.whatsapp` | `wa_texto_error`, `wa_pdf_error` | Fallo al enviar mensaje WhatsApp |
| `maravia.cache` | `cache_actualizar`, `cache_eliminar` | Operaciones Redis |
| `maravia.bot_api_log` | `bot_api_log_ok`, `bot_api_log_http_error` | Resultado de escribir en bot_api_log |

Ejemplo de un `extraccion_resultado`:

```json
{
  "ts": "2026-04-24T17:47:59Z",
  "level": "INFO",
  "logger": "maravia.extraccion",
  "msg": "extraccion_resultado",
  "wa_id": "51987654321",
  "id_from": 3,
  "operacion": "venta",
  "monto_total": 118.0,
  "moneda": "PEN",
  "entidad_nombre": "TAMBO SAC",
  "n_productos": 2,
  "estado_prev": 1,
  "estado_nuevo": 3,
  "listo_para_finalizar": true
}
```

---

## 2. bot_api_log (persistentes)

Tabla Postgres con una fila por cada llamada del bot a las APIs externas (ws_venta.php, ws_compra.php, SUNAT). Incluye el payload completo y la respuesta.

### 2.1 CLI básico

```bash
# Últimos 20 logs (resumen tabular)
python scripts/ver_logs.py

# Últimos 50
python scripts/ver_logs.py --limite 50

# Paginación
python scripts/ver_logs.py --limite 50 --pagina 2
```

### 2.2 Filtros por resultado y tipo de falla

```bash
# Solo fallidos
python scripts/ver_logs.py --resultado fallido

# Solo exitosos
python scripts/ver_logs.py --resultado exitoso

# Fallidos por stock insuficiente
python scripts/ver_logs.py --tipo-falla stock_insuficiente

# Fallidos por timeout
python scripts/ver_logs.py --tipo-falla timeout

# Fallidos por rechazo SUNAT
python scripts/ver_logs.py --tipo-falla sunat_rechazo

# Fallidos por credenciales mal configuradas
python scripts/ver_logs.py --tipo-falla credenciales_invalidas

# Fallidos por payload inválido
python scripts/ver_logs.py --tipo-falla payload_invalido
```

**Valores válidos de `--tipo-falla`:** `timeout`, `http_error`, `api_error`, `sunat_rechazo`, `moneda_invalida`, `sin_productos`, `producto_no_encontrado`, `stock_insuficiente`, `credenciales_invalidas`, `payload_invalido`, `error_sql`, `error_desconocido`.

### 2.3 Filtros por identidad

```bash
# Por wa_id (número WhatsApp)
python scripts/ver_logs.py --wa-id 51987654321

# Por id_from (empresa)
python scripts/ver_logs.py --id-from 3

# Por id_empresa (credenciales WhatsApp)
python scripts/ver_logs.py --id-empresa 1

# Combinados
python scripts/ver_logs.py --wa-id 51987654321 --resultado fallido
```

### 2.4 Filtros por tipo de operación

```bash
# Solo ventas
python scripts/ver_logs.py --operacion venta

# Solo compras
python scripts/ver_logs.py --operacion compra

# Solo llamadas a ws_venta.php
python scripts/ver_logs.py --api php_venta

# Solo llamadas a ws_compra.php
python scripts/ver_logs.py --api php_compra

# Solo llamadas directas a SUNAT
python scripts/ver_logs.py --api sunat
```

### 2.5 Filtros por fecha

```bash
# De hoy
python scripts/ver_logs.py --desde hoy

# De ayer
python scripts/ver_logs.py --desde ayer --hasta ayer

# Últimos 7 días
python scripts/ver_logs.py --desde hace-7d

# Rango específico
python scripts/ver_logs.py --desde 2026-04-01 --hasta 2026-04-24

# Últimos 30 días de fallidos
python scripts/ver_logs.py --desde hace-30d --resultado fallido
```

### 2.6 Búsqueda de texto libre

```bash
# Buscar por nombre de entidad (cliente/proveedor)
python scripts/ver_logs.py --buscar "TAMBO"

# Combinado con otros filtros
python scripts/ver_logs.py --buscar "TAMBO" --resultado fallido
```

### 2.7 Detalle completo de un log específico

```bash
# Cabecera + negocio + resultado + productos
python scripts/ver_logs.py --id 42

# Con payload enviado y respuesta JSON completos
python scripts/ver_logs.py --id 42 --raw
```

### 2.8 Modo follow (tail -f sobre la BD)

```bash
# Polling cada 5 segundos (default)
python scripts/ver_logs.py --follow

# Polling cada 2 segundos
python scripts/ver_logs.py --follow --interval 2

# Polling cada 30 segundos (baja carga)
python scripts/ver_logs.py --follow --interval 30
```

### 2.9 Sin colores (para pipes y scripts)

```bash
python scripts/ver_logs.py --no-color

# Guardar resultado en archivo
python scripts/ver_logs.py --resultado fallido --no-color > fallidos.txt
```

### 2.10 Override de URL

```bash
# Default: https://api.maravia.pe/servicio/ws_bot_api_log.php
# (o la env var URL_BOT_API_LOG)

# Contra local
python scripts/ver_logs.py --url http://localhost/maravia/servicio/ws_bot_api_log.php

# Por env var
export URL_BOT_API_LOG="http://localhost/maravia/servicio/ws_bot_api_log.php"
python scripts/ver_logs.py
```

### 2.11 Comandos API directos con curl

Si no tienes Python a mano, puedes llamar la API directamente:

```bash
# Listar últimos 20
curl -s -X POST https://api.maravia.pe/servicio/ws_bot_api_log.php \
  -H "Content-Type: application/json" \
  -d '{"codOpe": "LISTAR_BOT_API_LOG", "pagina": 1, "limite": 20}' | jq .

# Solo fallidos
curl -s -X POST https://api.maravia.pe/servicio/ws_bot_api_log.php \
  -H "Content-Type: application/json" \
  -d '{"codOpe": "LISTAR_BOT_API_LOG", "resultado": "fallido", "limite": 50}' | jq .

# Detalle de un log
curl -s -X POST https://api.maravia.pe/servicio/ws_bot_api_log.php \
  -H "Content-Type: application/json" \
  -d '{"codOpe": "OBTENER_BOT_API_LOG", "id": 42}' | jq .

# Items de un log
curl -s -X POST https://api.maravia.pe/servicio/ws_bot_api_log.php \
  -H "Content-Type: application/json" \
  -d '{"codOpe": "LISTAR_BOT_API_LOG_DETALLE", "log_id": 42}' | jq .
```

---

## 3. Cuándo usar cada uno

| Escenario | Herramienta |
|---|---|
| El usuario se queja de un comprobante mal emitido (hace días) | `bot_api_log` — `ver_logs.py --wa-id <num> --desde <fecha>` |
| Quiero ver exactamente qué se mandó a SUNAT para el caso X | `bot_api_log` — `ver_logs.py --id X --raw` |
| El bot no está respondiendo ahora a un usuario | `stdout` — `docker logs -f <c>` con `grep <wa_id>` |
| ¿Por qué el bot saltó a estado 4 si faltaban datos? | `stdout` — filtrar por `maravia.clasificador` y `transicion_estado` |
| Reporte de fallas por tipo (últimos 30 días) | `bot_api_log` — `ver_logs.py --desde hace-30d --resultado fallido` |
| Un cálculo de IGV salió raro | `stdout` — filtrar por `maravia.extraccion` y `extraccion_resultado` (es efímero, hay que verlo pronto) |
| Auditoría: ¿qué facturas se emitieron para cliente X? | `bot_api_log` — `ver_logs.py --buscar "<razon_social>" --resultado exitoso` |
| Monitorear en vivo las finalizaciones | `bot_api_log` — `ver_logs.py --follow` |
| Monitorear en vivo toda la conversación (todos los pasos) | `stdout` — `docker logs -f <c>` |

---

## Limitaciones conocidas

### Gap: bugs de lógica antes de finalizar

`bot_api_log` solo captura el momento en que el bot llama a la API externa (estado 5). Si el bug está en la **extracción de datos**, el **cálculo de IGV**, el **clasificador** o la **máquina de estados**, solo lo ves en los logs stdout — que son efímeros.

Solución parcial: cuando investigues un log fallido con `--raw`, revisa el campo `metadata`. Si no tiene el snapshot del Redis, el caso ya no es reconstruible.

### Los logs stdout se pierden al reiniciar

Si reinicias el contenedor o rota la política de logs de Docker, los logs stdout se van. Para un caso que no quedó en `bot_api_log`, la investigación se complica.

Solución a futuro: configurar un driver de logs persistente (CloudWatch, Loki, o una tabla `bot_event_log` separada).
