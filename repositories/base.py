from abc import ABC, abstractmethod


class CacheRepository(ABC):
    """Abstracción del repositorio de caché (historial de operaciones)."""

    @abstractmethod
    def consultar(self, wa_id: str, id_from: int) -> dict | None:
        """Retorna el primer registro del caché o None si no existe."""
        ...

    @abstractmethod
    def consultar_lista(self, wa_id: str, id_from: int) -> list[dict]:
        """Retorna la lista completa de registros (útil para detectar si el registro es nuevo)."""
        ...

    @abstractmethod
    def insertar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        """Inserta un nuevo registro de caché y retorna la respuesta del servidor."""
        ...

    @abstractmethod
    def actualizar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        """Actualiza el registro de caché existente y retorna la respuesta del servidor."""
        ...

    @abstractmethod
    def eliminar(self, wa_id: str, id_from: int) -> dict:
        """Elimina el registro de caché y retorna la respuesta del servidor."""
        ...

    def upsert(self, wa_id: str, id_from: int, datos: dict, es_nuevo: bool) -> dict:
        """Inserta o actualiza según si el registro ya existe."""
        if es_nuevo:
            return self.insertar(wa_id, id_from, datos)
        return self.actualizar(wa_id, id_from, datos)
