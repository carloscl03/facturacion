import json
from abc import ABC, abstractmethod

from openai import OpenAI


class AIService(ABC):
    """Abstracción del proveedor de IA generativa."""

    @abstractmethod
    def completar_json(self, prompt: str) -> dict:
        """Envía un prompt y espera una respuesta en formato JSON."""
        ...

    @abstractmethod
    def completar_texto(self, prompt: str) -> str:
        """Envía un prompt y retorna la respuesta como texto libre."""
        ...


class OpenAIService(AIService):
    """Implementación con el modelo GPT de OpenAI."""

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini") -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def completar_json(self, prompt: str) -> dict:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    def completar_texto(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": prompt}],
        )
        return (response.choices[0].message.content or "").strip()
