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
import re

from openai import AsyncOpenAI

from src.rag.context import ANSWER_GENERATION

log = logging.getLogger(__name__)

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "qwen3-vl-8b-instruct-q4_k_m")
# Entity-extraction output is short and structured; a tight cap keeps indexing fast.
# User-facing answers get a larger budget (see src.rag.context.ANSWER_GENERATION).
EXTRACTION_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "400"))
ANSWER_MAX_TOKENS = int(os.getenv("LLM_ANSWER_MAX_TOKENS", "1500"))
# Sampling knobs for experiments (defaults reproduce the original greedy decoding).
DEFAULT_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))
FREQUENCY_PENALTY = float(os.getenv("LLM_FREQUENCY_PENALTY", "0.0"))
_THINK_RE = re.compile(r"<think>.*?</think>\s*", flags=re.DOTALL)

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
    # Qwen3 hybrid-thinking models: /no_think must lead the USER message to disable
    # chain-of-thought (it has no effect in the system prompt). Other models (e.g.
    # Qwen2.5) have no thinking mode and must not receive the tag.
    if "qwen3" in LM_STUDIO_MODEL.lower() and not prompt.lstrip().startswith("/no_think"):
        prompt = "/no_think\n" + prompt
    messages.append({"role": "user", "content": prompt})

    default_cap = ANSWER_MAX_TOKENS if ANSWER_GENERATION.get() else EXTRACTION_MAX_TOKENS
    log.debug("LLM send: %d msgs, ~%d chars", len(messages), sum(len(m["content"]) for m in messages))

    extra = {"frequency_penalty": FREQUENCY_PENALTY} if FREQUENCY_PENALTY else {}
    response = await client.chat.completions.create(
        model=LM_STUDIO_MODEL,
        messages=messages,
        max_tokens=kwargs.get("max_tokens", default_cap),
        temperature=kwargs.get("temperature", DEFAULT_TEMPERATURE),
        **extra,
    )
    choice = response.choices[0]
    if choice.finish_reason == "length":
        # Silent truncation corrupts extraction output and cuts answers short.
        log.warning("LLM output truncated at max_tokens (model=%s)", LM_STUDIO_MODEL)
    return _THINK_RE.sub("", choice.message.content or "")
