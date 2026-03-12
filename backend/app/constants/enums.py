from enum import StrEnum


class SectionTag(StrEnum):
    TITLE           = "TITLE"
    ABSTRACT        = "ABSTRACT"
    INTRODUCTION    = "INTRODUCTION"
    RELATED_WORK    = "RELATED_WORK"
    BACKGROUND      = "BACKGROUND"
    METHODOLOGY     = "METHODOLOGY"
    EXPERIMENTS     = "EXPERIMENTS"
    RESULTS         = "RESULTS"
    DISCUSSION      = "DISCUSSION"
    CONCLUSION      = "CONCLUSION"
    REFERENCES      = "REFERENCES"
    APPENDIX        = "APPENDIX"
    ACKNOWLEDGMENTS = "ACKNOWLEDGMENTS"
    OTHER           = "OTHER"


EVALUABLE_SECTIONS: frozenset[SectionTag] = frozenset({
    SectionTag.ABSTRACT,
    SectionTag.INTRODUCTION,
    SectionTag.RELATED_WORK,
    SectionTag.METHODOLOGY,
    SectionTag.RESULTS,
    SectionTag.DISCUSSION,
    SectionTag.CONCLUSION,
    SectionTag.BACKGROUND,
})

SECTION_MERGE_MAP: dict[SectionTag, SectionTag] = {
    SectionTag.EXPERIMENTS: SectionTag.RESULTS,
}

SECTION_FALLBACKS: dict[SectionTag, list[SectionTag]] = {
    SectionTag.METHODOLOGY:  [SectionTag.EXPERIMENTS, SectionTag.BACKGROUND],
    SectionTag.RESULTS:      [SectionTag.EXPERIMENTS, SectionTag.DISCUSSION],
    SectionTag.RELATED_WORK: [SectionTag.BACKGROUND, SectionTag.INTRODUCTION],
    SectionTag.DISCUSSION:   [SectionTag.CONCLUSION],
}


class ExtractionPath(StrEnum):
    PDF   = "pdf"
    LATEX = "latex"


class PipelineStage(StrEnum):
    INGESTION         = "ingestion"
    PAGE_EXTRACTION   = "page_extraction"
    SECTION_TAGGING   = "section_tagging"
    STITCHING         = "stitching"
    TOKEN_BUDGET      = "token_budget"
    WAVE1_AGENTS      = "wave1_agents"
    WAVE2_AGENTS      = "wave2_agents"
    AGGREGATION       = "aggregation"
    EXECUTIVE_SUMMARY = "executive_summary"
    REPORT_GENERATION = "report_generation"
    DISPLAY           = "display"


class AgentName(StrEnum):
    GRAMMAR      = "grammar"
    NOVELTY      = "novelty"
    FACTCHECK    = "factcheck"
    CONSISTENCY  = "consistency"
    AUTHENTICITY = "authenticity"


AGENT_REQUIRED_SECTIONS: dict[AgentName, list[SectionTag]] = {
    AgentName.GRAMMAR: [
        SectionTag.ABSTRACT, SectionTag.INTRODUCTION, SectionTag.RELATED_WORK,
        SectionTag.METHODOLOGY, SectionTag.RESULTS, SectionTag.DISCUSSION,
        SectionTag.CONCLUSION,
    ],
    AgentName.NOVELTY: [
        SectionTag.ABSTRACT, SectionTag.INTRODUCTION,
        SectionTag.RELATED_WORK, SectionTag.CONCLUSION,
    ],
    AgentName.FACTCHECK: [
        SectionTag.INTRODUCTION, SectionTag.METHODOLOGY, SectionTag.RESULTS,
    ],
    AgentName.CONSISTENCY: [
        SectionTag.METHODOLOGY, SectionTag.RESULTS,
    ],
    AgentName.AUTHENTICITY: [
        SectionTag.RESULTS, SectionTag.METHODOLOGY,
    ],
}


