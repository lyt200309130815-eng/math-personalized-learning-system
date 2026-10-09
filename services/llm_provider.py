"""Small text-generation adapters; no learning decisions or database access."""

import os
import settings  # Bootstrap the shared project .env before reading any provider settings.

from google import genai
from openai import OpenAI


DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
PROVIDER_CONFIG = {
    "deepseek": ("DeepSeek", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
    "gemini": ("Gemini", "GEMINI_API_KEY", "GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
    "openai": ("OpenAI", "OPENAI_API_KEY", "OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
}


class LLMUnavailable(RuntimeError):
    """Safe configuration or provider failure suitable for display."""


def get_provider_config() -> dict:
    """Return non-secret active configuration; never expose a key value."""
    provider = settings.get_setting("LLM_PROVIDER", "").strip().lower() or "deepseek"
    if provider not in PROVIDER_CONFIG:
        raise LLMUnavailable("AI 服务配置无效，请选择 deepseek、openai 或 gemini。")
    name, key_variable, model_variable, default_model = PROVIDER_CONFIG[provider]
    return {
        "provider": provider, "name": name,
        "model": settings.get_setting(model_variable, "").strip() or default_model,
        "configured": bool(settings.get_setting(key_variable, "").strip()),
    }


def _generate_gemini(prompt: str, model: str, system_prompt: str | None = None) -> str:
    # Explicit environment lookup avoids GOOGLE_API_KEY taking precedence.
    with genai.Client(api_key=settings.get_setting("GEMINI_API_KEY"),
                      http_options={"timeout": 20000, "retry_options": {"attempts": 1}}) as client:
        contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        return client.models.generate_content(model=model, contents=contents).text


def _generate_openai(prompt: str, model: str, system_prompt: str | None = None) -> str:
    options = {"instructions": system_prompt} if system_prompt else {}
    key = settings.get_setting("OPENAI_API_KEY")
    credentials = {} if key == os.environ.get("OPENAI_API_KEY") else {"api_key": key}
    with OpenAI(timeout=20.0, max_retries=0, **credentials) as client:
        return client.responses.create(
            model=model, input=prompt, max_output_tokens=1000, store=False, **options,
        ).output_text


def _generate_deepseek(prompt: str, model: str, system_prompt: str | None = None) -> str:
    with OpenAI(api_key=settings.get_setting("DEEPSEEK_API_KEY"), base_url=DEEPSEEK_BASE_URL,
                timeout=20.0, max_retries=0) as client:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt or "请遵守用户提供的指令。"},
                      {"role": "user", "content": prompt}],
            stream=False,
        )
        return response.choices[0].message.content


# Future adapters implement the same (prompt, model, system_prompt) contract.
PROVIDER_GENERATORS = {
    "deepseek": _generate_deepseek, "gemini": _generate_gemini, "openai": _generate_openai,
}


def generate_text(prompt: str, system_prompt: str | None = None) -> str:
    """Dispatch one text request; sanitize failures without logging credentials."""
    config = get_provider_config()
    if not config["configured"]:
        raise LLMUnavailable(f"尚未配置 {config['name']} AI 服务。")
    try:
        text = PROVIDER_GENERATORS[config["provider"]](prompt, config["model"], system_prompt)
        if not isinstance(text, str) or not text.strip():
            raise LLMUnavailable("AI学习反馈暂时不可用，请稍后重试。")
        return text.strip()
    except Exception:
        raise LLMUnavailable("AI学习反馈暂时不可用，请稍后重试。") from None
