"""
Cálculo centralizado de IGV (18%) con precisión Decimal.

Toda lógica de IGV del proyecto debe usar estas funciones para evitar
inconsistencias entre el monto_total almacenado y el detalle enviado a la API.

REGLA SUNAT: Los cálculos deben ir siempre de base → IGV → total.
  - precio_unitario en el detalle = precio BASE (sin IGV)
  - valor_subtotal_item = precio_base × cantidad
  - valor_igv = subtotal × 0.18
  - valor_total_item = subtotal + igv
Esto garantiza que sum(subtotal) + sum(igv) == sum(total) siempre,
que es lo que SUNAT valida al emitir el comprobante.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_TASA = Decimal("0.18")
_FACTOR = Decimal("1.18")
_2D = Decimal("0.01")


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
    Calcula (monto_total, base, igv) de forma determinística.

    - sin_igv=True  -> notas/honorarios: base=0, igv=0, total=monto
    - igv_incluido=True  -> monto ya incluye IGV (default)
    - igv_incluido=False -> monto es base imponible, se agrega IGV

    Siempre calcula de base → igv → total para consistencia SUNAT.
    """
    if monto <= 0:
        return (0.0, 0.0, 0.0)

    m = Decimal(str(monto))

    if sin_igv:
        return (_r(m), 0.0, 0.0)

    if igv_incluido:
        base = (m / _FACTOR).quantize(_2D, ROUND_HALF_UP)
    else:
        base = m.quantize(_2D, ROUND_HALF_UP)

    # Siempre: igv = base * 0.18, total = base + igv
    igv = (base * _TASA).quantize(_2D, ROUND_HALF_UP)
    total = (base + igv).quantize(_2D, ROUND_HALF_UP)

    return (float(total), float(base), float(igv))


def calcular_item(
    precio_unitario: float,
    cantidad: float,
    *,
    igv_incluido: bool = True,
    sin_igv: bool = False,
) -> dict:
    """
    Calcula los valores de un ítem del detalle para la API SUNAT.

    Retorna dict con:
      precio_unitario  (precio unitario BASE sin IGV, como espera SUNAT)
      cantidad
      valor_subtotal_item  (base = precio_base × cantidad)
      valor_igv            (subtotal × 0.18)
      valor_total_item     (subtotal + igv)

    SUNAT valida: sum(subtotal) + sum(igv) == sum(total)
    Al calcular siempre base→igv→total, esto se garantiza.
    """
    pu = Decimal(str(precio_unitario))
    qty = Decimal(str(cantidad))

    if sin_igv:
        total = (qty * pu).quantize(_2D, ROUND_HALF_UP)
        return {
            "precio_unitario": _r(pu),
            "cantidad": float(qty),
            "valor_subtotal_item": float(total),
            "valor_igv": 0.0,
            "valor_total_item": float(total),
        }

    if igv_incluido:
        # El precio del usuario ya incluye IGV → extraer base
        pu_base = (pu / _FACTOR).quantize(_2D, ROUND_HALF_UP)
    else:
        # El precio del usuario es base
        pu_base = pu.quantize(_2D, ROUND_HALF_UP)

    # Siempre: subtotal = base * qty, igv = subtotal * 0.18, total = subtotal + igv
    subtotal = (pu_base * qty).quantize(_2D, ROUND_HALF_UP)
    igv = (subtotal * _TASA).quantize(_2D, ROUND_HALF_UP)
    total = (subtotal + igv).quantize(_2D, ROUND_HALF_UP)

    return {
        "precio_unitario": float(pu_base),
        "cantidad": float(qty),
        "valor_subtotal_item": float(subtotal),
        "valor_igv": float(igv),
        "valor_total_item": float(total),
    }


def sumar_productos(
    productos: list[dict],
    *,
    igv_incluido: bool = True,
    sin_igv: bool = False,
) -> tuple[float, float, float]:
    """
    Suma todos los productos y retorna (monto_total, base, igv) consistente
    con lo que calcular_item daría para cada uno.

    Garantiza: monto_total == sum(valor_total_item) == sum(subtotal) + sum(igv)
    """
    total_acc = Decimal("0")
    base_acc = Decimal("0")
    igv_acc = Decimal("0")

    for p in productos:
        pu = float(p.get("precio_unitario") or p.get("precio") or 0)
        qty = float(p.get("cantidad", 1))
        if pu <= 0:
            continue
        item = calcular_item(pu, qty, igv_incluido=igv_incluido, sin_igv=sin_igv)
        total_acc += Decimal(str(item["valor_total_item"]))
        base_acc += Decimal(str(item["valor_subtotal_item"]))
        igv_acc += Decimal(str(item["valor_igv"]))

    return (_r(total_acc), _r(base_acc), _r(igv_acc))
