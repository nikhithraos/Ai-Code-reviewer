from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Category(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    QUALITY = "quality"


class Finding(BaseModel):
    id: str = ""
    category: Category
    severity: Severity
    title: str
    line_start: Optional[int] = None
    explanation: str
    suggested_fix: str
    source: str = "llm"          # "ast" (deterministic) or "llm"

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v):
        # LLMs often return "high" or "HIGH" instead of "High"
        return v.strip().capitalize() if isinstance(v, str) else v


class ReviewResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class FixResult(BaseModel):
    improved_code: str
    changes: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    language: str
    initial: list[Finding] = Field(default_factory=list)
    fix: Optional[FixResult] = None
    final: list[Finding] = Field(default_factory=list)
    resolved: list[Finding] = Field(default_factory=list)
    remaining: list[Finding] = Field(default_factory=list)
    introduced: list[Finding] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    comparison_reliable: bool = True