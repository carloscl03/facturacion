#!/usr/bin/env python3
"""
CLI para consultar bot_api_log desde terminal (local o dentro del contenedor).

Uso:
    python scripts/ver_logs.py                     # Últimos 20 logs
    python scripts/ver_logs.py --limite 50         # Últimos 50
    python scripts/ver_logs.py --resultado fallido # Solo fallidos
    python scripts/ver_logs.py --wa-id 51987654321 # De un usuario
    python scripts/ver_logs.py --api php_venta     # Solo ventas
    python scripts/ver_logs.py --desde 2026-04-01 --hasta 2026-04-24
    python scripts/ver_logs.py --id 42             # Detalle completo de un log
    python scripts/ver_logs.py --follow            # Tail -f (polling cada 5s)

Variables de entorno (opcional):
    URL_BOT_API_LOG=https://api.maravia.pe/servicio/ws_bot_api_log.php
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

import requests

URL_DEFAULT = os.getenv("URL_BOT_API_LOG", "https://api.maravia.pe/servicio/ws_bot_api_log.php")

# Colores ANSI (funcionan en bash, PowerShell moderno, y terminales Linux)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
GRAY = "\033[90m"


def _color(text: str, code: str, use_color: bool = True) -> str:
    if not use_color:
        return text
    return f"{code}{text}{RESET}"


def _fmt_monto(m, moneda: str | None = None) -> str:
    if m is None or m == "":
        return "-"
    try:
        val = float(m)
        sim = moneda or ""
        return f"{sim} {val:,.2f}".strip()
    except (ValueError, TypeError):
        return str(m)


def _fmt_fecha(ts: str | None) -> str:
    if not ts:
        return "-"
    try:
        # PostgreSQL retorna ISO 8601
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(ts)[:19]


def _resolver_fecha(s: str | None) -> str | None:
    """Resuelve 'hoy', 'ayer', 'hace-7d', etc. a YYYY-MM-DD."""
    if not s:
        return None
    s = s.strip().lower()
    hoy = date.today()
    if s == "hoy":
        return hoy.isoformat()
    if s == "ayer":
        return (hoy - timedelta(days=1)).isoformat()
    if s.startswith("hace-") and s.endswith("d"):
        try:
            dias = int(s[5:-1])
            return (hoy - timedelta(days=dias)).isoformat()
        except ValueError:
            pass
    # Asumir que ya es YYYY-MM-DD
    return s


def _post(url: str, body: dict, timeout: int = 15) -> dict:
    try:
        r = requests.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=timeout)
        try:
            return r.json()
        except ValueError:
            return {"success": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except requests.RequestException as e:
        return {"success": False, "error": f"Conexión: {e}"}


def listar(args, use_color: bool) -> int:
    body: dict = {
        "codOpe": "LISTAR_BOT_API_LOG",
        "pagina": args.pagina,
        "limite": args.limite,
    }
    if args.wa_id:
        body["wa_id"] = args.wa_id
    if args.id_from:
        body["id_from"] = args.id_from
    if args.id_empresa:
        body["id_empresa"] = args.id_empresa
    if args.api:
        body["api_destino"] = args.api
    if args.operacion:
        body["operacion"] = args.operacion
    if args.resultado:
        body["resultado"] = args.resultado
    if args.tipo_falla:
        body["tipo_falla"] = args.tipo_falla
    desde = _resolver_fecha(args.desde)
    hasta = _resolver_fecha(args.hasta)
    if desde:
        body["fecha_inicio"] = desde
    if hasta:
        body["fecha_fin"] = hasta
    if args.buscar:
        body["busqueda"] = args.buscar

    data = _post(args.url, body)

    if not data.get("success"):
        print(_color(f"ERROR: {data.get('error') or data.get('message')}", RED, use_color))
        return 1

    rows = data.get("data") or []
    total = data.get("total", len(rows))
    pag = data.get("pagina", 1)
    tp = data.get("total_paginas", 1)

    if not rows:
        print(_color("Sin resultados para esos filtros.", DIM, use_color))
        return 0

    # Encabezado
    print(_color(f"Mostrando {len(rows)} de {total} logs  (página {pag}/{tp})", BOLD, use_color))
    print()

    # Tabla compacta
    headers = ["ID", "Fecha", "wa_id", "API", "Op", "Resultado", "Entidad", "Monto", "Falla", "Venta/Compra"]
    widths = [5, 19, 13, 12, 7, 10, 28, 14, 22, 11]

    sep = "  "
    linea_header = sep.join(h.ljust(w) for h, w in zip(headers, widths))
    print(_color(linea_header, BOLD, use_color))
    print(_color("-" * len(linea_header), GRAY, use_color))

    for row in rows:
        res = row.get("resultado") or "-"
        color_res = GREEN if res == "exitoso" else RED if res == "fallido" else YELLOW
        id_vc = row.get("id_venta") or row.get("id_compra") or "-"
        entidad = (row.get("entidad_nombre") or "-")[:widths[6]]
        falla = (row.get("tipo_falla") or "-")[:widths[8]]
        cols = [
            str(row.get("id") or "-").ljust(widths[0]),
            _fmt_fecha(row.get("created_at")).ljust(widths[1]),
            (row.get("wa_id") or "-")[:widths[2]].ljust(widths[2]),
            (row.get("api_destino") or "-")[:widths[3]].ljust(widths[3]),
            (row.get("operacion") or "-")[:widths[4]].ljust(widths[4]),
            _color(res[:widths[5]].ljust(widths[5]), color_res, use_color),
            entidad.ljust(widths[6]),
            _fmt_monto(row.get("monto_total"), row.get("moneda")).ljust(widths[7]),
            _color(falla.ljust(widths[8]), YELLOW if falla != "-" else GRAY, use_color),
            str(id_vc).ljust(widths[9]),
        ]
        print(sep.join(cols))

    print()
    if tp > 1 and pag < tp:
        print(_color(f"  Para ver más: --pagina {pag + 1}", DIM, use_color))
    return 0


def obtener(args, use_color: bool) -> int:
    data = _post(args.url, {"codOpe": "OBTENER_BOT_API_LOG", "id": args.id})
    if not data.get("success"):
        print(_color(f"ERROR: {data.get('error') or data.get('message')}", RED, use_color))
        return 1

    log = data.get("log") or data.get("data") or {}
    if not log:
        print(_color(f"No se encontró log id={args.id}", YELLOW, use_color))
        return 1

    res = log.get("resultado") or "-"
    color_res = GREEN if res == "exitoso" else RED if res == "fallido" else YELLOW

    print()
    print(_color(f"=== LOG #{log.get('id')} ===", BOLD, use_color))
    print(f"  {_color('Fecha:', BOLD, use_color)}     {_fmt_fecha(log.get('created_at'))}")
    print(f"  {_color('wa_id:', BOLD, use_color)}     {log.get('wa_id')}  (id_from={log.get('id_from')}, id_empresa={log.get('id_empresa') or '-'})")
    print(f"  {_color('API:', BOLD, use_color)}       {log.get('api_destino')}  ({log.get('operacion')})")
    print(f"  {_color('Resultado:', BOLD, use_color)} {_color(res, color_res, use_color)}  HTTP {log.get('http_status') or '-'}  {log.get('latency_ms') or '-'}ms  intento={log.get('intento_numero') or 1}")
    if log.get("tipo_falla"):
        print(f"  {_color('Falla:', BOLD, use_color)}     {_color(log['tipo_falla'], YELLOW, use_color)}")
    if log.get("error_mensaje"):
        print(f"  {_color('Error:', BOLD, use_color)}     {_color(log['error_mensaje'], RED, use_color)}")

    print()
    print(_color("--- NEGOCIO ---", CYAN, use_color))
    print(f"  Entidad:  {log.get('entidad_nombre') or '-'}  ({log.get('entidad_numero') or '-'})  id={log.get('entidad_id') or '-'}")
    print(f"  Doc:      {log.get('tipo_documento') or '-'}  {log.get('serie') or ''}{('-' + str(log.get('numero'))) if log.get('numero') else ''}".rstrip())
    print(f"  Moneda:   {log.get('moneda') or '-'}  (id={log.get('id_moneda') or '-'})")
    print(f"  Base:     {_fmt_monto(log.get('monto_base'), log.get('moneda'))}")
    print(f"  IGV:      {_fmt_monto(log.get('monto_igv'), log.get('moneda'))}")
    print(f"  Total:    {_color(_fmt_monto(log.get('monto_total'), log.get('moneda')), BOLD, use_color)}")

    if log.get("id_venta") or log.get("id_compra") or log.get("serie_numero") or log.get("pdf_url"):
        print()
        print(_color("--- RESULTADO EMISIÓN ---", CYAN, use_color))
        if log.get("id_venta"):
            print(f"  id_venta:     {log['id_venta']}")
        if log.get("id_compra"):
            print(f"  id_compra:    {log['id_compra']}")
        if log.get("serie_numero"):
            print(f"  Comprobante:  {_color(log['serie_numero'], GREEN, use_color)}")
        if log.get("sunat_estado"):
            print(f"  SUNAT:        {log['sunat_estado']}")
        if log.get("pdf_url"):
            print(f"  PDF:          {log['pdf_url']}")

    detalle = log.get("detalle") or []
    if detalle:
        print()
        print(_color(f"--- PRODUCTOS ({len(detalle)}) ---", CYAN, use_color))
        print(f"  {'#':2}  {'Nombre':30} {'Cant':>6} {'PU base':>12} {'Subtotal':>10} {'IGV':>8} {'Total':>10}")
        for d in detalle:
            nombre = (d.get("nombre") or "-")[:30]
            print(f"  {d.get('indice', 0):2}  {nombre:30} {float(d.get('cantidad') or 0):>6.2f} {float(d.get('precio_unitario') or 0):>12.4f} {float(d.get('valor_subtotal_item') or 0):>10.2f} {float(d.get('valor_igv') or 0):>8.2f} {float(d.get('valor_total_item') or 0):>10.2f}")

    if args.raw:
        print()
        print(_color("--- PAYLOAD ENVIADO ---", CYAN, use_color))
        print(json.dumps(log.get("payload_enviado") or {}, indent=2, ensure_ascii=False))
        print()
        print(_color("--- RESPUESTA API ---", CYAN, use_color))
        print(json.dumps(log.get("respuesta_api") or {}, indent=2, ensure_ascii=False))
        if log.get("metadata"):
            print()
            print(_color("--- METADATA ---", CYAN, use_color))
            print(json.dumps(log["metadata"], indent=2, ensure_ascii=False))

    print()
    return 0


def follow(args, use_color: bool) -> int:
    """tail -f: muestra nuevos logs según aparezcan (polling)."""
    print(_color(f"Siguiendo logs nuevos (cada {args.interval}s). Ctrl+C para salir.", DIM, use_color))
    print()

    ultimo_id = 0
    # Semilla: saltar todo lo existente (mostrar solo nuevos)
    data = _post(args.url, {"codOpe": "LISTAR_BOT_API_LOG", "pagina": 1, "limite": 1})
    if data.get("success") and data.get("data"):
        ultimo_id = int(data["data"][0].get("id") or 0)

    try:
        while True:
            data = _post(args.url, {"codOpe": "LISTAR_BOT_API_LOG", "pagina": 1, "limite": 50})
            if data.get("success"):
                nuevos = [r for r in (data.get("data") or []) if int(r.get("id") or 0) > ultimo_id]
                for row in reversed(nuevos):  # del más viejo al más nuevo
                    res = row.get("resultado") or "-"
                    color_res = GREEN if res == "exitoso" else RED if res == "fallido" else YELLOW
                    linea = (
                        f"[{_fmt_fecha(row.get('created_at'))}] "
                        f"#{row.get('id'):<5} "
                        f"{(row.get('api_destino') or '-'):<12} "
                        f"{_color(res.ljust(8), color_res, use_color)} "
                        f"{(row.get('entidad_nombre') or '-')[:30]:<30} "
                        f"{_fmt_monto(row.get('monto_total'), row.get('moneda'))}"
                    )
                    if row.get("tipo_falla"):
                        linea += f"  {_color(row['tipo_falla'], YELLOW, use_color)}"
                    print(linea)
                    ultimo_id = max(ultimo_id, int(row.get("id") or 0))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()
        print(_color("  Saliendo...", DIM, use_color))
        return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="CLI para consultar bot_api_log (historial de payloads del bot).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--url", default=URL_DEFAULT, help="URL del endpoint (default: env URL_BOT_API_LOG o api.maravia.pe)")
    p.add_argument("--no-color", action="store_true", help="Desactiva colores ANSI")

    # Filtros de listado
    p.add_argument("--id", type=int, help="Si se indica, muestra el detalle completo de ese log")
    p.add_argument("--pagina", type=int, default=1)
    p.add_argument("--limite", type=int, default=20)
    p.add_argument("--wa-id", help="Filtrar por wa_id (teléfono)")
    p.add_argument("--id-from", type=int, help="Filtrar por id_from")
    p.add_argument("--id-empresa", type=int, help="Filtrar por id_empresa")
    p.add_argument("--api", choices=["php_venta", "php_compra", "sunat"], help="Filtrar por api_destino")
    p.add_argument("--operacion", choices=["venta", "compra"], help="Filtrar por operación")
    p.add_argument("--resultado", choices=["exitoso", "fallido"], help="Filtrar por resultado")
    p.add_argument("--tipo-falla", help="Filtrar por tipo_falla (timeout, stock_insuficiente, etc.)")
    p.add_argument("--desde", help="Fecha inicio: YYYY-MM-DD | hoy | ayer | hace-7d")
    p.add_argument("--hasta", help="Fecha fin: YYYY-MM-DD | hoy | ayer")
    p.add_argument("--buscar", help="Búsqueda de texto libre (entidad_nombre, etc.)")
    p.add_argument("--raw", action="store_true", help="En --id, muestra payload y respuesta completos")
    p.add_argument("--follow", "-f", action="store_true", help="Modo tail -f (polling)")
    p.add_argument("--interval", type=int, default=5, help="Intervalo de polling en segundos (default 5)")

    args = p.parse_args()
    use_color = not args.no_color and sys.stdout.isatty()

    if args.follow:
        return follow(args, use_color)
    if args.id:
        return obtener(args, use_color)
    return listar(args, use_color)


if __name__ == "__main__":
    sys.exit(main())
