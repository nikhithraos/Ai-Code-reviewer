from abc import ABC, abstractmethod
import requests


class LLMProvider(ABC):
    """Agents depend on this interface, never on a concrete model."""

    @abstractmethod
    def generate(self, system: str, prompt: str, *,
                 temperature: float = 0.1, json_mode: bool = False) -> str:
        ...


class OllamaProvider(LLMProvider):
    def __init__(self, model="qwen2.5-coder:7b",
                 host="http://localhost:11434", timeout=180):
        self.model, self.host, self.timeout = model, host, timeout

    def generate(self, system, prompt, *, temperature=0.1, json_mode=False):
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": temperature},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
        }
        if json_mode:
            payload["format"] = "json"
        r = requests.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["message"]["content"]


class MockProvider(LLMProvider):
    """Returns canned responses in order. Lets us test without a real LLM."""

    def __init__(self, responses: list[str]):
        self.responses, self.calls = responses, 0

    def generate(self, system, prompt, *, temperature=0.1, json_mode=False):
        reply = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return reply


def get_provider(name: str = "ollama", **kwargs) -> LLMProvider:
    if name == "ollama":
        return OllamaProvider(**kwargs)
    if name == "mock":
        return MockProvider(**kwargs)
    raise ValueError(f"Unknown provider: {name}")