"""
Cálculo centralizado de IGV (18%) con precisión Decimal.

CONTRATO PHP (confirmado con test_precalculado.py contra ws_venta.php):
  - precio_unitario en detalle_items = precio BASE (sin IGV), 10dp para precisión SUNAT
  - valor_subtotal_item = round(pu_base × qty, 2)
  - valor_igv = round(subtotal × 0.18, 2)
  - valor_total_item = subtotal + igv (CON IGV)
  - El SP suma valor_total_item para Venta.monto → queda con IGV correcto

Helpers:
  - calcular_item(pu, qty) → (pu_base, sub, igv, total) precalculados para el payload
  - calcular_igv(monto)    → (total, base, igv) para resumen visual
  - sumar_productos(prods) → suma agregada consistente con calcular_item
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_TASA = Decimal("0.18")
_FACTOR = Decimal("1.18")
_2D = Decimal("0.01")
_10D = Decimal("0.0000000001")  # 10 decimales para precio_unitario (precisión SUNAT UBL)


def _r(d: Decimal) -> float:
    """Redondea a 2 decimales y convierte a float."""
    return float(d.quantize(_2D, ROUND_HALF_UP))


def es_tipo_sin_igv(tipo_documento: str | None) -> bool:
    """True si el tipo de documento no lleva IGV (notas, honorarios)."""
    td = (tipo_documento or "").strip().lower()
    return td in ("nota de venta", "nota de compra", "recibo por honorarios")


def calcular_igv(
    monto: float,
    *,
    igv_incluido: bool = True,
    sin_igv: bool = False,
) -> tuple[float, float, float]:
    """
    Calcula (monto_total, base, igv) para resumen visual.

    - sin_igv=True  -> notas/honorarios: base=0, igv=0, total=monto
    - igv_incluido=True  -> monto ya incluye IGV (default)
    - igv_incluido=False -> monto es base imponible, se agrega IGV
    """
    if monto <= 0:
        return (0.0, 0.0, 0.0)

    m = Decimal(str(monto))

    if sin_igv:
        return (_r(m), 0.0, 0.0)

    if igv_incluido:
        total = m.quantize(_2D, ROUND_HALF_UP)
        base = (total / _FACTOR).quantize(_2D, ROUND_HALF_UP)
        igv = (total - base).quantize(_2D, ROUND_HALF_UP)
    else:
        base = m.quantize(_2D, ROUND_HALF_UP)
        total = (base * _FACTOR).quantize(_2D, ROUND_HALF_UP)
        igv = (total - base).quantize(_2D, ROUND_HALF_UP)

    return (float(total), float(base), float(igv))


def precio_base(precio: float, *, igv_incluido: bool = True, sin_igv: bool = False) -> float:
    """
    Convierte un precio a precio BASE (sin IGV) para el payload.

    2 decimales — PHP redondea pu a 2dp en ambos caminos de validación,
    por lo que enviar más precisión causa mismatch.
    """
    if sin_igv or not igv_incluido:
        return round(precio, 2)
    return _r(Decimal(str(precio)) / _FACTOR)


def valor_total_item(pu_base: float, qty: float, *, sin_igv: bool = False) -> float:
    """
    Calcula valor_total_item = pu_base × qty a 2 decimales.
    PHP usa 2dp para pu en ambos caminos de validación.
    """
    return _r(Decimal(str(pu_base)) * Decimal(str(qty)))


def calcular_item(
    precio_unitario: float,
    qty: float,
    *,
    igv_incluido: bool = True,
    sin_igv: bool = False,
) -> tuple[float, float, float, float]:
    """
    Devuelve (pu_base, valor_subtotal_item, valor_igv, valor_total_item) precalculados.

    Estrategia base→IGV→total (consistente con SUNAT):
      - pu_base = precio / 1.18 (si incluye IGV) o precio tal cual (si no)
      - subtotal = round(pu_base × qty, 2)
      - igv = round(subtotal × 0.18, 2)
      - total = subtotal + igv

    Para notas/honorarios (sin_igv=True): igv=0, subtotal=total=pu × qty.
    El precio_unitario se mantiene con alta precisión (10dp) para evitar
    errores de redondeo acumulados en SUNAT.
    """
    pu = Decimal(str(precio_unitario))
    q = Decimal(str(qty))

    if sin_igv:
        pu_b = pu.quantize(_10D, ROUND_HALF_UP)
        subtotal = (pu * q).quantize(_2D, ROUND_HALF_UP)
        return (float(pu_b), float(subtotal), 0.0, float(subtotal))

    if igv_incluido:
        pu_b = (pu / _FACTOR).quantize(_10D, ROUND_HALF_UP)
    else:
        pu_b = pu.quantize(_10D, ROUND_HALF_UP)

    subtotal = (pu_b * q).quantize(_2D, ROUND_HALF_UP)
    igv = (subtotal * _TASA).quantize(_2D, ROUND_HALF_UP)
    total = subtotal + igv
    return (float(pu_b), float(subtotal), float(igv), float(total))


def sumar_productos(
    productos: list[dict],
    *,
    igv_incluido: bool = True,
    sin_igv: bool = False,
) -> tuple[float, float, float]:
    """
    Suma todos los productos y retorna (monto_total, base, igv) para resumen visual.

    monto_total = sum(precio_con_igv × cantidad) — lo que el usuario ve.
    base = sum(precio_base × cantidad).
    igv = total - base.

    Respeta igv_incluido por producto si el producto tiene el campo "igv_incluido".
    """
    total_acc = Decimal("0")
    base_acc = Decimal("0")

    for p in productos:
        pu_raw = float(p.get("precio_unitario") or p.get("precio") or 0)
        qty = float(p.get("cantidad", 1))
        if pu_raw <= 0:
            continue

        # igv_incluido por producto (override del global)
        p_igv_incl = p.get("igv_incluido")
        if p_igv_incl is not None:
            prod_igv_incluido = p_igv_incl is True or str(p_igv_incl).strip().lower() == "true"
        else:
            prod_igv_incluido = igv_incluido

        pu = Decimal(str(pu_raw))
        q = Decimal(str(qty))

        if sin_igv:
            item_total = (pu * q).quantize(_2D, ROUND_HALF_UP)
            total_acc += item_total
        elif prod_igv_incluido:
            # Precio ya incluye IGV → total = pu × qty, base = (pu/1.18) × qty
            item_total = (pu * q).quantize(_2D, ROUND_HALF_UP)
            pu_b = (pu / _FACTOR).quantize(_2D, ROUND_HALF_UP)
            item_base = (pu_b * q).quantize(_2D, ROUND_HALF_UP)
            total_acc += item_total
            base_acc += item_base
        else:
            # Precio es base → total = round(pu × 1.18, 2) × qty
            pu_con = (pu * _FACTOR).quantize(_2D, ROUND_HALF_UP)
            item_total = (pu_con * q).quantize(_2D, ROUND_HALF_UP)
            item_base = (pu * q).quantize(_2D, ROUND_HALF_UP)
            total_acc += item_total
            base_acc += item_base

    total = _r(total_acc)
    base = _r(base_acc)
    igv = round(total - base, 2) if not sin_igv else 0.0
    return (total, base, igv)
