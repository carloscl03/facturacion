# Bitácora de tickets de soporte

Análisis técnico de tickets relacionados con el bot. Documenta bug raíz,
componente afectado y acción tomada por cada uno. Complementa la BD
`ticket_soporte` con el contexto del bot que ahí no queda.

**Convenciones:**
- Categoría de bug: `visión upstream` (servicio n8n/lambda que parsea imágenes), `bot Python` (este repo), `PHP backend` (ws_*.php), `UX` (problema flujo conversación), `infra` (deploy/red/redis).
- Si fix nuevo, anotar commit + estado deploy.
- Si está fuera de scope del bot, anotar a quién reportar.

---

## Ticket #339 — TKT-2026-00091

**Asunto:** Error al registrar factura con Marita
**Estado/Prioridad:** Abierto / Media
**Fecha:** 2026-05-29
**Empresa:** 1
**Reporta:** usr 2 (sin asignar)

### Reporte
"extrajo muy mal los datos de la factura"

2 screenshots: (1) boleta original SUNAT EB01-75 del proveedor ARAUCO GRANDEZ
CARLOS FELIPE; (2) resumen del bot WhatsApp con montos incorrectos.

### Análisis

**Boleta real (EB01-75):**
- Cantidad: 1 — seguimiento incubadora scale proyecto maraviIA
- Importe venta (subtotal sin IGV): S/ 1779.66
- **Importe Total con IGV: S/ 2100.00**

**Bot extrajo:**
- Total: S/ 1779.66 ❌
- Subtotal: S/ 1508.19 (= 1779.66/1.18)
- IGV: S/ 271.47

El bot tomó "Importe venta" (que en SUNAT es el subtotal sin IGV) y lo trató
como si fuera el total. Luego dividió entre 1.18 para sacar la base, lo que
multiplica el error. El total real (S/2100) quedó descartado.

### Bug raíz

- **Categoría:** visión upstream
- **Componente:** servicio n8n/lambda que parsea imagen de comprobante SUNAT
- **No es bug del bot Python.** Bot recibe JSON con campos mal asignados; los
  fixes de IGV recientes (commits `5aefc96`, `3992b93`) no aplican porque el
  monto extraído ya es base, no total con IGV mal interpretado.

### Acción tomada

- Reportar al equipo backend/n8n: servicio visión confunde "Importe venta"
  con total en boletas SUNAT. Debería leer "Importe Total" o el monto al pie.
- No requiere cambio en `maravia-bot`.
- Ticket NO finalizó (estado bot < 5), por eso no aparece en `bot_api_log`.

---

## Ticket #661 — TKT-2026-00141

**Asunto:** Maravita graba mal la información de datos de compras y ventas
**Estado/Prioridad:** Abierto / **Crítica**
**Fecha:** 2026-06-11
**Empresa:** 25 (Magic Innovation Labs)
**Reporta:** usr 2 → asignado usr 309

### Reporte
Dos bugs separados:
- **Bug A (compra):** bot reportó "✅ COMPRA REGISTRADA — S/34 — balón de gas",
  pero en sistema web la compra #28 quedó con Subtotal/IGV/Total = S/0.00.
- **Bug B (venta):** bot reportó "✨ VENTA REGISTRADA EN SUNAT — Kevin Cáceda
  — S/83.76 — 3 filtros magic", pero el PDF SUNAT BM01-000001 emitido salió
  con Precio Unitario/Subtotal/IGV/Total = S/0.00. **SUNAT aceptó boleta
  legal con monto cero.**

### Análisis

Cruzando `bot_api_log` con tablas `compra`/`venta`/`detalleitem_*`:

- `bot_api_log #133` (compra): `monto_total=34.00` denormalizado, **pero
  payload_enviado.detalles[0]` tenía `precio_unitario=0`, `valor_total_item=0`**.
  PHP guardó lo que llegó. `compra.monto=0`, `detalleitem_compra.valor_total_item=0`.
- `bot_api_log #67` (venta): mismo patrón. `monto_total=83.76` denormalizado,
  pero `detalle_items[0].precio_unitario=0`. SUNAT emitió boleta con cero.

### Bug raíz

- **Categoría:** bot Python
- **Componente:** [services/helpers/productos.py](services/helpers/productos.py),
  [services/helpers/compra_mapper.py](services/helpers/compra_mapper.py)
