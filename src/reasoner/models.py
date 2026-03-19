# src/reasoner/models.py
"""Multi-model AI chain with automatic fallback: Gemini -> Kimi -> GLM -> OpenAI."""
import os
import json
from enum import Enum
from dataclasses import dataclass

import google.genai as genai
from openai import OpenAI


def _get_api_keys():
    """Lazily fetch API keys from environment at call time."""
    return {
        "gemini": os.getenv("GEMINI_API_KEY", ""),
        "kimi": os.getenv("KIMI_API_KEY", ""),
        "glm": os.getenv("GLM_API_KEY", ""),
        "openai": os.getenv("OPENAI_API_KEY", ""),
    }


class ModelProvider(Enum):
    GEMINI = "gemini"
    KIMI = "kimi"
    GLM = "glm"
    OPENAI = "openai"


@dataclass
class ModelResponse:
    text: str
    provider: ModelProvider
    model_name: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelChain:
    """
    Multi-model chain with fallback.
    Tries providers in order: Gemini -> Kimi -> GLM -> OpenAI.
    Logs which provider succeeded.
    """

    DEFAULT_MODELS = {
        ModelProvider.GEMINI: "gemini-2.0-flash",
        ModelProvider.KIMI: "moonshot-v1-8k",
        ModelProvider.GLM: "glm-4-flash",
        ModelProvider.OPENAI: "gpt-4o-mini",
    }

    def __init__(self, model_overrides: dict[ModelProvider, str] | None = None):
        self.providers = self._build_provider_list()
        self.models = model_overrides or self.DEFAULT_MODELS
        keys = _get_api_keys()
        self._openai_client = OpenAI(api_key=keys["openai"]) if keys["openai"] else None

    def _build_provider_list(self) -> list[ModelProvider]:
        """Return providers in fallback order, skipping those without API keys."""
        keys = _get_api_keys()
        chain = []
        for provider in [ModelProvider.GEMINI, ModelProvider.KIMI, ModelProvider.GLM, ModelProvider.OPENAI]:
            if keys[provider.value]:
                chain.append(provider)
        if not chain:
            raise ValueError("No AI API keys configured")
        return chain

    def complete(self, prompt: str, system_prompt: str = "", max_tokens: int = 1000) -> ModelResponse:
        """Send a prompt through the fallback chain. Returns first successful response."""
        for provider in self.providers:
            try:
                if provider == ModelProvider.GEMINI:
                    return self._call_gemini(prompt, system_prompt, max_tokens)
                elif provider == ModelProvider.KIMI:
                    return self._call_kimi(prompt, system_prompt, max_tokens)
                elif provider == ModelProvider.GLM:
                    return self._call_glm(prompt, system_prompt, max_tokens)
                elif provider == ModelProvider.OPENAI:
                    return self._call_openai(prompt, system_prompt, max_tokens)
            except Exception as e:
                print(f"  [{provider.value}] Failed: {e}. Trying next provider...")
                continue
        raise RuntimeError("All AI providers failed")

    def _call_gemini(self, prompt: str, system_prompt: str, max_tokens: int) -> ModelResponse:
        genai.configure(api_key=_get_api_keys()["gemini"])
        model_name = self.models[ModelProvider.GEMINI]
        client = genai.Client()
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        response = client.models.generate_content(model=model_name, contents=full_prompt)
        return ModelResponse(text=response.text, provider=ModelProvider.GEMINI, model_name=model_name)

    def _call_kimi(self, prompt: str, system_prompt: str, max_tokens: int) -> ModelResponse:
        import requests
        headers = {"Authorization": f"Bearer {API_KEYS['kimi']}", "Content-Type": "application/json"}
        payload = {
            "model": self.models[ModelProvider.KIMI],
            "messages": (
                [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
                if system_prompt else [{"role": "user", "content": prompt}]
            ),
            "max_tokens": max_tokens,
        }
        resp = requests.post("https://api.moonshot.cn/v1/chat/completions", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return ModelResponse(
            text=data["choices"][0]["message"]["content"],
            provider=ModelProvider.KIMI,
            model_name=self.models[ModelProvider.KIMI],
        )

    def _call_glm(self, prompt: str, system_prompt: str, max_tokens: int) -> ModelResponse:
        import requests
        headers = {"Authorization": f"Bearer {API_KEYS['glm']}", "Content-Type": "application/json"}
        payload = {
            "model": self.models[ModelProvider.GLM],
            "messages": (
                [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
                if system_prompt else [{"role": "user", "content": prompt}]
            ),
            "max_tokens": max_tokens,
        }
        resp = requests.post("https://open.bigmodel.cn/api/paas/v4/chat/completions", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return ModelResponse(
            text=data["choices"][0]["message"]["content"],
            provider=ModelProvider.GLM,
            model_name=self.models[ModelProvider.GLM],
        )

    def _call_openai(self, prompt: str, system_prompt: str, max_tokens: int) -> ModelResponse:
        if not self._openai_client:
            raise ValueError("OpenAI API key not configured")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = self._openai_client.chat.completions.create(
            model=self.models[ModelProvider.OPENAI],
            messages=messages,
            max_tokens=max_tokens,
        )
        return ModelResponse(
            text=response.choices[0].message.content,
            provider=ModelProvider.OPENAI,
            model_name=self.models[ModelProvider.OPENAI],
        )
