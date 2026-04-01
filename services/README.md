# Servicios — Lógica de Negocio

## Índice de servicios

| Archivo | Clase | Propósito |
|---------|-------|-----------|
| `ai_service.py` | `AIService` / `OpenAIService` | Abstracción de IA (OpenAI GPT-4.1-mini) |
| `extraccion_service.py` | `ExtraccionService` | Servicio principal: extrae datos, identifica entidad, busca catálogo, diagnostica faltantes |
| `clasificador_service.py` | `ClasificadorService` | Clasifica intención del mensaje y gestiona transiciones de estado |
| `opciones_service.py` | `OpcionesService` | Estado 4: listas de sucursal, centro costo, forma pago |
| `confirmar_registro_service.py` | `ConfirmarRegistroService` | Transición estado 3 → 4 |
| `finalizar_service.py` | `FinalizarService` | Emite comprobante (SUNAT / compra) y envía por WhatsApp |
| `identificador_service.py` | `IdentificadorService` | Busca o crea cliente/proveedor por RUC/DNI |
| `resumen_service.py` | `ResumenService` | Genera resumen visual del registro actual |
| `informador_service.py` | `InformadorService` | Responde preguntas de ayuda sobre el registro |
| `casual_service.py` | `CasualService` | Saludo inicial + botones Compra/Venta |
| `preguntador_service.py` | `PreguntadorService` / `PreguntadorV2Service` | Genera siguiente pregunta contextualizada |
| `iniciar_service.py` | `IniciarService` | Crea registro inicial en Redis |
| `eliminar_service.py` | `EliminarService` | Elimina registro temporal completo |
| `whatsapp_sender.py` | (funciones) | Módulo centralizado de envío a WhatsApp (texto, PDF, lista, botones) |

---

## Diagrama de dependencias

```
ClasificadorService ──→ AIService
        │                    ↑
        │              ExtraccionService ──→ IdentificadorService ──→ EntityRepository
        │                    │
        ▼                    ▼
  CacheRepository      CacheRepository
        ↑
        │
  OpcionesService ──→ InformacionRepository
        │              ParametrosRepository
        │              AIService (resolver opciones)
        │
  ConfirmarRegistroService ──→ CacheRepository
        │
  FinalizarService ──→ EntityRepository
        │               SunatClient
        │               EliminarService
        │
  ResumenService ──→ AIService + CacheRepository
  InformadorService ──→ AIService + CacheRepository
  CasualService ──→ AIService + whatsapp_sender
        │
  whatsapp_sender ──→ ws_send_whatsapp_oficial / _list / _buttons
  PreguntadorService ──→ AIService + CacheRepository
  IniciarService ──→ CacheRepository
  EliminarService ──→ CacheRepository
```

---

## Flujo de enrutamiento (ClasificadorService)

```
Mensaje del usuario
        │
        ▼
  ¿Hay registro en Redis?
        │
   NO ──┤── SÍ ─────────────────────────────────┐
        │                                        │
  ¿Indica compra/venta?              IA clasifica intención
        │                                        │
   SÍ → extraccion              ┌────────────────┼────────────────┐
   NO → casual                  │                │                │
                          actualizar        opciones         resumen
                          (estado ≤ 3)    (estado ≥ 4)    (explícito)
                                │                │
                                │          ┌─────┴─────┐
                                │     confirmar    finalizar
                                │    (estado 3)   (estado ≥ 5)
                                │     → 3→4         → emitir
                                │
                          ┌─────┴─────┐
                     eliminar    (candados)
                                 - casual → actualizar (con registro)
                                 - actualizar → opciones (estado ≥ 4)
                                 - finalizar → resumen (estado < 5)
```

---

## Detalle por servicio

### ExtraccionService

**Constructor:** `repo: CacheRepository`, `ai: AIService`, `identificador: IdentificadorService | None`, `informacion_repo`

**Método principal:** `ejecutar(wa_id, mensaje, id_from, *, url=None, id_empresa=None, id_plataforma=None) → dict`

