"""
Test directo del módulo whatsapp_sender.
Verifica que enviar_texto funciona con id_empresa=1.

Uso:
  python test/test_whatsapp_sender.py
  python test/test_whatsapp_sender.py 51999999999 1
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from services.whatsapp_sender import enviar_texto

DEFAULT_PHONE = "51999999999"
DEFAULT_ID_EMPRESA = 1
DEFAULT_ID_PLATAFORMA = 6


def main():
    phone = DEFAULT_PHONE
    id_empresa = DEFAULT_ID_EMPRESA
    if len(sys.argv) >= 3:
        phone = sys.argv[1]
        id_empresa = int(sys.argv[2])
    elif len(sys.argv) == 2:
        phone = sys.argv[1]

    mensaje = "Test desde whatsapp_sender.py - si recibes esto, el envio directo funciona."

    print(f"Enviando texto a {phone} con id_empresa={id_empresa}, id_plataforma={DEFAULT_ID_PLATAFORMA}")
    ok, err = enviar_texto(id_empresa, phone, mensaje, DEFAULT_ID_PLATAFORMA)
    print(f"  OK: {ok}")
    if err:
        print(f"  Error: {err}")

    # Tambien probar sin id_plataforma
    print(f"\nEnviando sin id_plataforma...")
    ok2, err2 = enviar_texto(id_empresa, phone, mensaje)
    print(f"  OK: {ok2}")
    if err2:
        print(f"  Error: {err2}")


if __name__ == "__main__":
    sys.exit(main() or 0)
