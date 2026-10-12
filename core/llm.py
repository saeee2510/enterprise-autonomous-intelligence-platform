"""
Thin wrapper around the OpenAI client.

Every LLM and embedding call goes through here so the pipeline can record
latency, token usage, and cost per step (used by the observability layer
and the evaluation).
"""
import json
import time

from core.config import config

# USD per 1M tokens (input, output). Check OpenAI's pricing page if you change models.
PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "text-embedding-3-small": (0.02, 0.0),
}

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = PRICES.get(model, (0.0, 0.0))
    return round((prompt_tokens * inp + completion_tokens * out) / 1_000_000, 6)


def chat(messages, json_mode: bool = False, temperature: float = 0.0, model: str = None):
    """Returns (text, usage) where usage has latency, tokens, and cost."""
    model = model or config.LLM_MODEL
    start = time.perf_counter()
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    resp = _get_client().chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        **kwargs,
    )
    usage = resp.usage
    meta = {
        "model": model,
        "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cost_usd": _cost(model, usage.prompt_tokens, usage.completion_tokens),
    }
    return resp.choices[0].message.content.strip(), meta


def chat_json(messages, temperature: float = 0.0, model: str = None):
    text, meta = chat(messages, json_mode=True, temperature=temperature, model=model)
    return json.loads(text), meta


def embed(texts):
    """Embeds a string or list of strings. Returns (vectors, usage)."""
    single = isinstance(texts, str)
    batch = [texts] if single else list(texts)
    start = time.perf_counter()
    resp = _get_client().embeddings.create(model=config.EMBEDDING_MODEL, input=batch)
    meta = {
        "model": config.EMBEDDING_MODEL,
        "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": 0,
        "cost_usd": _cost(config.EMBEDDING_MODEL, resp.usage.prompt_tokens, 0),
    }
    vectors = [d.embedding for d in resp.data]
    return (vectors[0] if single else vectors), meta
