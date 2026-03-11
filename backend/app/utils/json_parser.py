"""
Robust JSON extraction from LLM responses.

LLMs frequently return JSON wrapped in markdown code fences, or with
leading/trailing prose.  This module tries three increasingly aggressive
strategies before giving up and returning a fallback dict.

Usage:
    data = parse_llm_json(llm_response_text)
    data = parse_llm_json(llm_response_text, fallback={"score": 50, "findings": []})
"""

import json
import re
from typing import Any, Optional

from app.utils.logger import get_logger

log = get_logger(__name__)

# Regex to extract the first JSON object or array from a string
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}", re.DOTALL)
_JSON_ARRAY_RE  = re.compile(r"\[[\s\S]*\]",  re.DOTALL)

# Regex for markdown code fences: ```json ... ``` or ``` ... ```
_CODE_FENCE_RE  = re.compile(
    r"```(?:json)?\s*\n?([\s\S]*?)\n?```",
    re.IGNORECASE,
)


def parse_llm_json(
    text: str,
    fallback: Optional[dict] = None,
    prefer_array: bool = False,
) -> Any:
    """
    Extract and parse JSON from an LLM response string.

    Strategy order:
      1. Direct json.loads on the stripped text
      2. Extract from markdown code fence (```json ... ```)
      3. Regex-extract the first {...} or [...] from the text

    Returns the parsed Python object on success, or *fallback* (default {})
    on total failure.
    """
    if fallback is None:
        fallback = {}

    text = text.strip()

    # --- Strategy 1: direct parse ---
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # --- Strategy 2: extract from code fence ---
    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            log.debug("parse_llm_json: code-fence content is not valid JSON")

    # --- Strategy 3: regex extract first JSON object or array ---
    pattern = _JSON_ARRAY_RE if prefer_array else _JSON_OBJECT_RE
    match = pattern.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            # Try the other pattern
            alt_pattern = _JSON_OBJECT_RE if prefer_array else _JSON_ARRAY_RE
            alt_match = alt_pattern.search(text)
            if alt_match:
                try:
                    return json.loads(alt_match.group(0))
                except json.JSONDecodeError:
                    pass

    # --- All strategies failed ---
    log.warning(
        "parse_llm_json: all strategies failed — returning fallback. "
        "First 200 chars of response: %r",
        text[:200],
    )
    return fallback


def extract_score(text: str, default: float = 50.0) -> float:
    """
    Pull a numeric score out of free-form LLM text when JSON parsing fails.

    Looks for patterns like: "score: 72", "Score: 72/100", "72 out of 100"
    Returns *default* if nothing is found.
    """
    patterns = [
        r'"score"\s*:\s*(\d+(?:\.\d+)?)',       # JSON-style "score": 72
        r'score[:\s]+(\d+(?:\.\d+)?)',           # score: 72
        r'(\d+(?:\.\d+)?)\s*/\s*100',           # 72/100
        r'(\d+(?:\.\d+)?)\s+out\s+of\s+100',   # 72 out of 100
        r'rating[:\s]+(\d+(?:\.\d+)?)',          # rating: 72
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if 0 <= value <= 100:
                return value

    log.debug("extract_score: no score pattern found, using default=%.1f", default)
    return default