- **Causa:** extractor IA pone `precio: 0` en items cuando el usuario solo da
  el monto total sin precio por unidad (ej. "balón de gas total 34", "3
  filtros total 83.76"). Los mappers no compensaban — pasaban precio=0 al
  detalle del payload, lo que terminaba en cero en BD y en SUNAT.
- **Inconsistencia interna:** `monto_total` (denormalizado por bot) tenía el
  valor correcto, pero el detalle iba en cero. Bot reportaba al usuario el
  monto correcto pero enviaba cero al backend.

### Acción tomada

- **Fix mappers:** si todos los productos tienen `precio=0` pero
  `monto_total > 0`, distribuir `monto_total` entre items proporcionalmente
  a `cantidad`. Aplicado en `construir_detalle_desde_registro` y
  `construir_detalles_compra`.
- **Tests nuevos** en `test/test_robustez_igv_casos_reales.py`:
  - `test_caso_661_compra_balon_gas_distribuye_monto_total`
  - `test_caso_661_venta_filtros_distribuye_monto_total`
  - `test_precio_cero_sin_monto_total_no_inventa` (caso edge: si no hay total tampoco, NO inventa)
  - `test_un_item_con_precio_otros_sin_no_redistribuye` (caso edge: respeta intención usuario)
- **Bug adicional reportado:** "en edición de compra no se puede editar el
  item" — UI/web, fuera de scope del bot. Reportar al equipo frontend.

### Pendiente

- Acción correctiva en BD: anular compra #1863 (S/0) y venta #1744 (S/0,
  boleta SUNAT BM01-000001). La boleta SUNAT con cero es problema fiscal
  — requiere emitir nota de crédito.

---

## Ticket #67 — TKT-2026-00053

**Asunto:** Error al registrar factura con el agente
**Estado/Prioridad:** En progreso / **Crítica**
**Fecha:** 2026-04-22 (creado), 2026-05-21 (último comentario cliente)
**Empresa:** 1
**Reporta:** usr 2 → asignado usr 58

### Reporte
Tres manifestaciones del mismo bug IGV (cronológicas):

1. **Compra #73 (abr 2026):** P.Unitario S/93.22 pero Subtotal=0, IGV=0,
   Total=S/93.22. PHP no recalculó IGV — quedó "todo en P.Unitario".
2. **WhatsApp bot (abr 2026):** bot reportó S/110.00 al usuario; sistema
   guardó S/93.22 (= 110/1.18). Bot interpretó precio como base sin IGV
   y dividió antes de enviar.
3. **Compra #204 (may 2026, tras fix interim):** chip claro pu=8.47,
   igv=1.52, total=9.99. Cliente dice "no considera todos los decimales"
   — debió ser igv=1.53, total=10.00.

### Bug raíz

Mismo bug compuesto que #232, #339, #661:
- **Manifestación A:** servicio visión/extracción IA pone `igv_incluido=False`
  cuando el monto leído del comprobante ya incluye IGV.
- **Manifestación B:** redondeo de IGV sobre subtotal redondeado pierde 1
  céntimo (igv.py calculaba `igv = round(round(pu_b × qty, 2) × 0.18, 2)`
  en vez de derivarlo por resta del total preservado).

### Acción tomada

Cubierto por los 7 commits pusheados a `main` el 2026-06-11:
- `5aefc96` — bot fuerza `igv_incluido=True` cuando viene de comprobante F/B/E
- `3992b93` — bot pre-procesador con hint determinístico cuando mensaje es
  JSON visión con `monto_total + impuesto > 0`
- `62cd0da` — bot mappers usan `calcular_item` con valores precalculados
- `70fcf9a` — bot `igv.py` preserva precisión: `total = pu × qty`, `igv = total - subtotal`
- `9403b89` (backend) — defense in depth: validación coherencia, rechazo
  suma=0, throw SUNAT con totalVenta≤0, prompt visión endurecido

### Pendiente

- Cerrar ticket #67 después de deploy bot + backend PHP.
- Verificar compras #73, #204 — quedaron mal en BD, requieren corrección
  manual o reemisión.

---

## Ticket #42 — TKT-2026-00035 (FUERA DE SCOPE)

**Asunto:** Error en cálculo de boletas
**Categoría:** ❌ NO es bot WhatsApp

**Hallazgo:** "Boletas" aquí = boletas de pago de empleados (planilla/RRHH),
NO boletas de venta SUNAT. Bug en módulo PHP de planilla: cliente cambió
puesto del empleado pero el cálculo sigue usando el sueldo anterior
(S/565 vs S/1130 esperado).

**Acción:** reportar al equipo backend PHP módulo RRHH. Fuera de scope
del bot WhatsApp.

---

## Tickets revisados y descartados (fuera de scope bot WhatsApp)

Resumen de tickets revisados que NO son del bot maravia-bot:

| # | Asunto | Categoría real |
|---|---|---|
| #26 | Chat WhatsApp Maravia no funciona | Chatweb (UI). Sin adjuntos/info concreta. |
| #49 | Nota de crédito | Módulo PHP notas crédito SUNAT (web). |
| #57 | Problemas con chatbot | Otro bot ("bot atención al cliente"). Empresa 19. |
| #68 | No verificar importe pendiente IGV | Módulo PHP tesorería. |
| #200 | Mensaje recuperación chatbot | Otro bot ("bot atención al cliente"), feature de mensajes a clientes inactivos. |

**Conclusión review batch 2026-06-11:** de 7 tickets pendientes revisados,
solo **#67 era del bot** y ya está cubierto por los 7 commits de hoy.
Los demás corresponden a otros productos (chatweb, bot atención cliente,
módulo RRHH, tesorería, notas crédito web).
