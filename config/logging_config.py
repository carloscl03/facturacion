"""
Configuración centralizada de logging para MaravIA Bot.

Formato JSON estructurado para facilitar búsqueda y análisis.
Niveles:
  DEBUG  — llamadas IA (tokens), hits de cache, detalles internos
  INFO   — transiciones de estado, llamadas externas, envíos WhatsApp
  WARNING — validaciones fallidas, campos faltantes, reintentos
  ERROR  — excepciones, fallos SUNAT, fallos WhatsApp críticos
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Formatter que emite cada log como una línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Campos extra agregados con logger.info(..., extra={...})
        skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for k, v in record.__dict__.items():
            if k not in skip:
                base[k] = v
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    """
    Inicializa el sistema de logging. Llamar una sola vez desde main.py.
    Emite JSON a stdout para que Docker/systemd/CloudWatch lo capture.
    """
    root = logging.getLogger()
    if root.handlers:
        return  # Ya configurado (evita duplicados en reload de uvicorn)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())

    numeric = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric)
    root.addHandler(handler)

    # Silenciar loggers muy verbosos de librerías externas
    for noisy in ("httpx", "httpcore", "openai._base_client", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Obtiene un logger con el nombre dado (usar nombre del módulo/servicio)."""
    return logging.getLogger(name)
