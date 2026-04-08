"""
LLM backend for LightRAG using LM Studio's OpenAI-compatible local server.

LM Studio runs at http://localhost:1234/v1 and handles GPU acceleration
for the Qwen3-VL-8B-Instruct model natively (including Blackwell/sm_120).

To use:
  1. Open LM Studio
  2. Load model: Qwen3-VL-8B-Instruct-Q4_K_M.gguf
  3. Start the local server (Developer tab → Start Server)
  4. Server will be available at http://localhost:1234
"""

import logging
import os
from openai import AsyncOpenAI

log = logging.getLogger(__name__)

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "qwen3-vl-8b-instruct-q4_k_m")

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=LM_STUDIO_BASE_URL,
            api_key="lm-studio",  # LM Studio ignores the key, any value works
        )
    return _client


async def llm_model_func(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list | None = None,
    **kwargs,
) -> str:
    """LightRAG-compatible async LLM function backed by LM Studio."""
    client = get_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    # Qwen3: /no_think must be at the START of the USER message (not system prompt)
    # to disable chain-of-thought. Placing it in the system prompt has no effect.
    messages.append({"role": "user", "content": prompt})

    total_chars = sum(len(m["content"]) for m in messages)
    log.info(f"LLM Send: {len(messages)} msgs, ~{total_chars} chars. (Concurrency {kwargs.get('concurrency', 'unk')})")

    response = await client.chat.completions.create(
        model=LM_STUDIO_MODEL,
        messages=messages,
        max_tokens=kwargs.get("max_tokens", 400),
        temperature=kwargs.get("temperature", 0.0),
    )
    content = response.choices[0].message.content or ""
    # Strip any <think>...</think> block in case thinking mode partially activates
    import re
    content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)
    return content