class AgentStatus(StrEnum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class PipelineStatus(StrEnum):
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class GrammarIssueType(StrEnum):
    SPELLING      = "spelling"
    GRAMMAR_ERROR = "grammar_error"
    PUNCTUATION   = "punctuation"
    STYLE         = "style"
    CLARITY       = "clarity"
    REDUNDANCY    = "redundancy"
    JARGON        = "jargon"


class GrammarRating(StrEnum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class NoveltyIndex(StrEnum):
    HIGHLY_NOVEL           = "HIGHLY_NOVEL"
    MODERATELY_NOVEL       = "MODERATELY_NOVEL"
    INCREMENTAL            = "INCREMENTAL"
    POTENTIALLY_DERIVATIVE = "POTENTIALLY_DERIVATIVE"


NOVELTY_SCORE_MAP: dict[NoveltyIndex, float] = {
    NoveltyIndex.HIGHLY_NOVEL:           90.0,
    NoveltyIndex.MODERATELY_NOVEL:       70.0,
    NoveltyIndex.INCREMENTAL:            45.0,
    NoveltyIndex.POTENTIALLY_DERIVATIVE: 20.0,
}


class ContributionAssessment(StrEnum):
    SIGNIFICANT = "SIGNIFICANT"
    MODERATE    = "MODERATE"
    MINOR       = "MINOR"
    UNCLEAR     = "UNCLEAR"


class ClaimCategory(StrEnum):
    CONSTANT    = "constant"
    FORMULA     = "formula"
    HISTORICAL  = "historical"
    STATISTICAL = "statistical"
    BENCHMARK   = "benchmark"
    CITATION    = "citation"
    DEFINITION  = "definition"


class ClaimStatus(StrEnum):
    VERIFIED   = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    SUSPICIOUS = "SUSPICIOUS"
    TRIVIAL    = "TRIVIAL"


class GapSeverity(StrEnum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class RiskLevel(StrEnum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"
    NONE   = "NONE"


class RedFlagType(StrEnum):
    TOO_PERFECT        = "too_perfect"
    ROUND_NUMBERS      = "round_numbers"
    NO_ERROR_BARS      = "no_error_bars"
    NO_ABLATION        = "no_ablation"
    CHERRY_PICKED      = "cherry_picked"
    LOGICAL_LEAP       = "logical_leap"
    MISSING_BASELINE   = "missing_baseline"
    SCALE_MISMATCH     = "scale_mismatch"
    P_HACKING          = "p_hacking"
    NO_REPRODUCIBILITY = "no_reproducibility"


class FindingSeverity(StrEnum):
    HIGH        = "HIGH"
    MEDIUM      = "MEDIUM"
    LOW         = "LOW"
    NOVEL       = "NOVEL"
    INCREMENTAL = "INCREMENTAL"
    DERIVATIVE  = "DERIVATIVE"
    VERIFIED    = "VERIFIED"
    SUSPICIOUS  = "SUSPICIOUS"
    UNVERIFIED  = "UNVERIFIED"
    SUPPORTED   = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    GAP         = "GAP"
    HIGH_RISK   = "HIGH_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    LOW_RISK    = "LOW_RISK"


AGENT_WEIGHTS: dict[AgentName, float] = {
    AgentName.CONSISTENCY:  0.30,
    AgentName.AUTHENTICITY: 0.25,
    AgentName.NOVELTY:      0.20,
    AgentName.FACTCHECK:    0.15,
    AgentName.GRAMMAR:      0.10,
}

PASS_THRESHOLD: float = 60.0
DEFAULT_SCORE:  float = 50.0


class ModelID(StrEnum):
    # --- Native Gemini API (google/* prefix routes to Gemini API directly) ---
    # GEMINI_25_FLASH = "google/gemini-3-flash-preview"
    GEMINI_25_FLASH = "google/gemini-2.5-flash"

    # --- OpenRouter free models (vision-capable) ---
    QWEN3_VL_30B     = "qwen/qwen3-vl-30b-a3b-thinking"
    NEMOTRON_12B_VL  = "nvidia/nemotron-nano-12b-v2-vl:free"

    # --- OpenRouter free models (text-only) ---
    QWEN3_NEXT_80B   = "qwen/qwen3-next-80b-a3b-instruct:free"
    GLM_45_AIR       = "z-ai/glm-4.5-air:free"
    STEPFUN_FLASH    = "stepfun/step-3.5-flash:free"
    ARCEE_TRINITY    = "arcee-ai/trinity-large-preview:free"
    MISTRAL_SMALL    = "mistralai/mistral-small-3.1-24b-instruct:free"
    OPENROUTER_AUTO = "openrouter/auto"


class TaskType(StrEnum):
    PAGE_TAG_VISION   = "page_tag_vision"
    PAGE_TAG_TEXT     = "page_tag_text"
    GRAMMAR           = "grammar"
    NOVELTY           = "novelty"
    FACTCHECK         = "factcheck"
    CONSISTENCY       = "consistency"
    AUTHENTICITY      = "authenticity"
    EXECUTIVE_SUMMARY = "executive_summary"


# Models that do NOT support json_schema response_format.
# They accept json_object (valid JSON, no schema enforcement) or text.
NO_SCHEMA_MODELS: frozenset[str] = frozenset({
    ModelID.STEPFUN_FLASH,
})

TASK_MODEL_CHAIN: dict[TaskType, list[ModelID]] = {
    TaskType.PAGE_TAG_VISION: [
        ModelID.QWEN3_VL_30B,
        ModelID.NEMOTRON_12B_VL,
        ModelID.GEMINI_25_FLASH,
    ],
    TaskType.PAGE_TAG_TEXT: [
        ModelID.GEMINI_25_FLASH,
        ModelID.QWEN3_NEXT_80B,
        ModelID.STEPFUN_FLASH,
        ModelID.GLM_45_AIR,
    ],
    TaskType.GRAMMAR: [
        ModelID.GEMINI_25_FLASH,
        ModelID.STEPFUN_FLASH,
        ModelID.ARCEE_TRINITY,
        ModelID.MISTRAL_SMALL,
    ],
    TaskType.NOVELTY: [
        ModelID.GEMINI_25_FLASH,
        ModelID.QWEN3_NEXT_80B,
        ModelID.GLM_45_AIR,
    ],
    TaskType.FACTCHECK: [
        ModelID.GEMINI_25_FLASH,
        ModelID.QWEN3_NEXT_80B,
        ModelID.STEPFUN_FLASH,
    ],
    TaskType.CONSISTENCY: [
        ModelID.GEMINI_25_FLASH,
        ModelID.GLM_45_AIR,
        ModelID.QWEN3_NEXT_80B,
    ],
    TaskType.AUTHENTICITY: [
        ModelID.GEMINI_25_FLASH,
        ModelID.STEPFUN_FLASH,
        ModelID.GLM_45_AIR,
        ModelID.QWEN3_NEXT_80B,
    ],
    TaskType.EXECUTIVE_SUMMARY: [
        ModelID.GEMINI_25_FLASH,
        ModelID.ARCEE_TRINITY,
        ModelID.OPENROUTER_AUTO,
    ],
}

TOKEN_BUDGET_TOTAL:    int   = 16_000
MAX_RETRIES_PER_MODEL: int   = 2
BACKOFF_BASE_S:        float = 1.5
AGENT_TIMEOUT_S:       int   = 120

OPENROUTER_BASE_URL:   str   = "https://openrouter.ai/api/v1/chat/completions"
ARXIV_API_BASE:        str   = "https://export.arxiv.org/api/query"
# SEMANTIC_SCHOLAR_API:  str   = "https://api.semanticscholar.org/graph/v1"
