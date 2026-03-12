from typing import Optional

from pydantic import BaseModel, Field

from app.constants import AgentName, AgentStatus, FindingSeverity, ModelID


class ModelConfig(BaseModel):
    model: ModelID
    temperature: float = 0.2
    max_tokens: int = 10_000
    retries: int = 3


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    content: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    model_used: str
    success: bool = True


class Finding(BaseModel):
    category: str
    location: str
    description: str
    severity: FindingSeverity
    suggestion: str = ""


class AgentResult(BaseModel):
    agent_name: AgentName
    score: Optional[float] = None
    findings: list[Finding] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    duration_s: float = 0.0
    status: AgentStatus = AgentStatus.COMPLETED
    error_msg: Optional[str] = None
    raw_output: str = ""
