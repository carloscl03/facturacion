"""
Cálculo centralizado de IGV (18%) con precisión Decimal.

CONTRATO PHP (confirmado con tests reales contra ws_venta.php):
  - precio_unitario en detalle_items = precio CON IGV (bruto)
  - valor_total_item = precio_unitario × cantidad
  - valor_subtotal_item = 0, valor_igv = 0 → PHP los recalcula internamente
  - PHP valida: sum(precio_unitario × cantidad) == sum(valor_total_item)

Nuestro cálculo de sub/igv es SOLO para el resumen visual al usuario.
El payload a la API envía sub=0, igv=0 y deja que PHP calcule.
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


def precio_con_igv(precio: float, *, igv_incluido: bool = True, sin_igv: bool = False) -> float:
    """
    Convierte un precio a precio CON IGV (lo que va en el payload como precio_unitario).

    - Si igv_incluido=True o sin_igv=True: devuelve tal cual (ya incluye IGV o no aplica).
    - Si igv_incluido=False: es base, agrega IGV (× 1.18).
    """
    if sin_igv or igv_incluido:
        return round(precio, 2)
    return _r(Decimal(str(precio)) * _FACTOR)


def sumar_productos(
    productos: list[dict],
    *,
    igv_incluido: bool = True,
    sin_igv: bool = False,
) -> tuple[float, float, float]:
    """
    Suma todos los productos y retorna (monto_total, base, igv).

    Calcula monto_total = sum(precio_con_igv × cantidad), que es exactamente
    lo que PHP calculará al recibir el payload.

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

        pu_final = Decimal(str(precio_con_igv(pu_raw, igv_incluido=prod_igv_incluido, sin_igv=sin_igv)))
        q = Decimal(str(qty))

        item_total = (pu_final * q).quantize(_2D, ROUND_HALF_UP)
        total_acc += item_total

        if not sin_igv:
            pu_base = (pu_final / _FACTOR).quantize(_2D, ROUND_HALF_UP)
            item_base = (pu_base * q).quantize(_2D, ROUND_HALF_UP)
            base_acc += item_base

    total = _r(total_acc)
    base = _r(base_acc)
    igv = round(total - base, 2) if not sin_igv else 0.0
    return (total, base, igv)
