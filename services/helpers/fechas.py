from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

# Zona horaria de Perú (UTC-5)
_TZ_PERU = timezone(timedelta(hours=-5))


def hoy_peru() -> str:
    """Retorna la fecha actual en Perú en formato YYYY-MM-DD."""
    return datetime.now(_TZ_PERU).date().isoformat()


def hoy_peru_ddmmyyyy() -> str:
    """Retorna la fecha actual en Perú en formato DD-MM-YYYY."""
    d = datetime.now(_TZ_PERU).date()
    return f"{d.day:02d}-{d.month:02d}-{d.year}"


def fecha_ddmmyyyy_a_api(fecha_ddmmyyyy: str | None) -> Optional[str]:
    """
    Convierte una fecha en formato DD-MM-YYYY al formato YYYY-MM-DD usado por la API.
    Si no puede convertir, devuelve la entrada tal cual. Acepta str o int (se convierte a str).
    """
    if fecha_ddmmyyyy is None:
        return None
    if not isinstance(fecha_ddmmyyyy, str):
        fecha_ddmmyyyy = str(fecha_ddmmyyyy)
    f = fecha_ddmmyyyy.strip()
    if len(f) == 10 and f[2] == "-" and f[5] == "-":
        dd, mm, yyyy = f[:2], f[3:5], f[6:]
        return f"{yyyy}-{mm}-{dd}"
    return f