**Responsabilidades:**
- Resuelve cola de productos pendientes (`producto_pendiente` / `productos_pendientes_cola` en Redis)
- Construye prompt con estado actual + mensaje del usuario
- IA extrae datos → `propuesta_cache`
- Fusiona propuesta con datos existentes en Redis (merge de productos, no reemplazo)
- Si detecta RUC/DNI (8/11 dígitos) → llama a `IdentificadorService.buscar_o_crear()`
- Busca cada producto en el catálogo de la empresa (`buscar_catalogo`):
  - 1 match → auto-fill silencioso (id_catalogo, precio, unidad) con ✅
  - N matches → cola de pendientes + lista WhatsApp interactiva
  - 0 matches → producto genérico sin catálogo
  - Búsqueda con fallback sin tildes (cámara → camara)
- Recalcula `monto_total` desde la suma de productos
- Calcula IGV determinísticamente en Python (nunca confía en la IA)
- Protege `tipo_documento` ya definido contra inferencias no solicitadas
- Calcula estado (0-3) automáticamente via `calcular_estado()`
- Preserva campos de opciones (sucursal, forma_pago, tipo_documento) y `url` entre rondas
- Valida `fecha_pago >= fecha_emision`
- Envía mensajes directamente por WhatsApp (texto y listas)
- **No sobrescribe** estado 4 ni 5 (esos los gestionan otros servicios)

### ClasificadorService

**Constructor:** `repo: CacheRepository`, `ai: AIService`

**Método principal:** `ejecutar(mensaje, wa_id, id_from) → dict`

**Transiciones de estado:**
- **3 → 4**: cuando `estado == 3` y mensaje es confirmación → escribe estado 4 en Redis
- **4 → 5**: cuando `estado == 4`, `opciones_completo == True` y mensaje es confirmación → escribe estado 5

**Candados (guardrails):**
- Con registro: nunca devolver `casual` (se corrige a `actualizar`)
- `estado ≥ 4` + `actualizar` → se redirige a `opciones`
- `estado < 3` + `opciones` → se redirige a `extraccion`
- `finalizar` solo con `estado ≥ 5`

### OpcionesService

**Constructor:** `cache: CacheRepository`, `informacion: InformacionRepository`, `parametros: ParametrosRepository | None`, `ai: Any`

**Métodos:**
- `get_next(wa_id, id_from, id_plataforma) → dict` — devuelve siguiente lista pendiente
- `submit(wa_id, id_from, campo, valor, id_plataforma) → dict` — procesa selección del usuario

**Orden de campos:**
1. `sucursal` (venta y compra)
2. `centro_costo` (solo compra, si hay `ParametrosRepository`)
3. `forma_pago` (venta y compra)

**Resolución de selección:** exacto → substring → IA → ID numérico

### FinalizarService

**Constructor:** `cache_repo: CacheRepository`, `entity_repo: EntityRepository`, `sunat_client: SunatClient | None`

**Método principal:** `ejecutar(wa_id, id_from, id_empresa, id_plataforma) → dict`

**Flujos:**
- **Venta**: `venta_mapper` → `ws_venta.php` → envía texto + PDF por WhatsApp → elimina registro
- **Compra**: `compra_mapper` → `ws_compra.php` → envía texto por WhatsApp → elimina registro
- **Error**: resetea a estado 3 para que el usuario corrija datos

### IdentificadorService

**Constructor:** `cache_repo: CacheRepository`, `entity_repo: EntityRepository`

**Métodos:**
- `buscar(tipo_ope, termino, id_from) → dict` — solo lectura, devuelve ficha
- `buscar_o_crear(tipo_ope, termino, id_from, nombre_entidad) → dict` — busca o registra
- `ejecutar(wa_id, tipo_ope, termino, id_from) → dict` — wrapper legacy que persiste en cache

**Lógica:**
- COMPRA → busca proveedor → si no existe, registra como proveedor
- VENTA → busca cliente → si no existe, registra como cliente
- Maneja: razón social (RUC), nombre completo (DNI), nombres+apellidos

---

## Transiciones de estado por servicio

| Transición | Responsable | Condición |
|------------|-------------|-----------|
| 0 → 1 → 2 → 3 | `ExtraccionService` | Automático según campos completos |
| 3 → 4 | `ClasificadorService` + `ConfirmarRegistroService` | Confirmación del usuario |
| 4 (opciones) | `OpcionesService` | Elige sucursal, centro costo, forma pago |
| 4 → 5 | `ClasificadorService` | Confirmación + opciones completas |
| 5 → finalizado | `FinalizarService` | Emite comprobante exitosamente |
| 5 → 3 (error) | `FinalizarService` | Error en emisión → vuelve a edición |
| cualquiera → eliminado | `EliminarService` | Usuario cancela |
