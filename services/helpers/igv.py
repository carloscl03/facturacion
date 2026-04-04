"""
Cálculo centralizado de IGV (18%) con precisión Decimal.

Toda lógica de IGV del proyecto debe usar estas funciones para evitar
inconsistencias entre el monto_total almacenado y el detalle enviado a la API.

CONTRATO PHP (ws_sunat_venta.php / construirJsonSunat):
  - precio_unitario en detalle_items = precio CON IGV (bruto)
  - PHP calcula total comprobante: sum(precio_unitario × cantidad)
  - SUNAT valida: total == sum(valor_total_item)
  - Por lo tanto: valor_total_item DEBE ser = precio_unitario × cantidad
  - valor_subtotal_item = base (sin IGV), valor_igv = total - base
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
        total = m.quantize(_2D, ROUND_HALF_UP)
        base = (total / _FACTOR).quantize(_2D, ROUND_HALF_UP)
        igv = (total - base).quantize(_2D, ROUND_HALF_UP)
    else:
        base = m.quantize(_2D, ROUND_HALF_UP)
        total = (base * _FACTOR).quantize(_2D, ROUND_HALF_UP)
        igv = (total - base).quantize(_2D, ROUND_HALF_UP)

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

    Contrato PHP: precio_unitario en el payload = precio CON IGV.
    PHP calcula total = sum(precio_unitario × cantidad) y valida contra sum(valor_total_item).

    Por lo tanto:
      - precio_unitario (output) = precio CON IGV
      - valor_total_item = precio_con_igv × cantidad  (lo que PHP calcularía)
      - valor_subtotal_item = precio_base × cantidad
      - valor_igv = total - subtotal
    """
    pu = Decimal(str(precio_unitario))
    qty = Decimal(str(cantidad))

    if sin_igv:
        # Para notas: no hay IGV, precio_unitario = precio tal cual
        total = (qty * pu).quantize(_2D, ROUND_HALF_UP)
        return {
            "precio_unitario": _r(pu),
            "cantidad": float(qty),
            "valor_subtotal_item": float(total),
            "valor_igv": 0.0,
            "valor_total_item": float(total),
        }

    if igv_incluido:
        # Precio del usuario/catálogo ya incluye IGV → es el precio_unitario final
        pu_con_igv = pu.quantize(_2D, ROUND_HALF_UP)
        pu_base = (pu_con_igv / _FACTOR).quantize(_2D, ROUND_HALF_UP)
    else:
        # Precio del usuario es base → calcular precio con IGV
        pu_base = pu.quantize(_2D, ROUND_HALF_UP)
        pu_con_igv = (pu_base * _FACTOR).quantize(_2D, ROUND_HALF_UP)

    # valor_total_item = pu_con_igv × qty  (exactamente como PHP lo calcularía)
    total = (pu_con_igv * qty).quantize(_2D, ROUND_HALF_UP)
    subtotal = (pu_base * qty).quantize(_2D, ROUND_HALF_UP)
    igv = (total - subtotal).quantize(_2D, ROUND_HALF_UP)

    return {
        "precio_unitario": float(pu_con_igv),   # CON IGV (como espera PHP)
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

    Garantiza: monto_total == sum(valor_total_item) == total que PHP calcula
    (sum de precio_unitario × cantidad por cada ítem).
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
