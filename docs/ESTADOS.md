# Revisión del sistema de estados

El registro en caché (Redis/API PHP) tiene un campo numérico **`estado`** (0 a 4) que controla el flujo del bot.

---

## Definición de estados

| Estado | Nombre conceptual | Condición (cálculo en `ExtraccionService._calcular_estado`) | Qué puede hacer el usuario |
|--------|-------------------|-------------------------------------------------------------|----------------------------|
| **0** | Sin operación / Inicial | `operacion` no es "venta" ni "compra" | Sin registro → clasificador devuelve **casual**. Con registro recién creado (ej. iniciar) → extracción pide tipo y datos. |
| **1** | Operación definida, sin obligatorios | `operacion` = venta/compra pero ningún obligatorio lleno | **Extracción**: ir llenando monto/productos, entidad, tipo doc, moneda. |
| **2** | Parcial | Al menos un obligatorio lleno, pero no todos | **Extracción**: seguir completando. |
| **3** | Obligatorios completos | Los 4 obligatorios cumplidos (ver abajo) | Clasificador acepta **confirmar-registro**. Tras confirmar → pasa a 4. |
| **4** | Confirmado (Estado 2 del flujo) | Puesto por confirmar-registro (o clasificador al clasificar confirmar) | **Opciones**: sucursal, forma de pago, medio de pago. Cuando las 3 están llenas → puede **finalizar-operacion**. |

### Obligatorios para estado 3 (`extraccion_service._calcular_estado`)

- `monto_total` > 0 **o** `productos` no vacío
- `entidad_nombre` **o** `entidad_id`
- `tipo_documento`
- `moneda`

---

## Dónde se escribe `estado`

| Origen | Valor | Archivo |
|--------|--------|---------|
| **IniciarService** | 0 | `iniciar_service.py`: al insertar registro con `operacion` (venta/compra). |
| **ExtraccionService** | 0, 1, 2 o 3 | `extraccion_service.py`: `_calcular_estado(payload_db)`; **no pisa 4** (si ya es 4, lo mantiene). |
| **ConfirmarRegistroService** | 4 | `confirmar_registro_service.py`: solo si `estado == 3`; actualiza a 4. |
| **ClasificadorService** | 4 | `clasificador_service.py`: si destino = confirmar-registro y estado = 3, actualiza a 4 en Redis (además del propio confirmar-registro). |
| **FinalizarService** | 4 | `finalizar_service.py`: tras éxito de emisión, actualiza registro con `estado: 4`. |

---

## Dónde se lee `estado`

| Consumidor | Uso |
|------------|-----|
| **ClasificadorService** | `_obtener_estado(registro)`. Sin registro → casual. Con registro: estado + `opciones_completo` para forzar destino: opciones solo si estado ≥ 4; confirmar-registro solo si estado = 3; finalizar solo si estado ≥ 4 y opciones completas. |
| **OpcionesService** | `estado = int(registro.get("estado") or 0)`. Si estado < 3 → no muestra listas (listo_estado1 = False). Si ≥ 3 → devuelve siguiente lista (sucursal / forma_pago / medio_pago). |
| **ConfirmarRegistroService** | Solo ejecuta la transición 3→4 si `estado == 3`. |

---

## Transiciones

```
                    ┌─────────────────────────────────────────────────────────┐
                    │  Sin registro en caché → clasificador devuelve "casual"  │
                    └─────────────────────────────────────────────────────────┘
                                              │
                    ┌─────────────────────────▼─────────────────────────────┐
                    │  POST /iniciar-flujo  o  extracción con venta/compra  │
                    │  → estado 0 (iniciar) o 0/1/2/3 (extracción)          │
                    └─────────────────────────┬─────────────────────────────┘
                                              │
  ┌───────────────────────────────────────────▼───────────────────────────────────────────┐
  │  ESTADO 0, 1, 2:  Clasificador → actualizar → Extracción (calcula 0|1|2|3)             │
  │  ESTADO 3:        Clasificador acepta confirmar-registro → ConfirmarRegistro → 4     │
  │                   Clasificador también escribe estado 4 al clasificar confirmar       │
  └───────────────────────────────────────────┬───────────────────────────────────────────┘
                                              │
                    ┌─────────────────────────▼─────────────────────────────┐
                    │  ESTADO 4:  Opciones (sucursal → forma_pago → medio)   │
                    │  Cuando opciones_completo → clasificador acepta        │
                    │  finalizar-operacion → FinalizarService (y escribe 4)  │
                    └───────────────────────────────────────────────────────┘
```

---

## Opciones completas (Estado 2 del flujo)

Se considera **opciones_completo** cuando el registro tiene:

- `id_sucursal`
- `forma_pago` (no vacío)
- `medio_pago` ∈ {"contado", "credito"}

Definido en `clasificador_service._opciones_completo`.

---

## Notas

1. **Campo en caché**: el nombre usado en el código es **`estado`** (numérico). En documentación antigua puede aparecer **`paso_actual`** (por ejemplo en `analizador_service` o README); el flujo principal usa `estado`.
2. **Config/estados.py**: está marcado como DEPRECATED; define constantes de texto (ej. `PENDIENTE_CONFIRMACION`). El flujo actual no depende de ellas; usa solo el entero 0–4.
3. **Opciones y estado 3**: `OpcionesService.get_next` acepta registro con **estado ≥ 3**. El **clasificador** solo envía a opciones cuando **estado ≥ 4**. En la práctica el usuario llega a opciones tras confirmar (3→4); si alguien llamara POST /opciones con estado 3, el servicio sí devolvería la primera lista.
4. **Protección del 4 en extracción**: si el registro ya está en estado 4, `ExtraccionService` no lo baja; usa `estado_calculado` solo cuando `estado_actual.get("estado") != 4`.
