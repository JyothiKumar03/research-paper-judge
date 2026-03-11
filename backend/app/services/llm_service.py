import asyncio
import base64
import time
from typing import Optional

import httpx

from app.config import settings
from app.constants import (
    BACKOFF_BASE_S,
    MAX_RETRIES_PER_MODEL,
    OPENROUTER_BASE_URL,
    TASK_MODEL_CHAIN,
    TaskType,
)
from app.types import LLMResponse, ModelConfig, TokenUsage
from app.utils.logger import get_logger

log = get_logger(__name__)

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


class LLMExhaustedError(RuntimeError):
    pass


def build_model_chain(task: TaskType, retries: int = MAX_RETRIES_PER_MODEL) -> list[ModelConfig]:
    return [ModelConfig(model=m, retries=retries) for m in TASK_MODEL_CHAIN[task]]


def _is_gemini(model: str) -> bool:
    return model.startswith("google/")


def _gemini_model_name(model: str) -> str:
    return model.removeprefix("google/").removesuffix(":free")


async def call_llm(
    prompt: str,
    models: list[ModelConfig],
    system: str = "",
    vision_images: Optional[list[bytes]] = None,
    response_max_tokens: int = 4_096,
    json_schema: Optional[dict] = None,
) -> LLMResponse:
    if not models:
        raise ValueError("call_llm: models list is empty")

    for model_cfg in models:
        response = await _try_model(model_cfg, prompt, system, vision_images, response_max_tokens, json_schema)
        if response is not None:
            return response

    raise LLMExhaustedError(f"call_llm: all {len(models)} model(s) exhausted")


async def _try_model(
    model_cfg: ModelConfig,
    prompt: str,
    system: str,
    vision_images: Optional[list[bytes]],
    response_max_tokens: int,
    json_schema: Optional[dict],
) -> Optional[LLMResponse]:
    payload = _build_payload(
        model=model_cfg.model,
        prompt=prompt,
        system=system,
        vision_images=vision_images,
        temperature=model_cfg.temperature,
        max_tokens=min(model_cfg.max_tokens, response_max_tokens),
        json_schema=json_schema,
    )

    post_fn = _post_gemini if _is_gemini(model_cfg.model) else _post_openrouter

    for attempt in range(1, model_cfg.retries + 1):
        log.debug("_try_model: model=%s attempt=%d/%d", model_cfg.model, attempt, model_cfg.retries)
        t0 = time.perf_counter()

        try:
            result = await post_fn(payload)
            log.info(
                "call_llm: ok model=%s tokens=%d %.2fs",
                model_cfg.model, result.usage.total_tokens, time.perf_counter() - t0,
            )
            return result

        except httpx.HTTPStatusError as exc:
            err_msg = _extract_error(exc)
            status = exc.response.status_code

            if status == 429 or status >= 500:
                delay = BACKOFF_BASE_S ** attempt
                log.warning(
                    "_try_model: HTTP %d on %s — %s | backoff %.1fs",
                    status, model_cfg.model, err_msg, delay,
                )
                await asyncio.sleep(delay)
            else:
                log.error(
                    "_try_model: HTTP %d (non-retryable) on %s — %s",
                    status, model_cfg.model, err_msg,
                )
                return None

        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            delay = BACKOFF_BASE_S ** attempt
            log.warning("_try_model: %s on %s | backoff %.1fs", type(exc).__name__, model_cfg.model, delay)
            await asyncio.sleep(delay)

        except Exception as exc:
            log.error("_try_model: unexpected error on %s — %s", model_cfg.model, exc, exc_info=True)
            return None

    log.warning("_try_model: retries exhausted for %s", model_cfg.model)
    return None


def _extract_error(exc: httpx.HTTPStatusError) -> str:
    try:
        body = exc.response.json()
        error = body.get("error", {})
        message = error.get("message") or body.get("message") or ""
        # OpenRouter proxies provider errors — extract the raw upstream message
        metadata = error.get("metadata", {})
        provider_raw = metadata.get("raw", "")
        provider_name = metadata.get("provider_name", "")
        if provider_raw:
            return f"{message} | provider={provider_name} | raw={provider_raw[:500]}"
        return message or exc.response.text[:400]
    except Exception:
        return exc.response.text[:400]


def _build_payload(
    model: str,
    prompt: str,
    system: str,
    vision_images: Optional[list[bytes]],
    temperature: float,
    max_tokens: int,
    json_schema: Optional[dict] = None,
) -> dict:
    messages: list[dict] = []

    if system:
        messages.append({"role": "system", "content": system})

    if vision_images:
        content_parts: list[dict] = [{"type": "text", "text": prompt}]
        for img_bytes in vision_images:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        messages.append({"role": "user", "content": content_parts})
    else:
        messages.append({"role": "user", "content": prompt})

    # Gemini API takes model name without the google/ prefix and :free suffix
    api_model = _gemini_model_name(model) if _is_gemini(model) else model

    payload: dict = {
        "model": api_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if json_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": json_schema,
        }

    return payload


async def _post_openrouter(payload: dict) -> LLMResponse:
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY is not set")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/research-validator",
        "X-Title": "Research Validator",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(OPENROUTER_BASE_URL, json=payload, headers=headers)
        response.raise_for_status()

    return _parse_response(response.json(), payload["model"])


async def _post_gemini(payload: dict) -> LLMResponse:
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not set — add it to .env")

    headers = {
        "Authorization": f"Bearer {settings.gemini_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(_GEMINI_BASE_URL, json=payload, headers=headers)
        response.raise_for_status()

    return _parse_response(response.json(), payload["model"])


def _parse_response(data: dict, fallback_model: str) -> LLMResponse:
    usage_raw = data.get("usage", {})
    return LLMResponse(
        content=data["choices"][0]["message"]["content"] or "",
        usage=TokenUsage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
        ),
        model_used=data.get("model", fallback_model),
        success=True,
    )
