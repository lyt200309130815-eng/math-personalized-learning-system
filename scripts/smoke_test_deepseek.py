"""Manual-only DeepSeek connectivity check; never print credentials."""

import os
from pathlib import Path
import sys

from openai import OpenAI, OpenAIError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.llm_provider import DEFAULT_DEEPSEEK_MODEL, DEEPSEEK_BASE_URL


def main() -> int:
    """Send one minimal request only when this script is explicitly executed."""
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("未检测到 DEEPSEEK_API_KEY，请先配置环境变量。")
        return 0
    model = os.environ.get("DEEPSEEK_MODEL", "").strip() or DEFAULT_DEEPSEEK_MODEL
    try:
        with OpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url=DEEPSEEK_BASE_URL,
                    timeout=20.0, max_retries=0) as client:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": "请简短回复。"},
                          {"role": "user", "content": "请只回复：API连接成功"}],
                stream=False,
            )
            print(response.choices[0].message.content or "未收到文本响应。")
    except OpenAIError as error:
        print(f"{type(error).__name__}：DeepSeek 请求失败，请检查密钥、余额、模型或网络。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
