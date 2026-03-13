from __future__ import annotations

from typing import Optional


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

