"""
Cliente HTTP para la API de ventas SUNAT.

Encapsula la llamada POST y el parseo de la respuesta,
de modo que FinalizarService no dependa de detalles HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from config import settings


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
        self._token = token or settings.TOKEN_SUNAT

    def crear_venta(self, payload: Dict[str, Any]) -> SunatResult:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        res = requests.post(self._url, json=payload, headers=headers)
        res_json = res.json()

        sunat_obj = res_json.get("sunat") or {}
        sunat_data = sunat_obj.get("sunat_data") or {}
        payload_data = (sunat_obj.get("data") or {}).get("payload") or {}
        payload_pdf = payload_data.get("pdf") if isinstance(payload_data.get("pdf"), dict) else {}

        url_pdf = (
            sunat_data.get("sunat_pdf")
            or sunat_data.get("enlace_documento")
            or payload_pdf.get("ticket")
            or payload_pdf.get("a4")
            or res_json.get("data", {}).get("url_pdf")
        )

        if url_pdf and res_json.get("success"):
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
