# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MaravIA Bot is a FastAPI REST API that processes WhatsApp messages to register accounting operations (ventas/compras) using GPT-4.1-mini. It integrates with a PHP backend (api.maravia.pe), SUNAT for electronic invoicing in Peru, and N8N for orchestration.

## Commands

```bash
# Install
pip install -r requirements.txt

# Run locally
uvicorn main:app --host 0.0.0.0 --port 3000 --reload

# Unit tests (safe, no external calls)
pytest test/test_helpers_domain.py test/test_safe_int_mappers.py -v

# Single test
pytest test/test_helpers_domain.py::test_calcular_estado_con_campos_obligatorios -v

# Integration tests (call real PHP APIs, create real records)
python test/test_registro.py
python test/test_pdf_sunat.py
```

No linter or formatter is configured.

## Architecture

### Layer flow
```
API Routes (api/routes/) → Services (services/) → Repositories (repositories/)
                                ↓
                           Prompts (prompts/)  →  AIService (OpenAI)
```

- **Routes**: Thin controllers using FastAPI `Depends()` for DI. All receive `wa_id`, `mensaje`, `id_from`.
- **Services**: Business logic. Each service gets dependencies via constructor injection.
- **Repositories**: Abstract `CacheRepository` with two backends — `HttpCacheRepository` (dev) and `RedisCacheRepository` (prod), switched by `CACHE_BACKEND` env var.
- **Prompts**: Dynamic prompt builders that inject Redis state + rules into GPT prompts.
- **Helpers** (`services/helpers/`): Pure domain logic — state calculation, IGV, mappers, normalization.

### State Machine (6 states)

Operations progress through states 0→5:

| State | Meaning | Driven by |
|-------|---------|-----------|
| 0 | No operación definida | ExtraccionService |
| 1 | Operación asignada (venta/compra) | ExtraccionService |
| 2 | Datos parciales | ExtraccionService |
| 3 | Todos los campos obligatorios completos | ExtraccionService (auto-calc via `calcular_estado()`) |
| 3→4 | Usuario dice "confirmo"/"dale"/"ok"/etc | ClasificadorService detecta confirmación |
| 4 | Selección de opciones (sucursal, forma_pago, centro_costo) | OpcionesService |
| 4→5 | Usuario confirma opciones | ClasificadorService |
| 5 | Emisión del comprobante → SUNAT/PHP | FinalizarService |

**Mandatory fields for state 3**: monto_total (o productos), entidad_nombre, tipo_documento, moneda, metodo_pago (+ dias_credito/nro_cuotas si crédito).

### IGV Calculation

All IGV logic is centralized in `services/helpers/igv.py` using `Decimal` for precision:
- **Factura/Boleta**: 18% IGV. Default: precio incluye IGV. Si usuario dice "más IGV": precio es base.
- **Nota de venta/compra, Recibo por honorarios**: Sin IGV (base=0, igv=0, total=monto directo).
- The `igv_incluido` flag in Redis controls whether prices are treated as base or IGV-inclusive.
- `calcular_igv()` for aggregate amounts, `calcular_item()` for per-product detalle, `sumar_productos()` for consistent totals.

### Key business rules

- **Regla 700 PEN**: Ventas en soles < S/ 700 → RUC/DNI opcional. >= 700 → obligatorio.
- **Notas**: No requieren numero_documento ni IGV. entidad_numero siempre opcional.
- **URL persistence**: El campo `url` (PDF adjunto) se preserva entre rondas de extracción.
- **Error SUNAT**: FinalizarService resetea a estado 3 para corrección y reintento.
- `normalizar_documento_entidad()` rechaza patrones como F001-00001 para evitar confundir serie de comprobante con RUC/DNI.

### External API distinction

- `id_from` → ID de empresa para datos (cache, registros, catálogos)
- `id_empresa` → ID de empresa con credenciales WhatsApp (puede diferir de id_from)

## Environment

Required: `OPENAI_API_KEY`. Optional: `CACHE_BACKEND` (http|redis), `REDIS_URL`, `MARAVIA_USER`, `MARAVIA_PASSWORD`. See `config/settings.py` for all variables.
