# MaravIA Bot — API de Registro Contable por WhatsApp

API REST construida con **FastAPI** que procesa mensajes de WhatsApp para registrar operaciones contables (ventas y compras) mediante inteligencia artificial (GPT-4.1-mini). Se integra con N8N como orquestador de flujos y con una API PHP como backend de persistencia.

---

## Tabla de contenidos

- [Arquitectura del proyecto](#arquitectura-del-proyecto)
- [Flujo de capas](#flujo-de-capas)
- [Flujo actual de datos](#flujo-actual-de-datos)
- [Endpoints disponibles](#endpoints-disponibles)
- [Variables de entorno](#variables-de-entorno)
- [Ejecución en modo local (desarrollo)](#ejecución-en-modo-local-desarrollo)
- [Ejecución en producción con Docker](#ejecución-en-producción-con-docker)

---

## Arquitectura del proyecto

El proyecto sigue una arquitectura limpia en capas aplicando los principios **SOLID**.

```
maravia-bot/
├── main.py                        # Punto de entrada: instancia FastAPI + registra routers
│
├── config/
│   └── settings.py                # Centraliza URLs, tokens y variables de entorno (DIP)
│
├── prompts/
│   ├── plantillas.py              # PLANTILLA_VISUAL y REGLAS_NORMALIZACION compartidas
│   ├── extraccion.py              # build_prompt_extractor(...) — prompt unificado (extracción + diagnóstico)
│   ├── preguntador.py             # build_prompt_pregunta(...) y build_prompt_preguntador_v2(...)
│   ├── clasificador.py            # build_prompt_router(...)
│   ├── informador.py              # build_prompt_info(...)
│   └── resumen.py                 # build_prompt_resumen(...)
│
├── repositories/
│   ├── base.py                    # Clase abstracta CacheRepository (ABC)
│   ├── cache_repository.py        # HttpCacheRepository — acceso a la API PHP de caché
│   └── entity_repository.py       # EntityRepository — acceso a clientes y proveedores
│
├── services/
│   ├── ai_service.py              # Clase abstracta AIService + OpenAIService
│   ├── extraccion_service.py      # Servicio principal: extrae datos, identifica entidad, genera diagnóstico, persiste
│   ├── preguntador_service.py     # Genera la siguiente pregunta contextualizada (standalone)
│   ├── clasificador_service.py    # Clasifica la intención del mensaje
│   ├── informador_service.py      # Responde preguntas de ayuda de llenado
│   ├── resumen_service.py         # Genera resumen del estado actual
│   ├── identificador_service.py   # Busca y confirma cliente/proveedor (método buscar() solo lectura)
│   ├── finalizar_service.py       # Emite el comprobante en SUNAT
│   ├── iniciar_service.py         # Inicia un nuevo flujo de registro
│   └── opciones_service.py        # Estado 2: listas de sucursal, forma de pago, método de pago
│
└── api/
    ├── deps.py                    # Factories de dependencias para FastAPI Depends()
    └── routes/
        ├── extraccion.py          # POST /procesar-extraccion (endpoint principal)
        ├── preguntador.py         # POST /generar-pregunta  |  POST /preguntador
        ├── clasificador.py        # POST /clasificar-mensaje
        ├── informador.py          # POST /informador
        ├── resumen.py             # GET  /generar-resumen
        ├── identificador.py       # POST /identificar-entidad
        ├── eliminar.py            # POST /eliminar-operacion
        ├── finalizar.py           # POST /finalizar-operacion
        ├── iniciar.py             # POST /iniciar-flujo
        └── opciones.py            # POST /opciones (Estado 2: sucursal, forma de pago, método de pago)
```

### Principios SOLID aplicados

| Principio | Implementación |
|-----------|----------------|
| **SRP** — Responsabilidad única | Cada capa (route, service, prompt, repository) tiene una sola razón de cambio |
| **OCP** — Abierto/cerrado | `AIService` y `CacheRepository` son abstracciones; agregar un nuevo proveedor no requiere tocar los servicios |
| **LSP** — Sustitución de Liskov | `OpenAIService` e `HttpCacheRepository` pueden reemplazarse por cualquier otra implementación de sus ABC |
| **ISP** — Segregación de interfaces | Cada ruta expone un contrato concreto y acotado; `EntityRepository` separa clientes de la IA |
| **DIP** — Inversión de dependencias | Los servicios reciben `CacheRepository` y `AIService` por constructor (inyección); las rutas usan `Depends()` |

---

## Flujo de capas

```
N8N / WhatsApp Bot
        │  HTTP
        ▼
  api/routes/          ← thin controllers (solo delegan)
        │  Depends()
        ▼
  services/            ← lógica de negocio
    ├── prompts/       ← construcción de prompts para la IA
    ├── ai_service     ← llamada a OpenAI GPT-4.1-mini
    └── repositories/  ← acceso a datos (API PHP)
            ├── cache_repository    → API PHP de caché (historial)
            └── entity_repository   → API PHP de clientes / proveedores
```

---

## Flujo actual de datos

El flujo se orquesta desde un **clasificador** que lee el mensaje del usuario y el **paso_actual** del registro para decidir el destino. La tabla `historial_cache` guarda los datos de la operación directamente en columnas (sin metadata_ia). El campo `ultima_pregunta` almacena el último mensaje enviado al usuario y sirve como contexto conversacional.

### 1. Entrada y clasificación

- **Clasificador** (`POST /clasificar-mensaje`): Recibe el mensaje y, si hay `wa_id` e `id_empresa`, consulta el registro y obtiene `ultima_pregunta` y `paso_actual`. Con el paso y el mensaje enruta a: **extraccion** (actualizar/confirmacion), **resumen**, **finalizar**, **informacion**, **eliminar** o **casual**.

### 2. Extracción (servicio unificado)

- **ExtraccionService** (`POST /procesar-extraccion`): Servicio principal que unifica extracción + identificación + diagnóstico en una sola llamada:
  1. Lee el registro actual de BD (columnas directas).
  2. Llama a la IA con un prompt unificado que extrae datos del mensaje Y genera diagnóstico de faltantes.
  3. Fusiona la propuesta de la IA con las columnas existentes.
  4. Si detecta una entidad identificable (RUC/DNI/nombre), llama al IdentificadorService inline.
  5. Calcula `paso_actual` dinámicamente según los campos obligatorios completos.
  6. Escribe directamente a columnas de BD (sin metadata_ia).
  7. Retorna: resumen de lo extraído + diagnóstico de faltantes + listo_para_finalizar.

### 3. Preguntador (standalone)

- **Preguntador** (`POST /preguntador`): Genera síntesis del estado actual y diagnóstico separado en preguntas obligatorias y opcionales. Se mantiene como endpoint standalone pero ya no es parte del flujo principal (el diagnóstico se genera dentro de ExtraccionService).

### 4. Finalizar

- **Finalizar** (`POST /finalizar-operacion`): Comprueba que estén llenos monto, tipo comprobante y cliente/proveedor (ventas). Si falta `entidad_id_maestro` pero hay nombre y documento, intenta registrar la entidad y continuar. Compra: devuelve síntesis; venta: síntesis + PDF (vía API SUNAT). Tras éxito escribe `paso_actual: 4`.

### Campos por agente (Extractor vs Opciones)

**Extractor (Estado 1 — `POST /procesar-extraccion`)**  
Los siguientes campos los extrae o recibe el extractor y se persisten en Redis/caché:

| Concepto | Campo en caché | Notas |
|----------|----------------|--------|
| Operación | `cod_ope` | "ventas" o "compras" |
| Entidad nombre | `entidad_nombre` | Razón social o nombre del cliente/proveedor |
| Entidad número (documento) | `entidad_numero_documento` | DNI 8 dígitos, RUC 11 dígitos |
| Tipo de documento (entidad) | `entidad_id_tipo_documento` | 1=DNI, 6=RUC |
| Tipo de comprobante | `id_comprobante_tipo` | Factura, Boleta, Nota de venta (según backend) |
| Número de documento (comprobante) | `numero_documento` | Ej: F001-00005678 (formato SUNAT) |
| Fecha de emisión | `fecha_emision` | Formato DD-MM-YYYY |
| Fecha de pago | `fecha_pago` | Formato DD-MM-YYYY |
| Moneda | `id_moneda` | PEN (1) o USD (2) |
| Monto total | `monto_total` | |
| Monto sin IGV | `monto_base` | |
| IGV | `monto_impuesto` | |
| Banco / cuenta | `caja_banco` | |
| id_empresa | (por request) | No lo extrae el extractor; viene del identificador de la sesión |
| Identificado | `identificado` | Bool; lo fija el identificador cuando encuentra la entidad (entidad_id_maestro, cliente_id, proveedor_id) |

**Opciones (Estado 2 — `POST /opciones`)**  
Los siguientes campos los define el agente de opciones (listas) y se persisten en Redis:

| Concepto | Campo en caché | Notas |
|----------|----------------|--------|
| Sucursal (nombre) | `sucursal_nombre` | Texto mostrado; lista desde `ws_informacion_ia.php` (OBTENER_SUCURSALES) |
| id sucursal | `id_sucursal` | ID numérico de la sucursal elegida |
| Forma de pago | `id_forma_pago` | Transferencia, TD, TC, Billetera virtual (IDs según backend) |
| Medio de pago | `tipo_operacion` | Contado o Crédito |

---

### Indicador de progreso (`paso_actual`)

| Valor | Significado | Condición |
|-------|-------------|-----------|
| `0` | Registro creado, sin tipo | `cod_ope` vacío |
| `1` | Tipo definido | `cod_ope` = ventas/compras, resto vacío |
| `2` | Datos parciales | Al menos un campo obligatorio llenado |
| `3` | Obligatorios completos | monto + entidad + comprobante + moneda + tipo_operacion |
| `4` | Finalizado | Post-SUNAT (lo escribe FinalizarService) |

### Flujo Estado 1 (registro hasta datos completos)

Este flujo cubre la primera parte del registro: desde que no hay registro en caché hasta tener todos los datos obligatorios. La última parte del registro (cierre/validación final) se cubrirá en **Estado 2** con otro agente.

1. **Primera interacción (mensaje casual o documento)**  
   - Si **no hay registro en Redis** y el mensaje no indica compra/venta ni contiene JSON: el clasificador devuelve **casual** y se sugiere el mensaje *"Para comenzar, indique si desea registrar una compra o una venta."* (campo `mensaje_casual_sugerido`).  
   - Si el mensaje **sí indica compra o venta**, o trae un **documento en JSON**: se pasa al clasificador y se envía a **actualizar** (extracción), que puede crear el registro.

2. **Con compra o venta (o documento)**  
   - **Extracción** crea o actualiza el registro en Redis y devuelve un listado de **datos faltantes en lenguaje natural** (diagnóstico). El usuario responde o envía más datos.

3. **Documento JSON**  
   - Si el usuario envía un documento en formato JSON, el clasificador lo envía a **actualizar**. La extracción prioriza las **etiquetas/claves del JSON** para llenar la mayor cantidad de campos; después devuelve solo las **preguntas que siguen faltando** (por lógica, menos que antes). Se repite hasta completar los obligatorios.

4. **Estado 2 (opciones)**  
   - Cuando el registro tiene todos los datos obligatorios (paso_actual ≥ 3), el agente `POST /opciones` permite elegir **sucursal** (desde `ws_informacion_ia.php`, codOpe OBTENER_SUCURSALES), **forma de pago** (transferencia, TD, TC, billetera virtual) y **método de pago** (contado/crédito). Las listas se envían con el payload que devuelve la API, enviándolo a `ws_send_whatsapp_list.php`. Las selecciones se persisten en Redis (id_sucursal, id_forma_pago, tipo_operacion).

---

## Endpoints disponibles

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/procesar-extraccion` | Extrae datos, identifica entidad, genera diagnóstico, persiste en BD |
| `POST` | `/generar-pregunta` | Genera la siguiente pregunta guiada con botones opcionales |
| `POST` | `/clasificar-mensaje` | Clasifica la intención del mensaje (actualizar, confirmar, finalizar…) |
| `POST` | `/informador` | Responde preguntas de ayuda sobre cómo llenar datos |
| `GET`  | `/generar-resumen` | Muestra el estado actual del registro con diagnóstico |
| `POST` | `/identificar-entidad` | Busca cliente o proveedor por RUC, DNI o nombre |
| `POST` | `/eliminar-operacion` | Cancela y limpia el borrador activo |
| `POST` | `/finalizar-operacion` | Emite el comprobante electrónico vía SUNAT |
| `POST` | `/iniciar-flujo` | Crea el registro inicial de caché para comenzar el flujo |
| `POST` | `/opciones` | Estado 2: opciones múltiples (sucursal, forma de pago, método de pago); devuelve payload para ws_send_whatsapp_list.php |
| `POST` | `/preguntador` | Síntesis + diagnóstico (preguntas obligatorias y opcionales) — standalone |

La documentación interactiva (Swagger) está disponible en:
- `http://localhost:3000/docs`
- `http://localhost:3000/redoc`

---

## Variables de entorno

Crea un archivo `.env` en la raíz del proyecto con el siguiente contenido:

```env
OPENAI_API_KEY=sk-...          # API Key de OpenAI
TOKEN_SUNAT=...                # Token Bearer para la API de facturación SUNAT
```

Las URLs de los servicios PHP externos están centralizadas en `config/settings.py` y no requieren configuración por entorno.

---

## Ejecución en modo local (desarrollo)

### Requisitos previos

- Python 3.11 o superior
- `pip`

### Pasos

**1. Clonar el repositorio e ingresar al directorio:**

```bash
git clone <url-del-repo>
cd maravia-bot
```

**2. Crear y activar un entorno virtual:**

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python -m venv venv
source venv/bin/activate
```

**3. Instalar dependencias:**

```bash
pip install fastapi uvicorn openai requests python-dotenv
```

**4. Crear el archivo `.env`:**

```bash
# Copiar el ejemplo y completar los valores
cp .env.example .env
```

**5. Ejecutar el servidor con recarga automática:**

```bash
uvicorn main:app --host 0.0.0.0 --port 3000 --reload
```

El flag `--reload` reinicia el servidor automáticamente al detectar cambios en el código.

**6. Verificar que la API responde:**

```
http://localhost:3000/docs
```

---

## Ejecución en producción con Docker

### Requisitos previos

- Docker
- Docker Compose

### Paso 1 — Preparar el archivo `.env`

```bash
cp .env.example .env
# Editar .env con los valores reales de producción
```

### Paso 2 — Construir y levantar el contenedor

```bash
docker-compose up --build -d
```

### Paso 3 — Verificar que el contenedor está activo

```bash
docker-compose ps
docker-compose logs -f
```

### Paso 4 — Verificar que la API responde

```
http://<ip-del-servidor>:3000/docs
```

### Comandos útiles de Docker

```bash
# Detener el servicio
docker-compose down

# Ver logs en tiempo real
docker-compose logs -f api-maravia

# Reconstruir la imagen tras cambios de dependencias
docker-compose up --build -d

# Reiniciar sin reconstruir
docker-compose restart api-maravia
```

---

## Archivos legacy (deprecados)

Los siguientes archivos se conservan como referencia pero ya no forman parte del flujo principal:

- `services/analizador_service.py` — reemplazado por `ExtraccionService`
- `services/confirmador_service.py` — absorbido por `ExtraccionService`
- `services/registrador_service.py` — ya no necesario (datos se escriben directo)
- `config/estados.py` — reemplazado por `paso_actual` (0-4)
- `prompts/analizador.py` — reemplazado por `prompts/extraccion.py`
- `main_cache.py` — archivo original monolítico, referencia histórica
