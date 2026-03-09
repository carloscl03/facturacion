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

El proyecto sigue una arquitectura limpia en capas aplicando los principios **SOLID**. El archivo original `main_cache.py` fue refactorizado en los siguientes módulos:

```
maravia-bot/
├── main.py                        # Punto de entrada: instancia FastAPI + registra routers
│
├── config/
│   ├── settings.py                # Centraliza URLs, tokens y variables de entorno (DIP)
│   └── estados.py                # Banderas de estado del flujo (metadata_ia.estado_flujo)
│
├── prompts/
│   ├── plantillas.py              # PLANTILLA_VISUAL y REGLAS_NORMALIZACION compartidas
│   ├── extraccion.py              # build_prompt_extractor(...)
│   ├── preguntador.py             # build_prompt_pregunta(...) y build_prompt_preguntador_v2(...)
│   ├── clasificador.py            # build_prompt_router(...)
│   ├── informador.py              # build_prompt_info(...)
│   ├── resumen.py                 # build_prompt_resumen(...)
│   ├── analizador.py              # build_prompt_analisis(...)
│   └── unificado.py               # build_prompt_unico(...)
│
├── repositories/
│   ├── base.py                    # Clase abstracta CacheRepository (ABC)
│   ├── cache_repository.py        # HttpCacheRepository — acceso a la API PHP de caché
│   └── entity_repository.py       # EntityRepository — acceso a clientes y proveedores
│
├── services/
│   ├── ai_service.py              # Clase abstracta AIService + OpenAIService
│   ├── extraccion_service.py      # Extrae datos contables del mensaje
│   ├── preguntador_service.py     # Genera la siguiente pregunta contextualizada
│   ├── clasificador_service.py    # Clasifica la intención del mensaje
│   ├── informador_service.py      # Responde preguntas de ayuda de llenado
│   ├── resumen_service.py         # Genera resumen del estado actual
│   ├── identificador_service.py  # Busca y confirma cliente/proveedor
│   ├── finalizar_service.py       # Emite el comprobante en SUNAT
│   ├── unificado_service.py       # Extrae + responde en una sola llamada a IA
│   ├── analizador_service.py      # Analiza y guarda cambios del mensaje (solo lo recién actualizado + confirmación)
│   ├── registrador_service.py     # Confirma y persiste la operación; orquesta identificador si aplica
│   ├── confirmador_service.py     # Orquesta registrador + preguntador; entrega un solo mensaje (síntesis+preguntas o identificación)
│   └── iniciar_service.py         # Inicia un nuevo flujo de registro
│
└── api/
    ├── deps.py                    # Factories de dependencias para FastAPI Depends()
    └── routes/
        ├── extraccion.py          # POST /procesar-extraccion
        ├── preguntador.py         # POST /generar-pregunta  |  POST /preguntador
        ├── clasificador.py        # POST /clasificar-mensaje
        ├── informador.py          # POST /informador
        ├── resumen.py             # GET  /generar-resumen
        ├── identificador.py       # POST /identificar-entidad
        ├── eliminar.py            # POST /eliminar-operacion
        ├── finalizar.py           # POST /finalizar-operacion
        ├── unificado.py           # POST /unificado
        ├── analizador.py          # POST /analizador
        ├── registrador.py         # POST /registrador
        ├── confirmador.py         # POST /confirmador
        └── iniciar.py             # POST /iniciar-flujo
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

El flujo se orquesta desde un **clasificador** que lee el mensaje del usuario y el **estado del flujo** (bandera en `metadata_ia.estado_flujo`) para decidir el destino. La tabla de caché (`historial_cache`) guarda los datos de la operación y `metadata_ia` (JSON) contiene `dato_registrado`, `dato_identificado` y `estado_flujo`.

### 1. Entrada y clasificación

- **Clasificador** (`POST /clasificar-mensaje`): Recibe el mensaje y, si hay `wa_id` e `id_empresa`, consulta el registro y obtiene `ultima_pregunta` y `estado_flujo` (desde `metadata_ia` o inferido por "IDENTIFICACION PENDIENTE"). Con la bandera y el mensaje enruta a: **actualizar** (analizador), **confirmacion** (confirmador), **resumen**, **finalizar**, **informacion**, **eliminar** o **casual**.

### 2. Actualizar (analizador)

- **Analizador** (`POST /analizador`): Extrae datos del mensaje y los fusiona con el registro actual. **No** devuelve un resumen de todo lo llenado; solo un mensaje de **lo recién actualizado o modificado** en este turno y una **línea de confirmación** (ej. "¿Es correcto?"). Persiste en caché y escribe en `metadata_ia` el `estado_flujo`: `pendiente_tipo_operacion` (si falta tipo venta/compra) o `pendiente_confirmacion` (si ya hay datos para confirmar).

### 3. Confirmación (confirmador)

- **Confirmador** (`POST /confirmador`): Ejecuta **registrador** y luego **preguntador**. Hay dos clases de mensaje posibles, pero **solo se entrega uno** según la bandera:
  - **Si el usuario venía de dato identificado** (`pendiente_identificacion` / "IDENTIFICACION PENDIENTE"): se acaba de confirmar la ficha del identificador; se registra y se devuelve únicamente **síntesis + preguntas** (obligatorias y opcionales) del preguntador.
  - **Si venía de dato analizado** y el **identificador** encontró algo en esta pasada: se devuelve únicamente el **mensaje de identificación** (ficha que pide confirmar la entidad; aún no se registra en el resto de la tabla hasta que el usuario confirme).
  - **Si venía de dato analizado** y no hay identificación: se devuelve únicamente **síntesis + preguntas**.

El registrador persiste `metadata_ia` en columnas de la tabla; si hay dato identificable sin ID, llama al **identificador**, que actualiza `metadata_ia` y pone `estado_flujo: pendiente_identificacion` y `ultima_pregunta: "IDENTIFICACION PENDIENTE"`. Tras registrar con éxito, el registrador escribe `estado_flujo: pendiente_datos`.

### 4. Preguntador y listo para finalizar

- **Preguntador** (interno en confirmador o `POST /preguntador`): Genera **síntesis** del estado actual y **diagnóstico** separado en **preguntas obligatorias** y **preguntas opcionales**. Si los tres obligatorios (monto/detalle, cliente o proveedor, tipo comprobante) están llenos, devuelve `listo_para_finalizar: true`. El confirmador, en ese caso, actualiza la caché con `estado_flujo: listo_para_finalizar`.

### 5. Finalizar

- **Finalizar** (`POST /finalizar-operacion`): Comprueba que estén llenos monto, tipo comprobante y cliente/proveedor (ventas). Si falta `entidad_id_maestro` pero hay nombre y documento, intenta registrar la entidad y continuar. Compra: devuelve síntesis; venta: síntesis + PDF (vía API SUNAT). Tras éxito escribe `estado_flujo: completado` en `metadata_ia`.

### Banderas de estado (`config/estados.py`)

| Bandera | Uso |
|--------|-----|
| `inicial` | Sin registro o sin estado; clasificador permite actualizar o casual. |
| `pendiente_tipo_operacion` | Falta indicar venta o compra; analizador pidió tipo. |
| `pendiente_confirmacion` | Analizador guardó datos; se espera sí/no del usuario. |
| `pendiente_identificacion` | Identificador mostró ficha; se espera confirmación de la entidad. |
| `pendiente_datos` | Registro ya persistido; preguntador mostró preguntas. |
| `listo_para_finalizar` | Obligatorios completos; se puede finalizar o completar opcionales. |
| `completado` | Operación finalizada; próximo mensaje como inicial o casual. |

---

## Endpoints disponibles

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/procesar-extraccion` | Extrae campos contables del mensaje y los guarda en caché |
| `POST` | `/generar-pregunta` | Genera la siguiente pregunta guiada con botones opcionales |
| `POST` | `/clasificar-mensaje` | Clasifica la intención del mensaje (actualizar, confirmar, finalizar…) |
| `POST` | `/informador` | Responde preguntas de ayuda sobre cómo llenar datos |
| `GET`  | `/generar-resumen` | Muestra el estado actual del registro con diagnóstico |
| `POST` | `/identificar-entidad` | Busca cliente o proveedor por RUC, DNI o nombre |
| `POST` | `/eliminar-operacion` | Cancela y limpia el borrador activo |
| `POST` | `/finalizar-operacion` | Emite el comprobante electrónico vía SUNAT |
| `POST` | `/unificado` | Extrae datos y genera respuesta visual en una sola llamada a IA |
| `POST` | `/analizador` | Analiza el mensaje, guarda cambios; retorna solo lo recién actualizado + confirmación |
| `POST` | `/registrador` | Confirma y persiste la propuesta; orquesta identificador si hay dato identificable sin ID |
| `POST` | `/confirmador` | Orquesta registrador + preguntador; devuelve un solo mensaje (síntesis+preguntas o identificación) |
| `POST` | `/iniciar-flujo` | Crea el registro inicial de caché para comenzar el flujo |
| `POST` | `/preguntador` | Síntesis + diagnóstico (preguntas obligatorias y opcionales); indica listo_para_finalizar si aplica |

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

### Paso 2 — Actualizar el `Dockerfile` para usar el nuevo punto de entrada

El `Dockerfile` debe apuntar a `main.py` (no a `main_cache.py`). Edita la última línea:

```dockerfile
# Antes (archivo original)
CMD ["python", "main_cache.py"]

# Después (arquitectura refactorizada)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
```

### Paso 3 — Construir y levantar el contenedor

```bash
docker-compose up --build -d
```

### Paso 4 — Verificar que el contenedor está activo

```bash
docker-compose ps
docker-compose logs -f
```

### Paso 5 — Verificar que la API responde

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

## Notas de migración

El archivo `main_cache.py` original se conserva en el repositorio como referencia histórica. El nuevo punto de entrada es `main.py`. Si tienes scripts o configuraciones que apuntan a `main_cache.py`, actualízalos a `main:app`.
