"""
Reporte en terminal del JSON devuelto por el servicio de historial cache (tabla historial_cache_n8n).

Usa el mismo servicio que test_actualizar_historial.py:
  https://api.maravia.pe/servicio/n8n/ws_historial_cache.php
  GET con codOpe=CONSULTAR_CACHE, ws_whatsapp, id_empresa.

Uso:
  python test/test_leer_historial.py
  python test/test_leer_historial.py --wa 51994748961 --empresa 2
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv

load_dotenv()

URL_CACHE = "https://api.maravia.pe/servicio/n8n/ws_historial_cache.php"

# Mismos valores por defecto que test_actualizar_historial.py
WA_ID_DEFECTO = "51994748961"
ID_EMPRESA_DEFECTO = 2


def main():
    import argparse
    p = argparse.ArgumentParser(description="Reporte JSON del historial cache vía ws_historial_cache.php")
    p.add_argument("--wa", default=os.getenv("WA_ID", WA_ID_DEFECTO), help="ws_whatsapp")
    p.add_argument("--empresa", type=int, default=int(os.getenv("ID_EMPRESA", str(ID_EMPRESA_DEFECTO))), help="id_empresa")
    args = p.parse_args()

    params = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": args.wa, "id_empresa": args.empresa}
    res = requests.get(URL_CACHE, params=params)

    try:
        data = res.json()
    except Exception as e:
        print(f"Error al parsear respuesta: {e}", file=sys.stderr)
        print(res.text, file=sys.stderr)
        sys.exit(1)

    # Reporte en terminal: todo el JSON de la respuesta
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
