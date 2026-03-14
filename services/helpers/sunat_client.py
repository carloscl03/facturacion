"""
Cliente HTTP para la API de ventas SUNAT.

Encapsula la llamada POST y el parseo de la respuesta,
de modo que FinalizarService no dependa de detalles HTTP.
Obtiene token vía login (codOpe=LOGIN) cuando hay credenciales en config.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from config import settings


def login_maravia(username: str, password: str, url_login: str | None = None) -> str | None:
    """
    Obtiene token JWT para la API Maravia.
    POST con codOpe=LOGIN, username, password.
    Respuesta: { "success": true, "usuario": {...}, "token": "eyJ..." } — token en raíz o en data.
    """
    url = url_login or settings.URL_LOGIN
    payload = {"codOpe": "LOGIN", "username": username, "password": password}
    try:
        r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        token = data.get("token") or (data.get("data") or {}).get("token")
        if token and isinstance(token, str):
            return token.strip()
        return None
    except Exception:
        return None


def obtener_token_sunat() -> str:
    """
    Token para Authorization en CREAR_VENTA. Siempre se obtiene por login;
    el token no es fijo (expira), no se usa TOKEN_SUNAT de env.
    Requiere MARAVIA_USER y MARAVIA_PASSWORD en config.
    """
    if not settings.MARAVIA_USER or not settings.MARAVIA_PASSWORD:
        return ""
    token = login_maravia(settings.MARAVIA_USER, settings.MARAVIA_PASSWORD)
    return token or ""


@dataclass
class SunatResult:
    success: bool
    url_pdf: Optional[str] = None
    serie: Optional[str] = None
    numero: Optional[str] = None
    error_mensaje: Optional[str] = None

    @property
    def serie_numero(self) -> str:
        return f"{self.serie or 'F001'}-{self.numero or '000'}"


class SunatClient:
    """Abstrae la comunicación con el endpoint de ventas SUNAT."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
    ) -> None:
        self._url = url or settings.URL_VENTA_SUNAT
        self._token = (token or "").strip() or obtener_token_sunat()

    def crear_venta(self, payload: Dict[str, Any]) -> SunatResult:
        if not (self._token or "").strip():
            return SunatResult(
                success=False,
                error_mensaje=(
                    "No se proporcionó token de autenticación. "
                    "Configure MARAVIA_USER y MARAVIA_PASSWORD en el entorno; el token se obtiene por login en "
                    "https://api.maravia.pe/servicio/ws_login.php (codOpe=LOGIN, username, password)."
                ),
            )
        headers = {
            "Authorization": f"Bearer {self._token.strip()}",
            "Content-Type": "application/json",
        }
        try:
            res = requests.post(self._url, json=payload, headers=headers, timeout=30)
        except requests.RequestException as e:
            return SunatResult(success=False, error_mensaje=str(e))

        try:
            res_json = res.json()
        except Exception:
            return SunatResult(
                success=False,
                error_mensaje=f"Respuesta no JSON (status {res.status_code}).",
            )

        sunat_obj = res_json.get("sunat") or {}
        sunat_data = sunat_obj.get("sunat_data") or {}
        payload_data = (sunat_obj.get("data") or {}).get("payload") or {}
        payload_pdf = payload_data.get("pdf") if isinstance(payload_data.get("pdf"), dict) else {}

        # Misma extracción de PDF que en test_pdf_sunat: sunat.sunat_data.sunat_pdf o enlace_documento
        url_pdf = (
            sunat_data.get("sunat_pdf")
            or sunat_data.get("enlace_documento")
            or payload_pdf.get("ticket")
            or payload_pdf.get("a4")
            or (res_json.get("data") or {}).get("url_pdf")
        )

        if res_json.get("success") and url_pdf:
            return SunatResult(
                success=True,
                url_pdf=url_pdf,
                serie=sunat_data.get("serie"),
                numero=sunat_data.get("numero"),
            )

        error = (
            res_json.get("message")
            or res_json.get("error")
            or "No se pudo generar el PDF."
        )
        return SunatResult(success=False, error_mensaje=error)
