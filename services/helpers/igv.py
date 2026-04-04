"""
Cálculo centralizado de IGV (18%) con precisión Decimal.

Toda lógica de IGV del proyecto debe usar estas funciones para evitar
inconsistencias entre el monto_total almacenado y el detalle enviado a la API.
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
    """
    if monto <= 0:
        return (0.0, 0.0, 0.0)

    m = Decimal(str(monto))

    if sin_igv:
        return (_r(m), 0.0, 0.0)

    if igv_incluido:
        base = (m / _FACTOR).quantize(_2D, ROUND_HALF_UP)
        total = m.quantize(_2D, ROUND_HALF_UP)
        igv = (total - base).quantize(_2D, ROUND_HALF_UP)
    else:
        base = m.quantize(_2D, ROUND_HALF_UP)
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
    Calcula los valores de un ítem del detalle para la API.

    Retorna dict con:
      precio_unitario  (precio unitario con IGV incluido, como espera la API)
      cantidad
      valor_subtotal_item  (base sin IGV)
      valor_igv
      valor_total_item     (base + IGV)
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

    bruto = (qty * pu).quantize(_2D, ROUND_HALF_UP)

    if igv_incluido:
        # El precio del usuario ya incluye IGV
        total = bruto
        base = (bruto / _FACTOR).quantize(_2D, ROUND_HALF_UP)
        igv = (total - base).quantize(_2D, ROUND_HALF_UP)
        pu_final = pu  # ya incluye IGV
    else:
        # El precio del usuario es base; agregar IGV
        base = bruto
        igv = (base * _TASA).quantize(_2D, ROUND_HALF_UP)
        total = (base + igv).quantize(_2D, ROUND_HALF_UP)
        # La API espera precio_unitario con IGV incluido
        pu_final = (pu * _FACTOR).quantize(_2D, ROUND_HALF_UP)

    return {
        "precio_unitario": float(pu_final),
        "cantidad": float(qty),
        "valor_subtotal_item": float(base),
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

    Esto garantiza que monto_total == sum(valor_total_item) del detalle.
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
