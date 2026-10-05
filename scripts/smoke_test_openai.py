"""Manually run a minimal Responses API request without exposing credentials."""

import os
from pathlib import Path
import sys

from openai import OpenAI, OpenAIError

# Support running this file directly from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.llm_provider import DEFAULT_OPENAI_MODEL


def main() -> int:
    """Read process environment; only an explicit script run sends a request."""
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("未检测到 OPENAI_API_KEY，请先配置环境变量。")
        return 0

    model = os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
    try:
        client = OpenAI()
        with client:
            response = client.with_options(timeout=20.0, max_retries=0).responses.create(
                model=model,
                input="请只回复：API连接成功",
                max_output_tokens=64,
                store=False,
            )
            print(response.output_text)
    except OpenAIError as error:
        print(f"{type(error).__name__}：API 请求失败，请检查凭据、模型、额度或网络配置。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
