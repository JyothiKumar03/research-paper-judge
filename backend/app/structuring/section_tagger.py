import asyncio
from pathlib import Path

import asyncpg

from app.constants import SectionTag, TaskType
from app.db import insert_page
from app.prompts.page_tagger import (
    PAGE_TAG_JSON_SCHEMA,
    PAGE_TAG_SYSTEM,
    build_text_prompt,
    build_vision_prompt,
)
from app.services.llm_service import LLMExhaustedError, build_model_chain, call_llm
from app.types import PageData
from app.utils.json_parser import parse_llm_json
from app.utils.logger import get_logger

log = get_logger(__name__)

_CONCURRENCY = 3


async def tag_page(page: PageData) -> PageData:
    # --- vision path: page has a screenshot (tables/figures present) ---
    if page.has_screenshot and page.screenshot_path:
        try:
            vision_bytes = Path(page.screenshot_path).read_bytes()
        except Exception as exc:
            log.warning("tag_page[%d]: cannot read screenshot %s — %s", page.page, page.screenshot_path, exc)
            vision_bytes = None

        if vision_bytes is not None:
            vision_models = build_model_chain(TaskType.PAGE_TAG_VISION)
            prompt = build_vision_prompt(page.markdown)
            try:
                response = await call_llm(
                    prompt,
                    vision_models,
                    system=PAGE_TAG_SYSTEM,
                    vision_images=[vision_bytes],
                    json_schema=PAGE_TAG_JSON_SCHEMA,
                )
                result = _parse_response(response.content, page.page, response.model_used)
                if result is not None:
                    log.info("tag_page[%d]: vision tag=%s model=%s", page.page, result["page_tag"], response.model_used)
                    return page.model_copy(update=result)
                log.warning("tag_page[%d]: vision parse failed — falling back to text", page.page)
            except LLMExhaustedError:
                log.warning("tag_page[%d]: all vision models exhausted — falling back to text", page.page)
            except Exception as exc:
                log.warning("tag_page[%d]: vision error — %s — falling back to text", page.page, exc)

    # --- text path (used directly for text-only pages, or as vision fallback) ---
    text_models = build_model_chain(TaskType.PAGE_TAG_TEXT)
    prompt = build_text_prompt(page.markdown)
    try:
        response = await call_llm(prompt, text_models, system=PAGE_TAG_SYSTEM, json_schema=PAGE_TAG_JSON_SCHEMA)
        result = _parse_response(response.content, page.page, response.model_used)
        if result is not None:
            log.info("tag_page[%d]: text tag=%s model=%s", page.page, result["page_tag"], response.model_used)
            return page.model_copy(update=result)
        log.warning("tag_page[%d]: text parse failed — tagging as OTHER", page.page)
    except LLMExhaustedError:
        log.error("tag_page[%d]: all text models exhausted — tagging as OTHER", page.page)
    except Exception as exc:
        log.error("tag_page[%d]: text error — %s — tagging as OTHER", page.page, exc)

    return page.model_copy(update={"page_tag": SectionTag.OTHER, "page_summary": "", "image_data": ""})


def _parse_response(content: str, page_num: int, model: str) -> dict | None:
    parsed = parse_llm_json(content, fallback={})
    if not isinstance(parsed, dict) or "page_tag" not in parsed:
        log.warning("tag_page[%d]: model=%s — no page_tag in response: %r", page_num, model, content[:200])
        return None

    tag_str = parsed.get("page_tag", "").strip().upper()
    try:
        page_tag = SectionTag(tag_str)
    except ValueError:
        log.warning("tag_page[%d]: model=%s — unknown tag %r — using OTHER", page_num, model, tag_str)
        page_tag = SectionTag.OTHER

    return {
        "page_tag":    page_tag,
        "page_summary": parsed.get("page_summary", "").strip(),
        "image_data":  parsed.get("image_data", "").strip(),
    }


async def tag_all_pages(pool: asyncpg.Pool, paper_id: str, pages: list[PageData]) -> list[PageData]:
    """
    Tags every page concurrently (up to _CONCURRENCY at a time).
    Each page is stored to the DB immediately after tagging — no waiting for the full batch.
    """
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _tag_and_store(page: PageData) -> PageData:
        async with semaphore:
            tagged = await tag_page(page)
            try:
                await insert_page(pool, paper_id, tagged)
                log.debug("tag_all_pages: stored page %d (tag=%s)", tagged.page, tagged.page_tag)
            except Exception as exc:
                log.error("tag_all_pages: DB write failed for page %d — %s", tagged.page, exc)
            return tagged

    log.info("tag_all_pages: starting %d pages (concurrency=%d)", len(pages), _CONCURRENCY)
    results = list(await asyncio.gather(*[_tag_and_store(p) for p in pages]))

    tagged = sum(1 for p in results if p.page_tag not in (None, SectionTag.OTHER))
    other  = sum(1 for p in results if p.page_tag == SectionTag.OTHER)
    log.info("tag_all_pages: done — tagged=%d other=%d / total=%d", tagged, other, len(results))
    return results
