"""
NIVEL 1 ROBUSTEZ: replay de payloads históricos contra los nuevos validadores.

Para cada fila de bot_api_log, evalúa si el payload pasaría las validaciones
nuevas (defense in depth) que se aplicaron en bot y backend:

  V1: cada item: sub+igv-desc ≈ total (tolerancia 0.05)
  V2: agregado: sum(sub)+sum(igv) ≈ sum(total) (tolerancia 0.10)
  V3: sum(total) > 0 (rechazo de comprobantes en cero — fix #661)
  V4: sum(total) ≈ monto_total denormalizado (consistencia interna)

Categoriza cada fila por qué validaciones pasa/falla.
NO crea registros, NO llama APIs.

Uso:
    python test/integration/test_replay_bot_api_log.py

Variables de entorno:
    REPLAY_LIMIT    cantidad de filas (default 100)
    REPLAY_VERBOSE  1 para detalles por fila (default 0)
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

_raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

import psycopg2  # type: ignore


DB_CONFIG = {
    "host": "database-1-maravia-produccion.cluster-cyh6ckayy1vd.us-east-1.rds.amazonaws.com",
    "port": 5432,
    "dbname": "maravia",
    "user": os.getenv("PG_USER", "shualt"),
    "password": os.getenv("PG_PASSWORD", "H3ll022Maravia"),
    "connect_timeout": 10,
}

LIMIT = int(os.getenv("REPLAY_LIMIT", "100"))
VERBOSE = os.getenv("REPLAY_VERBOSE", "0") == "1"


def _normalizar_payload(p):
    if isinstance(p, dict):
        return p
    if isinstance(p, str):
        try:
            return json.loads(p)
        except (TypeError, ValueError):
            return None
    return None


def validar_payload(payload, monto_total_log):
    """
    Aplica las validaciones nuevas a un payload. Retorna dict con flags.
    """
    items = payload.get("detalle_items") or payload.get("detalles") or []
    sum_sub = sum(float(i.get("valor_subtotal_item") or 0) for i in items)
    sum_igv = sum(float(i.get("valor_igv") or 0) for i in items)
    sum_total = sum(float(i.get("valor_total_item") or 0) for i in items)

    # V1: coherencia por item
    v1_ok = True
    v1_errores = []
    for idx, it in enumerate(items):
        s = float(it.get("valor_subtotal_item") or 0)
        i_ = float(it.get("valor_igv") or 0)
        t = float(it.get("valor_total_item") or 0)
        d = float(it.get("valor_descuento") or 0)
        esperado = round(s + i_ - d, 2)
        if abs(esperado - round(t, 2)) > 0.05:
            v1_ok = False
            v1_errores.append(f"item#{idx}: {s}+{i_}-{d}={esperado} ≠ {t}")

    # V2: agregado
    esperado_total = round(sum_sub + sum_igv, 2)
    v2_ok = abs(esperado_total - round(sum_total, 2)) <= 0.10

    # V3: rechazo cero (fix #661)
    v3_ok = round(sum_total, 2) > 0

    # V4: consistencia con monto_total denormalizado
    v4_ok = True
    if monto_total_log > 0 and sum_total > 0:
        ratio = sum_total / monto_total_log
        v4_ok = 0.5 < ratio < 2.0

    return {
        "items_count": len(items),
        "sum_sub": sum_sub,
        "sum_igv": sum_igv,
        "sum_total": sum_total,
        "monto_total_log": monto_total_log,
        "v1_coherencia_items": v1_ok,
        "v1_errores": v1_errores,
        "v2_coherencia_agregada": v2_ok,
        "v3_no_cero": v3_ok,
        "v4_consistente_con_monto_log": v4_ok,
    }


def categorizar(val):
    """Mapea resultado de validación a categoría human-readable."""
    if val["items_count"] == 0:
        return "SIN_ITEMS"

    if not val["v3_no_cero"]:
        # Caso #661: comprobante con S/0
        if val["monto_total_log"] > 0:
            return "ROTO_BOT_REPORTÓ_NO_CERO_PERO_ENVIÓ_CERO"
        return "ROTO_TODO_EN_CERO"

    if not val["v1_coherencia_items"]:
        return "ROTO_INCOHERENTE_ITEM"

    if not val["v2_coherencia_agregada"]:
        return "ROTO_INCOHERENTE_AGREGADO"

    if not val["v4_consistente_con_monto_log"]:
        return "INCONSISTENTE_DETALLE_VS_MONTO_LOG"

    return "OK_PASARIA_VALIDACIONES"


def run():
    print(f"=== REPLAY bot_api_log → validadores nuevos (limit={LIMIT}) ===\n")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, api_destino, operacion, resultado, monto_total,
               payload_enviado, created_at
        FROM bot_api_log
        WHERE payload_enviado IS NOT NULL
          AND api_destino IN ('php_venta', 'php_compra')
        ORDER BY created_at DESC
        LIMIT %s
    """, (LIMIT,))

    rows = cur.fetchall()
    print(f"Procesando {len(rows)} filas...\n")

    contador = Counter()
    casos_rotos = []
    casos_inconsistentes = []

    for r in rows:
        row_id, api, operacion, resultado, monto_total, payload, created_at = r
        payload = _normalizar_payload(payload)
        if not payload:
            contador["SKIPPED_payload_invalido"] += 1
            continue

        monto_log = float(monto_total or 0)
        val = validar_payload(payload, monto_log)
        cat = categorizar(val)
        contador[cat] += 1

        if VERBOSE or cat.startswith("ROTO_") or cat == "INCONSISTENTE_DETALLE_VS_MONTO_LOG":
            print(
                f"  #{row_id:4d}  {api:11s}  {resultado:8s}  "
                f"items={val['items_count']}  sum_total={val['sum_total']:8.2f}  "
                f"monto_log={monto_log:8.2f}  → {cat}"
            )

        if cat.startswith("ROTO_"):
            casos_rotos.append({"id": row_id, "cat": cat, "val": val})
        elif cat == "INCONSISTENTE_DETALLE_VS_MONTO_LOG":
            casos_inconsistentes.append({"id": row_id, "val": val})

    cur.close()
    conn.close()

    print("\n=== RESUMEN ===")
    total = sum(contador.values())
    print(f"Total procesados: {total}\n")
    print(f"{'Categoría':<55} {'Cant':>5}  {'%':>6}")
    print("-" * 72)
    for cat, n in sorted(contador.items(), key=lambda kv: -kv[1]):
        pct = (n / total * 100) if total else 0
        marca = ""
        if cat == "OK_PASARIA_VALIDACIONES":
            marca = " ✅"
        elif cat.startswith("ROTO_"):
            marca = " ❌ los fixes RECHAZARÍAN esto ahora"
        elif cat == "INCONSISTENTE_DETALLE_VS_MONTO_LOG":
            marca = " ⚠️ bot reportó != envió"
        elif cat == "SIN_ITEMS":
            marca = " ⚠️"
        print(f"  {cat:<53} {n:>5}  {pct:>5.1f}%{marca}")

    print("\n=== CONCLUSIÓN ===")
    rotos = sum(v for k, v in contador.items() if k.startswith("ROTO_"))
    inconsistentes = sum(v for k, v in contador.items() if k == "INCONSISTENTE_DETALLE_VS_MONTO_LOG")
    ok = contador.get("OK_PASARIA_VALIDACIONES", 0)

    print(f"  • {ok}/{total} payloads históricos PASARÍAN las validaciones nuevas")
    if rotos:
        print(f"  • {rotos}/{total} payloads históricos serían RECHAZADOS por los fixes nuevos")
        print(f"    (eran bugs que los fixes ahora previenen)")
    if inconsistentes:
        print(f"  • {inconsistentes}/{total} payloads con inconsistencia detalle vs monto_total denormalizado")

    if casos_rotos and not VERBOSE:
        print(f"\nCasos rotos detectados (primeros 5):")
        for c in casos_rotos[:5]:
            print(f"  #{c['id']}  {c['cat']}  monto_log={c['val']['monto_total_log']:.2f}  sum_total={c['val']['sum_total']:.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(run())
