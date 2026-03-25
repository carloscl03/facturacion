# MaravIA Bot — API de Registro Contable por WhatsApp

API REST construida con **FastAPI** que procesa mensajes de WhatsApp para registrar operaciones contables (ventas y compras) mediante inteligencia artificial (GPT-4.1-mini). Se integra con **N8N** como orquestador de flujos, una **API PHP** como backend de datos y **SUNAT** para emisión de comprobantes electrónicos.

---

## Tabla de contenidos

- [Arquitectura del proyecto](#arquitectura-del-proyecto)
- [Stack tecnológico](#stack-tecnológico)
- [Flujo de capas](#flujo-de-capas)
- [Máquina de estados (0 a 5)](#máquina-de-estados-0-a-5)
- [Flujo completo de una operación](#flujo-completo-de-una-operación)
- [Endpoints disponibles](#endpoints-disponibles)
- [Servicios principales](#servicios-principales)
- [Helpers y mappers](#helpers-y-mappers)
- [Repositorios](#repositorios)
- [Prompts (IA)](#prompts-ia)
- [APIs externas (PHP / N8N)](#apis-externas-php--n8n)
- [Estructura de datos en Redis](#estructura-de-datos-en-redis)
- [Reglas de negocio importantes](#reglas-de-negocio-importantes)
- [Tests](#tests)
- [Variables de entorno](#variables-de-entorno)
- [Ejecución local](#ejecución-local)
- [Ejecución con Docker](#ejecución-con-docker)
- [Archivos legacy](#archivos-legacy)

---

## Arquitectura del proyecto

Arquitectura limpia en capas con principios **SOLID**:

```
maravia-bot/
├── main.py                            # FastAPI app + registro de routers
├── config/
│   └── settings.py                    # URLs, tokens, env vars centralizadas
│
├── api/
│   ├── deps.py                        # Inyección de dependencias (Depends)
│   └── routes/                        # Thin controllers (solo delegan)
│       ├── extraccion.py              # POST /procesar-extraccion
│       ├── clasificador.py            # POST /clasificar-mensaje
│       ├── opciones.py                # POST /opciones
│       ├── confirmar_registro.py      # POST /confirmar-registro
│       ├── finalizar.py               # POST /finalizar-operacion
│       ├── identificador.py           # POST /identificar-entidad
│       ├── resumen.py                 # GET  /generar-resumen
│       ├── informador.py              # POST /informador
│       ├── casual.py                  # POST /casual
│       ├── preguntador.py             # POST /generar-pregunta | /preguntador
│       ├── iniciar.py                 # POST /iniciar-flujo
│       ├── eliminar.py                # POST /eliminar-operacion
│       └── unificado.py               # POST /unificado (legacy)
│
├── services/                          # Lógica de negocio
│   ├── ai_service.py                  # Abstract AIService + OpenAIService
│   ├── extraccion_service.py          # Servicio principal de extracción
│   ├── clasificador_service.py        # Clasifica intención del mensaje
│   ├── opciones_service.py            # Estado 4: sucursal, centro costo, forma pago
│   ├── confirmar_registro_service.py  # Transición estado 3 → 4
│   ├── finalizar_service.py           # Emite comprobante (SUNAT / compra)
│   ├── identificador_service.py       # Busca/crea cliente o proveedor
│   ├── resumen_service.py             # Genera resumen visual
│   ├── informador_service.py          # Responde preguntas de ayuda
│   ├── casual_service.py              # Saludo inicial + botones compra/venta
│   ├── preguntador_service.py         # Genera siguiente pregunta
│   ├── iniciar_service.py             # Crea registro inicial
│   ├── eliminar_service.py            # Elimina registro temporal
│   └── helpers/
│       ├── registro_domain.py         # Lógica de estados y validación
│       ├── opciones_domain.py         # Campos y orden del Estado 4
│       ├── productos.py               # Normalización de productos
│       ├── venta_mapper.py            # Payload para ws_venta.php
│       ├── compra_mapper.py           # Payload para ws_compra.php
│       ├── sunat_client.py            # Cliente SUNAT (login + emisión)
│       └── fechas.py                  # Conversión de fechas
│
├── prompts/                           # Construcción de prompts para IA
│   ├── plantillas.py                  # PLANTILLA_VISUAL + ESTRUCTURA_GUIA
│   ├── extraccion.py                  # Prompt de extracción de datos
│   ├── clasificador.py                # Prompt del clasificador/router
│   ├── informador.py                  # Prompt del informador
│   ├── resumen.py                     # Prompt del resumen
│   ├── preguntador.py                 # Prompt del preguntador
│   └── casual.py                      # Prompt del saludo casual
│
├── repositories/                      # Acceso a datos
│   ├── base.py                        # ABC CacheRepository
│   ├── cache_repository.py            # HttpCacheRepository (API PHP)
│   ├── redis_cache_repository.py      # RedisCacheRepository
│   ├── cache_factory.py               # Factory según CACHE_BACKEND
│   ├── entity_repository.py           # Clientes y proveedores
│   ├── informacion_repository.py      # Sucursales, formas/medios de pago
│   └── parametros_repository.py       # Centros de costo
│
├── test/                              # Tests de integración y unitarios
├── php/                               # Copias de referencia del backend PHP
└── docker-compose.yml
```

### Principios SOLID aplicados

| Principio | Implementación |
|-----------|----------------|
| **SRP** | Cada capa (route, service, prompt, repository) tiene una sola responsabilidad |
| **OCP** | `AIService` y `CacheRepository` son abstracciones extensibles sin modificar consumidores |
| **LSP** | `OpenAIService`, `HttpCacheRepository` y `RedisCacheRepository` son intercambiables |
| **ISP** | Cada ruta expone un contrato acotado; repositorios separados por dominio |
| **DIP** | Servicios reciben dependencias por constructor; rutas usan `Depends()` |

---

## Stack tecnológico

- **Python 3.11+**, FastAPI, Uvicorn
- **OpenAI GPT-4.1-mini** (vía `openai` SDK)
- **Redis** (caché principal en producción) / HTTP fallback (API PHP en dev)
- **Requests** (llamadas a APIs PHP externas)
- **python-dotenv** (variables de entorno)
- **Docker / Docker Compose** (despliegue)

---

## Flujo de capas

```
WhatsApp → N8N (orquestador)
                │  HTTP POST
                ▼
          api/routes/           ← Thin controllers
                │  Depends()
                ▼
          services/             ← Lógica de negocio
            ├── prompts/        ← Prompts para IA
            ├── ai_service      ← OpenAI GPT-4.1-mini
            └── repositories/   ← Acceso a datos
                  ├── Redis / HTTP Cache
                  ├── Entity (clientes/proveedores)
                  ├── Informacion (sucursales, pagos)
                  └── Parametros (centros de costo)
```

---

## Máquina de estados (0 a 5)

El campo `estado` en Redis controla en qué fase está cada operación:

| Estado | Significado | Condición de entrada |
|--------|-------------|----------------------|
| **0** | Sin tipo de operación | Registro creado, `operacion` vacío |
| **1** | Operación definida | `operacion` = venta/compra, al menos un dato |
| **2** | Datos parciales | Al menos un campo obligatorio lleno |
| **3** | Obligatorios completos | monto + entidad + tipo_documento + moneda + metodo_pago |
| **4** | Confirmado, eligiendo opciones | Usuario confirmó; elige sucursal, forma pago, centro costo |
| **5** | Opciones completas, listo para emitir | Usuario confirmó opciones; se procede a finalizar |

### Transiciones

```
Estado 0 → 1 → 2 → 3    ExtraccionService (calcula automáticamente)
Estado 3 → 4             ClasificadorService (detecta confirmación) → ConfirmarRegistroService
Estado 4                  OpcionesService (sucursal → centro_costo [compra] → forma_pago)
Estado 4 → 5             ClasificadorService (detecta segunda confirmación con opciones completas)
Estado 5 → finalizado    FinalizarService (emite comprobante, luego EliminarService borra registro)
```

### Confirmaciones (palabras clave)

Las mismas palabras aplican para ambas transiciones (3→4 y 4→5):
> sí, confirmo, dale, correcto, listo, ok, confirmar, de acuerdo, va, perfecto, adelante, acepto, vale, está bien, procede

### Reinicio por error

Si `FinalizarService` falla (error SUNAT o API), el estado se resetea a **3** para que el usuario pueda editar datos y volver a confirmar.

---

## Flujo completo de una operación

### 1. Primer mensaje (sin registro)

```
Usuario envía mensaje → ClasificadorService (sin IA, reglas directas)
  ├── Mensaje indica compra/venta o JSON → destino: extraccion
  └── Mensaje casual → destino: casual (saludo + botones Compra/Venta)
```

### 2. Extracción de datos (estados 0-3)

```
POST /procesar-extraccion
  1. Lee registro actual de Redis
  2. Construye prompt con estado actual + mensaje
  3. IA extrae datos → propuesta_cache
  4. Fusiona propuesta con datos existentes
  5. Si detecta RUC/DNI → IdentificadorService (busca o crea entidad)
  6. Calcula estado automáticamente (0-3)
  7. Persiste en Redis
  8. Retorna: resumen visual + diagnóstico de faltantes
```

El diagnóstico solo pregunta por campos **realmente vacíos**. Cuando todos los obligatorios están completos, muestra: *"¿Confirmar todo para continuar?"*

### 3. Confirmación (estado 3 → 4)

```
Usuario dice "confirmo" → ClasificadorService detecta confirmación
  → siguiente_estado = true, intencion = opciones
  → Escribe estado 4 en Redis
  → Orquestador llama a /opciones (get_next)
```

### 4. Opciones (estado 4)

El flujo de opciones presenta listas de WhatsApp en orden:

| Orden | Campo | Aplica a | Fuente |
|-------|-------|----------|--------|
| 1 | Sucursal | Venta y Compra | `ws_informacion_ia.php` (OBTENER_SUCURSALES) |
| 2 | Centro de costo | Solo Compra | `ws_parametros.php` (OBTENER_TABLAS_MAESTRAS) |
| 3 | Forma de pago | Venta y Compra | `ws_forma_pago.php` (LISTAR_FORMAS_PAGO) |

Cuando todas las opciones están completas, muestra: *"Por favor, bríndame una confirmación para continuar"*

### 5. Segunda confirmación (estado 4 → 5)

```
Usuario confirma → ClasificadorService detecta confirmación + opciones completas
  → siguiente_estado = true, intencion = finalizar
  → Escribe estado 5 en Redis
  → Orquestador llama a /finalizar-operacion
```

### 6. Finalización (estado 5)

```
POST /finalizar-operacion
  ├── Venta: venta_mapper → ws_venta.php (REGISTRAR_VENTA_N8N)
  │     ├── Éxito: envía texto + PDF por WhatsApp, elimina registro
  │     └── Error SUNAT: resetea a estado 3, envía mensaje de error
  │
  └── Compra: compra_mapper → ws_compra.php (REGISTRAR_COMPRA)
        ├── Éxito: envía texto por WhatsApp, elimina registro
        └── Error: resetea a estado 3, envía mensaje de error
```

---

## Endpoints disponibles

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/procesar-extraccion` | Extrae datos, identifica entidad, diagnostica faltantes, persiste en Redis |
| `POST` | `/clasificar-mensaje` | Clasifica intención: actualizar, opciones, resumen, finalizar, casual, eliminar |
| `POST` | `/opciones` | Estado 4: listas de sucursal, centro costo (compra), forma pago |
| `POST` | `/confirmar-registro` | Transición explícita estado 3 → 4 |
| `POST` | `/finalizar-operacion` | Emite comprobante (SUNAT para venta, API para compra) |
| `POST` | `/identificar-entidad` | Busca cliente/proveedor por RUC, DNI o nombre |
| `GET` | `/generar-resumen` | Resumen visual del estado actual |
| `POST` | `/informador` | Responde preguntas de ayuda sobre el registro |
| `POST` | `/casual` | Saludo inicial + botones Compra/Venta por WhatsApp |
| `POST` | `/generar-pregunta` | Genera siguiente pregunta contextualizada |
| `POST` | `/preguntador` | Síntesis + diagnóstico (obligatorios y opcionales) |
| `POST` | `/iniciar-flujo` | Crea registro inicial en Redis |
| `POST` | `/eliminar-operacion` | Elimina registro temporal completo |

Documentación interactiva: `http://localhost:3000/docs` | `http://localhost:3000/redoc`

---

## Servicios principales

### ExtraccionService

Servicio central del flujo. En una sola llamada:
- Extrae datos del mensaje usando IA
- Identifica entidades (RUC/DNI) vía `IdentificadorService`
- Calcula el estado (0-3) automáticamente
- Preserva campos de opciones y URL entre rondas
- Valida coherencia de fechas (fecha_pago >= fecha_emision)
- Recibe `url` como parámetro opcional y lo persiste en Redis

### ClasificadorService

Orquestador de intenciones:
- **Sin registro en Redis**: clasifica sin IA (reglas directas)
- **Con registro**: usa IA (`build_prompt_router`) + candados de servicio
- Gestiona transiciones 3→4 y 4→5 cuando detecta confirmación
- Candados: nunca devuelve `casual` si hay registro; `actualizar` solo en estado ≤ 3; `finalizar` solo en estado ≥ 5

### OpcionesService

Maneja la fase de opciones (estado 4):
- `get_next()`: devuelve la siguiente lista pendiente + payload para WhatsApp list
- `submit()`: matchea la selección del usuario con opciones en Redis (exacto → substring → IA → int)
- Guarda `opciones_actuales` en Redis para resolver mensajes de texto a IDs

### IdentificadorService

- `buscar()`: solo lectura, devuelve ficha de identificación
- `buscar_o_crear()`: si no existe, registra cliente (venta) o proveedor (compra)
- Maneja razón social (RUC/empresa), nombre completo (DNI/persona) y nombres+apellidos

### FinalizarService

- Valida campos obligatorios antes de emitir
- **Venta**: `construir_payload_venta_n8n()` → `ws_venta.php` → envía texto + PDF por WhatsApp
- **Compra**: `construir_payload_compra()` → `ws_compra.php` → envía texto por WhatsApp
- En error: resetea a estado 3 para que el usuario corrija y reintente

---

## Helpers y mappers

### registro_domain.py

Lógica de dominio para el registro:
- `calcular_estado()`: calcula estado 0-3 según campos completos
- `opciones_completas()`: verifica si sucursal + forma_pago están elegidos (+ centro_costo en compra)
- `normalizar_documento_entidad()`: valida DNI (8 dígitos) / RUC (11 dígitos); rechaza patrones serie-número (ej: F001-00001)
- `operacion_desde_registro()`: lee `operacion` o `cod_ope` del registro

### opciones_domain.py

- `CAMPOS_ESTADO2 = ("sucursal", "centro_costo", "forma_pago")`
- `siguiente_campo_pendiente()`: retorna el siguiente campo a elegir en orden; salta `centro_costo` en ventas

### venta_mapper.py

- `TIPO_DOCUMENTO_MAP`: factura=1, boleta=2, nota de venta=7, nota de compra=7
- `MONEDA_MAP`: PEN=1, USD=2
- `traducir_registro_a_parametros()`: convierte registro Redis → (operacion, params)
- `construir_payload_venta_n8n()`: arma JSON para `REGISTRAR_VENTA_N8N`
- Incluye `pdf_url` desde `reg.get("url")` para adjuntar documento

### compra_mapper.py

- `construir_payload_compra()`: arma JSON para `REGISTRAR_COMPRA`
- Incluye `enlace_documento` desde `reg.get("url")`
- Normaliza `tipo_compra`: "Contado" o "Crédito" (con tilde, requerido por PostgreSQL)

### productos.py

- Normaliza productos desde lista, JSON string o texto
- Calcula subtotal/IGV: `subtotal = total / 1.18`, `igv = total - subtotal`
- Para notas (venta/compra): IGV = 0, subtotal = 0

### sunat_client.py

- `login_maravia()`: obtiene JWT vía `ws_login.php`
- `SunatClient.crear_venta()`: POST a `ws_venta.php`, parsea respuesta SUNAT
- Extrae `pdf_url` de múltiples ubicaciones posibles en la respuesta

---

## Repositorios

### CacheRepository (ABC)

Interfaz abstracta con dos implementaciones:
- **`HttpCacheRepository`**: usa API PHP (`ws_historial_cache.php`). Default en desarrollo (`CACHE_BACKEND=http`).
- **`RedisCacheRepository`**: usa Redis directo con Hash + TTL. Producción (`CACHE_BACKEND=redis`).

Métodos: `consultar()`, `consultar_lista()`, `insertar()`, `actualizar()`, `eliminar()`, `upsert()`, `guardar_debug()`.

### EntityRepository

Gestiona clientes y proveedores vía API PHP:
- `buscar_cliente()` / `buscar_proveedor()`: búsqueda por RUC/DNI/nombre
- `registrar_cliente()` / `registrar_proveedor()`: alta con fallback de `id_tipo_documento`
- `registrar_compra()`: envía payload completo a `ws_compra.php`

### InformacionRepository

- `obtener_sucursales()`: desde `ws_informacion_ia.php`
- `obtener_formas_pago()`: desde `ws_forma_pago.php`
- `obtener_medios_pago_catalogo()`: desde `ws_medio_pago.php`

### ParametrosRepository

- `obtener_centros_costo()`: desde `ws_parametros.php` (solo compras)

---

## Prompts (IA)

Todos los prompts están en `prompts/` y son funciones que construyen el texto del prompt dinámicamente.

| Módulo | Función | Propósito |
|--------|---------|-----------|
| `extraccion.py` | `build_prompt_extractor()` | Extrae datos, genera resumen visual y diagnóstico de faltantes |
| `clasificador.py` | `build_prompt_router()` | Clasifica intención y detecta confirmaciones |
| `informador.py` | `build_prompt_info()` | Responde preguntas de ayuda del usuario |
| `resumen.py` | `build_prompt_resumen()` | Genera resumen auditado del registro |
| `preguntador.py` | `build_prompt_preguntador_v2()` | Genera preguntas separadas (obligatorias/opcionales) |
| `casual.py` | Prompt de saludo | Genera saludo contextual para primer mensaje |
| `plantillas.py` | `PLANTILLA_VISUAL` | Template visual compartido por todos los prompts |

### Plantilla visual (resumen dinámico)

Solo muestra líneas para campos con valor:

```
🛒 *COMPRA*  /  📤 *VENTA*
📄 *Factura* F001-00001
👤 *Cliente:* Empresa SAC
🆔 *RUC:* 20123456789
📦 *Detalle:* 2 x Producto — S/ 100.00
💰 Subtotal: S/ 84.75 | IGV: S/ 15.25 | *Total: S/ 100.00*
💵 *Moneda:* PEN
💳 *Método:* Contado
📅 *Emisión:* 25-03-2026
```

---

## APIs externas (PHP / N8N)

### Backend PHP (api.maravia.pe)

| Endpoint | Operaciones | Uso |
|----------|-------------|-----|
| `ws_historial_cache.php` | CONSULTAR/INSERTAR/ACTUALIZAR/ELIMINAR_CACHE | Caché HTTP (dev) |
| `ws_cliente.php` | BUSCAR_CLIENTE, REGISTRAR_CLIENTE | Gestión de clientes |
| `ws_proveedor.php` | BUSCAR_PROVEEDOR, REGISTRAR_PROVEEDOR_SIMPLE | Gestión de proveedores |
| `ws_venta.php` | REGISTRAR_VENTA_N8N | Registro de ventas + SUNAT |
| `ws_compra.php` | REGISTRAR_COMPRA | Registro de compras |
| `ws_informacion_ia.php` | OBTENER_SUCURSALES | Catálogos |
| `ws_parametros.php` | OBTENER_TABLAS_MAESTRAS | Centros de costo |
| `ws_login.php` | LOGIN | JWT para SUNAT |

### N8N Catálogos

| Endpoint | Operación |
|----------|-----------|
| `ws_forma_pago.php` | LISTAR_FORMAS_PAGO |
| `ws_medio_pago.php` | LISTAR_MEDIOS_PAGO |

### WhatsApp

| Endpoint | Tipo |
|----------|------|
| `ws_send_whatsapp_oficial.php` | Texto y documentos PDF |
| `ws_send_whatsapp_list.php` | Listas interactivas (opciones) |
| `ws_send_whatsapp_buttons.php` | Botones interactivos (Compra/Venta) |

**Nota sobre IDs**: `id_from` se usa para datos (cache, tablas, registro). `id_empresa` se usa para credenciales de WhatsApp. Son diferentes cuando la empresa de datos no coincide con la que tiene credenciales WhatsApp.

---

## Estructura de datos en Redis

Cada registro se identifica por `wa_id` + `id_from` y contiene:

```
estado                  int (0-5)
operacion               "venta" | "compra"
entidad_nombre          string (razón social o nombre)
entidad_numero          string (RUC 11 dígitos o DNI 8 dígitos)
entidad_id              int (ID maestro del cliente/proveedor)
tipo_documento          "factura" | "boleta" | "nota de venta" | "nota de compra"
numero_documento        string (serie-número: "F001-00001") — NO aplica en notas
moneda                  "PEN" | "USD"
metodo_pago             "contado" | "credito"
dias_credito            int (solo si credito: 15, 30, 45, 60, 90)
nro_cuotas              int (solo si credito: 1-24)
monto_total             float
monto_sin_igv           float (0 en notas)
igv                     float (0 en notas)
productos               JSON string
fecha_emision           "DD-MM-YYYY"
fecha_pago              "DD-MM-YYYY" (debe ser >= fecha_emision)
url                     string (URL de documento adjunto, persistente)
id_sucursal             int
sucursal                string (nombre)
id_centro_costo         int (solo compra)
id_forma_pago           int
forma_pago              string (nombre)
opciones_actuales       JSON (lista temporal para matchear selecciones)
ultima_pregunta         string (keyword del último campo preguntado)
identificado            bool
```

---

## Reglas de negocio importantes

### Notas de venta y compra

- **IGV**: no se calcula. `monto_sin_igv = 0`, `igv = 0`, `monto_total` es el dato principal.
- **Número de comprobante** (`numero_documento`): no aplica. Nunca se pregunta serie/número para notas.
- **Entidad**: si el monto es < S/ 700, el documento (RUC/DNI) es opcional.

### Método de pago

- Solo se pregunta si `metodo_pago` es null. Una vez definido ("contado" o "credito"), nunca se repregunta.
- `dias_credito` y `nro_cuotas` solo se preguntan cuando `metodo_pago = "credito"`. Si es "contado" o aún no definido, esas preguntas no existen.

### Regla 700 PEN

Para ventas en soles: si `monto_total < 700`, el documento de identidad (RUC/DNI) es opcional y puede ser nota de venta. Si `monto_total >= 700`, el documento es obligatorio.

### URL de documento adjunto

- Se recibe como parámetro opcional en `/procesar-extraccion` (campo `url`)
- Se persiste en Redis y se preserva entre rondas de extracción
- Se envía como `pdf_url` en ventas y `enlace_documento` en compras
- Solo se elimina cuando se borra el registro completo (`EliminarService`)

### Normalización de documentos

`normalizar_documento_entidad()` rechaza patrones de serie-número (ej: `EB01-4`, `F001-00005678`) para evitar confundir el número de comprobante con el DNI/RUC del cliente.

---

## Tests

Los tests están en `test/` y se ejecutan directamente contra las APIs PHP o como tests unitarios locales.

### Tests de APIs externas (integración)

| Test | Descripción |
|------|-------------|
| `test_registro.py` | Registra compra completa en `ws_compra.php` |
| `test_pdf_sunat.py` | Registra venta (nota) en `ws_venta.php` |
| `test_nota_venta.py` | Nota de venta con payload mínimo |
| `test_nota_compra.py` | Nota de compra con payload mínimo |
| `test_nota_docu.py` | Nota de venta/compra sin entidad, monto < 700 |
| `test_url.py` | Verifica que `pdf_url` (venta) y `enlace_documento` (compra) se acepten |
| `test_cliente.py` | Búsqueda de clientes |
| `test_cliente_obtener_o_crear.py` | Buscar o registrar cliente idempotente |
| `test_proveedor_obtener_o_registrar.py` | Registrar proveedor |
| `test_proveedor_obtener_o_crear.py` | Buscar o registrar proveedor idempotente |
| `test_validar_ids_venta.py` | Compatibilidad de IDs tipo documento en venta |
| `test_validar_ids_compra.py` | Compatibilidad de IDs tipo documento en compra |
| `test_obtener_pagos.py` | Lista métodos de pago desde API |
| `test_inventario.py` | Consulta catálogo público |

### Tests de servicios (unitarios/locales)

| Test | Descripción |
|------|-------------|
| `test_helpers_domain.py` | Funciones de `registro_domain`, `opciones_domain`, `productos`, `venta_mapper` |
| `test_opciones_service_unit.py` | OpcionesService con APIs reales pero sin servidor FastAPI |
| `test_sunat_payload_contracts_debug.py` | Valida contratos de payload SUNAT |

### Tests de infraestructura

| Test | Descripción |
|------|-------------|
| `test_redis.py` | Conexión y operaciones Redis |
| `test_leer_historial.py` | Lectura de caché HTTP |
| `test_actualizar_historial.py` | Actualización de caché HTTP |
| `test_conexion.py` | Conexión con OpenAI |

### Tests de WhatsApp

| Test | Descripción |
|------|-------------|
| `test_pdf_wsp.py` | Envío de PDF por WhatsApp |
| `test_whatsapp_buttons.py` | Envío de botones interactivos |
| `test_opciones.py` | Flujo completo de listas WhatsApp |

### Ejecución

```bash
# Test individual
python test/test_url.py

# Con pytest
pytest test/test_helpers_domain.py -v
```

---

## Variables de entorno

Crear `.env` en la raíz (copiar desde `.env.example`):

```env
# Obligatorias
OPENAI_API_KEY=sk-...              # API Key de OpenAI

# Cache backend
CACHE_BACKEND=http                  # "http" (dev, default) o "redis" (producción)
REDIS_URL=redis://127.0.0.1:6379/0 # URL de Redis (solo si CACHE_BACKEND=redis)
REDIS_TTL=86400                     # TTL en segundos (default: 24h)

# SUNAT (opcional, para emisión de comprobantes)
MARAVIA_USER=...                    # Usuario para login SUNAT
MARAVIA_PASSWORD=...                # Password para login SUNAT
TOKEN_SUNAT=...                     # Token Bearer directo (alternativa al login)

# WhatsApp (opcional)
ID_EMPRESA_WHATSAPP=1               # ID empresa con credenciales WhatsApp

# IA
MODELO_IA=gpt-4.1-mini             # Modelo OpenAI (default: gpt-4.1-mini)
```

Las URLs de las APIs PHP están centralizadas en `config/settings.py` y se pueden sobreescribir con variables de entorno.

---

## Ejecución local

### Requisitos

- Python 3.11+
- pip

### Pasos

```bash
# 1. Clonar e ingresar
git clone <url-del-repo>
cd maravia-bot

# 2. Entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/macOS

# 3. Dependencias
pip install -r requirements.txt
# o manualmente:
pip install fastapi uvicorn openai requests python-dotenv redis

# 4. Configurar
cp .env.example .env
# Editar .env con valores reales

# 5. Ejecutar
uvicorn main:app --host 0.0.0.0 --port 3000 --reload

# 6. Verificar
# http://localhost:3000/docs
```

---

## Ejecución con Docker

```bash
# Preparar .env
cp .env.example .env

# Construir y levantar
docker-compose up --build -d

# Verificar
docker-compose ps
docker-compose logs -f

# Comandos útiles
docker-compose down              # Detener
docker-compose restart api-maravia  # Reiniciar
docker-compose up --build -d     # Reconstruir
```

---

## Archivos legacy

Se conservan como referencia pero no forman parte del flujo activo:

| Archivo | Reemplazado por |
|---------|-----------------|
| `services/legacy/analizador_service.py` | `ExtraccionService` |
| `services/legacy/confirmador_service.py` | `ExtraccionService` |
| `services/legacy/registrador_service.py` | Escritura directa a Redis |
| `config/estados.py` | Campo `estado` (0-5) en `registro_domain.py` |
| `prompts/analizador.py` | `prompts/extraccion.py` |
| `main_cache.py` | Monolito original, solo referencia histórica |

---

## Carpeta php/

Contiene copias en `.txt` del código PHP del backend como referencia:

- `ventan8n.txt` — `ws_venta.php` (registro de ventas + SUNAT)
- `compras.txt` — `ws_compra.php` (registro de compras)
- `busqueda de producto.txt` — Consulta de inventario
