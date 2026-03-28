# Rutas API — Endpoints REST

Thin controllers que delegan toda la lógica a los servicios. Las dependencias se inyectan via `FastAPI Depends()`.

---

## Inyección de dependencias (deps.py)

| Factory | Retorna | Lógica |
|---------|---------|--------|
| `get_cache_repo()` | `HttpCacheRepository` o `RedisCacheRepository` | Según `CACHE_BACKEND` |
| `get_entity_repo()` | `EntityRepository` | Instancia única |
| `get_informacion_repo()` | `InformacionRepository` | Instancia única |
| `get_parametros_repo()` | `ParametrosRepository` | Instancia única |
| `get_ai_service()` | `OpenAIService` | Con `OPENAI_API_KEY` y `MODELO_IA` |
| `get_identificador_service()` | `IdentificadorService` | Combina cache + entity repos |
| `get_sunat_client()` | `SunatClient` | Con token SUNAT |

---

## Endpoints activos

### POST /procesar-extraccion

**Archivo:** `extraccion.py` | **Servicio:** `ExtraccionService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `wa_id` | str | query | sí |
| `mensaje` | str | query | sí |
| `id_from` | int | query | sí |
| `url` | str | query | no |

Servicio principal. Extrae datos del mensaje, identifica entidades, diagnostica faltantes, persiste en Redis. El parámetro `url` es opcional y se guarda persistentemente en Redis.

---

### POST /clasificar-mensaje

**Archivo:** `clasificador.py` | **Servicio:** `ClasificadorService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `mensaje` | str | query | sí |
| `wa_id` | str | query | sí |
| `id_from` | int | query | sí |

Clasifica la intención del mensaje. Retorna: `intencion`, `destino`, `estado`, `siguiente_estado`, `op_visible`, `opciones_ok`. Gestiona transiciones 3→4 y 4→5.

---

### POST /opciones

**Archivo:** `opciones.py` | **Servicio:** `OpcionesService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `wa_id` | str | query | sí |
| `id_from` | int | query | sí |
| `mensaje` | str | query | no |
| `action` | str | query | no ("get" o "submit") |
| `campo` | str | query | no |
| `valor` | str/int | query | no |
| `id_plataforma` | int | query | no (default: 6) |
| `id_empresa` | int | query | no |
| body | `OpcionesBody` | JSON | no |

**Lógica especial:**
- Primer mensaje se ignora (solo carga la lista con `get_next`)
- Si hay `opciones_actuales` en Redis → infiere `action=submit`
- Envía listas WhatsApp automáticamente via `ws_send_whatsapp_list.php`
- Cuando `estado2_completo`: envía mensaje de confirmación via `ws_send_whatsapp_oficial.php`

**Nota sobre IDs:** `id_from` se usa para datos (cache, tablas). `id_empresa` se usa para credenciales WhatsApp.

---

### POST /confirmar-registro

**Archivo:** `confirmar_registro.py` | **Servicio:** `ConfirmarRegistroService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `wa_id` | str | query | sí |
| `id_from` | int | query | sí |

Transición explícita estado 3 → 4. Valida que los obligatorios estén completos.

---

### POST /finalizar-operacion

**Archivo:** `finalizar.py` | **Servicio:** `FinalizarService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `wa_id` | str | query | sí |
| `id_from` | int | query | sí |
| `id_empresa` | int | query | no |
| `id_plataforma` | int | query | no (default: 6) |

Emite comprobante. `id_from` para datos; `id_empresa` para credenciales WhatsApp (si difieren).

---

### POST /identificar-entidad

**Archivo:** `identificador.py` | **Servicio:** `IdentificadorService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `wa_id` | str | query | sí |
| `tipo_ope` | str | query | sí |
| `termino` | str | query | sí |
| `id_from` | int | query | sí |

Busca cliente/proveedor por RUC, DNI o nombre.

---

### GET /generar-resumen

**Archivo:** `resumen.py` | **Servicio:** `ResumenService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `wa_id` | str | query | sí |
| `id_from` | int | query | sí |

Genera resumen visual del estado actual del registro.

---

### POST /informador

**Archivo:** `informador.py` | **Servicio:** `InformadorService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `mensaje` | str | query | sí |
| `wa_id` | str | query | no |
| `id_from` | int | query | no |

Responde preguntas de ayuda sobre el registro.

---

### POST /casual

**Archivo:** `casual.py` | **Servicio:** `CasualService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `mensaje` | str | query | sí |
| `wa_id` | str | query | no |
| `id_from` | int | query | no |
| `id_empresa` | int | query | no |
| `id_plataforma` | int | query | no (default: 6) |

Saludo inicial. Si hay `wa_id` + `id_empresa`, envía botones Compra/Venta por WhatsApp.

---

### POST /generar-pregunta | POST /preguntador

**Archivo:** `preguntador.py` | **Servicio:** `PreguntadorService` / `PreguntadorV2Service`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `wa_id` | str | query | sí |
| `id_from` | int | query | sí |

Genera siguiente pregunta contextualizada.

---

### POST /iniciar-flujo

**Archivo:** `iniciar.py` | **Servicio:** `IniciarService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `wa_id` | str | query | sí |
| `id_from` | int | query | sí |
| `tipo` | str | query | sí ("venta" o "compra") |

Crea registro inicial en Redis.

---

### POST /eliminar-operacion

**Archivo:** `eliminar.py` | **Servicio:** `EliminarService`

| Parámetro | Tipo | Origen | Requerido |
|-----------|------|--------|-----------|
| `wa_id` | str | query | sí |
| `id_from` | int | query | sí |

Elimina registro temporal completo.

---

## Flujo de orquestación N8N

```
WhatsApp → N8N Webhook
              │
              ▼
        /clasificar-mensaje
              │
              ├── destino: "extraccion" ──→ /procesar-extraccion
              ├── destino: "casual" ──→ /casual
              ├── destino: "opciones" ──→ /opciones
              ├── destino: "confirmar-registro" ──→ /confirmar-registro → /opciones
              ├── destino: "generar-resumen" ──→ /generar-resumen
              ├── destino: "finalizar-operacion" ──→ /finalizar-operacion
              ├── destino: "eliminar-operacion" ──→ /eliminar-operacion
              └── destino: "informador" ──→ /informador
```

### Flujo típico de una venta

```
1. /clasificar-mensaje → casual
2. /casual → botones Compra/Venta
3. /clasificar-mensaje → extraccion
4. /procesar-extraccion → extrae datos (repite hasta estado 3)
5. /clasificar-mensaje → confirmar-registro (usuario confirma)
6. /confirmar-registro → estado 4
7. /opciones → sucursal → forma_pago (repite por campo)
8. /clasificar-mensaje → finalizar (usuario confirma opciones)
9. /finalizar-operacion → emite comprobante + WhatsApp
```

---

## Rutas legacy

| Ruta | Archivo | Reemplazada por |
|------|---------|-----------------|
| `/unificado` | `unificado.py` | `/procesar-extraccion` |
| `/analizador` | `analizador.py` | `/procesar-extraccion` |
| `/confirmador` | `confirmador.py` | `/confirmar-registro` |
| `/registrador` | `registrador.py` | Escritura directa en servicios |
