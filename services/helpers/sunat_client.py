"""
Cliente HTTP para la API de ventas SUNAT.

Encapsula la llamada POST y el parseo de la respuesta,
de modo que FinalizarService no dependa de detalles HTTP.
Soporta:
- ws_venta.php (N8N): REGISTRAR_VENTA / REGISTRAR_VENTA_N8N (sin token; devuelve pdf_url en raíz)
- ws_ventas.php: CREAR_VENTA (puede requerir Bearer token vía LOGIN)
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


def obtener_token_sunat() -> tuple[str, str | None]:
    """
    Token para Authorization en CREAR_VENTA. Se obtiene por LOGIN (codOpe=LOGIN).
    Retorna (token, error). Si error no es None, el token está vacío y error describe el fallo.
    """
    if not (settings.MARAVIA_USER or "").strip() or not (settings.MARAVIA_PASSWORD or "").strip():
        return "", (
            "Faltan MARAVIA_USER y/o MARAVIA_PASSWORD en el entorno (.env). "
            "El token se obtiene automáticamente llamando a la API de login (ws_login.php) con esas credenciales; "
            "añada ambas variables a su archivo .env (puede copiar .env.example y rellenar sus credenciales Maravia)."
        )
    token = login_maravia(settings.MARAVIA_USER, settings.MARAVIA_PASSWORD)
    if not token:
        return "", "LOGIN en ws_login.php falló o no devolvió token. Revisar credenciales y URL (MARAVIA_URL_LOGIN)."
    return token, None


@dataclass
class SunatResult:
    success: bool
    url_pdf: Optional[str] = None
    serie: Optional[str] = None
    numero: Optional[str] = None
    error_mensaje: Optional[str] = None
    error_debug: Optional[Dict[str, Any]] = None  # Respuesta cruda de la API en caso de error (para diagnóstico)

    @property
    def serie_numero(self) -> str:
        return f"{self.serie or 'F001'}-{self.numero or '000'}"


class SunatClient:
    """Abstrae la comunicación con endpoints de ventas (N8N y/o CREAR_VENTA)."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
    ) -> None:
        self._url = url or settings.URL_VENTA_SUNAT
        self._token = (token or "").strip()

    def _asegurar_token(self) -> tuple[str | None, str | None]:
        """Obtiene token por LOGIN si no hay uno. Retorna (token, error); si token es None, error describe el fallo."""
        if (self._token or "").strip():
            return self._token.strip(), None
        token, error = obtener_token_sunat()
        if token:
            self._token = token
            return token, None
        return None, error

    def crear_venta(self, payload: Dict[str, Any]) -> SunatResult:
        cod_ope = str(payload.get("codOpe") or "").strip().upper()
        headers = {"Content-Type": "application/json"}
        # N8N ws_venta.php: no requiere token (según comportamiento observado en test).
        if cod_ope not in ("REGISTRAR_VENTA", "REGISTRAR_VENTA_N8N"):
            token, error_msg = self._asegurar_token()
            if not token:
                mensaje = (
                    error_msg
                    if error_msg
                    else "No se obtuvo token. Configure MARAVIA_USER y MARAVIA_PASSWORD; el token se obtiene por LOGIN en ws_login.php (codOpe=LOGIN)."
                )
                return SunatResult(success=False, error_mensaje=mensaje)
            headers["Authorization"] = f"Bearer {token}"
        # N8N (ws_venta.php) puede demorar porque incluye generación SUNAT y SP.
        # Un timeout bajo termina en gateways/proxies con 502 y/o cuerpo no-JSON.
        timeout_s = 90 if cod_ope in ("REGISTRAR_VENTA", "REGISTRAR_VENTA_N8N") else 60
        try:
            res = requests.post(self._url, json=payload, headers=headers, timeout=timeout_s)
        except requests.RequestException as e:
            return SunatResult(success=False, error_mensaje=str(e))

        try:
            res_json = res.json()
        except Exception:
            raw_preview = None
            try:
                raw_preview = (res.text or "")[:300] if res.text else None
            except Exception:
                raw_preview = None
            return SunatResult(
                success=False,
                error_mensaje=f"Respuesta no JSON (status {res.status_code}).",
                error_debug={"status_code": res.status_code, "raw": raw_preview},
            )

        # Caso N8N (ws_venta.php): pdf_url y sunat_estado están en la raíz
        if cod_ope in ("REGISTRAR_VENTA", "REGISTRAR_VENTA_N8N"):
            if res_json.get("success"):
                url_pdf = res_json.get("pdf_url") or res_json.get("url_pdf")
                return SunatResult(
                    success=True,
                    url_pdf=url_pdf,
                    serie=res_json.get("serie"),
                    numero=str(res_json.get("numero")) if res_json.get("numero") is not None else None,
                )
            err = res_json.get("details") or res_json.get("message") or res_json.get("error") or "No se pudo registrar la venta."
            return SunatResult(
                success=False,
                error_mensaje=err,
                error_debug={"status_code": res.status_code, **{k: res_json.get(k) for k in ("success", "error", "message", "details")}},
            )

        # Caso CREAR_VENTA (ws_ventas.php): estructura sunat.sunat_data + payload.pdf
        sunat_obj = res_json.get("sunat") or {}
        sunat_data = sunat_obj.get("sunat_data") or {}
        payload_data = (sunat_obj.get("data") or {}).get("payload") or {}
        payload_pdf = payload_data.get("pdf") if isinstance(payload_data.get("pdf"), dict) else {}

        url_pdf = (
            sunat_data.get("sunat_pdf")
            or sunat_data.get("enlace_documento")
            or payload_pdf.get("ticket")
            or payload_pdf.get("a4")
            or (res_json.get("data") or {}).get("url_pdf")
        )

        if res_json.get("success") and url_pdf:
            return SunatResult(success=True, url_pdf=url_pdf, serie=sunat_data.get("serie"), numero=sunat_data.get("numero"))

        # Preferir mensaje detallado de SUNAT (sunat_data.sunat_error_mensaje) para saber el motivo del rechazo
        error = (
            (sunat_data.get("sunat_error_mensaje") or "").strip()
            or (res_json.get("details") or "").strip()
            or res_json.get("message")
            or res_json.get("error")
            or "No se pudo generar el PDF."
        )
        # Si SUNAT dice "El DNI X no es válido" y X parece número de comprobante (ej. B005-00000008), aclarar
        if error and "DNI" in error and "-" in error:
            error = (
                error.rstrip(".")
                + ". (El número de comprobante no debe enviarse como documento del cliente; el documento del cliente es el DNI/RUC, 8 u 11 dígitos.)"
            )
        # Debug: respuesta de la API para ver status, códigos y mensaje detallado de SUNAT
        error_debug = {
            "status_code": res.status_code,
            "success": res_json.get("success"),
            "message": res_json.get("message"),
            "error": res_json.get("error"),
            "details": res_json.get("details"),
            "sunat": res_json.get("sunat"),
        }
        return SunatResult(success=False, error_mensaje=error, error_debug=error_debug)
