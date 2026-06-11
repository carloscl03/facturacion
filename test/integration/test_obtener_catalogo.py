"""
Test GET ws_obtenerCatalogo.php — busca productos en catálogo por nombre.

Uso:
  python test/test_obtener_catalogo.py
  python test/test_obtener_catalogo.py 2 camara
"""
import json
import sys

import requests

URL_CATALOGO = "https://api.maravia.pe/servicio/n8n_asistente/ws_obtenerCatalogo.php"

DEFAULT_ID_EMPRESA = 2
DEFAULT_NOMBRE = "camara"


def obtener_catalogo(id_empresa: int, nombre: str) -> dict:
    """GET ws_obtenerCatalogo.php con id_empresa y nombre."""
    params = {"id_empresa": id_empresa, "nombre": nombre}
    try:
        resp = requests.get(URL_CATALOGO, params=params, timeout=15)
        print(f"  Status: {resp.status_code}")
        print(f"  URL:    {resp.url}")
        if resp.status_code != 200:
            print(f"  Body:   {resp.text[:500]}")
            return {}
        data = resp.json()
        return data
    except requests.RequestException as e:
        print(f"  Error: {e}")
        return {}


def main():
    id_empresa = DEFAULT_ID_EMPRESA
    nombre = DEFAULT_NOMBRE
    if len(sys.argv) >= 3:
        id_empresa = int(sys.argv[1])
        nombre = sys.argv[2]
    elif len(sys.argv) == 2:
        nombre = sys.argv[1]

    print(f"GET ws_obtenerCatalogo.php | id_empresa={id_empresa} | nombre={nombre}")
    print("-" * 60)

    data = obtener_catalogo(id_empresa, nombre)
    print("\nRespuesta:")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main() or 0)
