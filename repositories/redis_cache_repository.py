from __future__ import annotations

import json

from redis import Redis

from repositories.base import CacheRepository


class RedisCacheRepository(CacheRepository):
    """Implementacion de CacheRepository usando Redis Hash."""

    def __init__(self, redis: Redis, ttl: int = 86400) -> None:
        self._r = redis
        self._ttl = ttl

    def _key(self, wa_id: str, id_from: int) -> str:
        return f"cache:{wa_id}:{id_from}"

    def consultar(self, wa_id: str, id_from: int) -> dict | None:
        data = self._r.hgetall(self._key(wa_id, id_from))
        if not data:
            return None
        return self._deserializar(data)

    def consultar_lista(self, wa_id: str, id_from: int) -> list[dict]:
        reg = self.consultar(wa_id, id_from)
        return [reg] if reg else []

    def insertar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        key = self._key(wa_id, id_from)
        self._r.hset(key, mapping=self._serializar(datos))
        self._r.expire(key, self._ttl)
        return {"success": True}

    def actualizar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        key = self._key(wa_id, id_from)
        self._r.hset(key, mapping=self._serializar(datos))
        self._r.expire(key, self._ttl)
        return {"success": True}

    def eliminar(self, wa_id: str, id_from: int) -> dict:
        try:
            self._r.delete(self._key(wa_id, id_from))
            return {"success": True}
        except Exception:
            return {"success": False}

    @staticmethod
    def _serializar(datos: dict) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in datos.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                out[k] = json.dumps(v, ensure_ascii=False)
            else:
                out[k] = str(v)
        return out

    @staticmethod
    def _deserializar(data: dict[bytes | str, bytes | str]) -> dict:
        out: dict = {}
        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v

            try:
                parsed = json.loads(val)
                if isinstance(parsed, (dict, list)):
                    out[key] = parsed
                    continue
            except (json.JSONDecodeError, TypeError):
                pass

            try:
                if "." in val:
                    out[key] = float(val)
                    continue
                out[key] = int(val)
                continue
            except (ValueError, TypeError):
                pass

            out[key] = val
        return out
