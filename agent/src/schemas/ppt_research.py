"""Research-stage schemas for PPT generation workflow."""

from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ResearchQuestion(BaseModel):
    """Key clarification question before content planning."""

    question: str = Field(..., min_length=4, max_length=300)
    category: Literal["audience", "purpose", "style", "data", "scope"]
    why: str = Field(..., min_length=4, max_length=500)


class ResearchEvidence(BaseModel):
    """Normalized evidence item used for grounded content generation."""

    claim: str = Field(..., min_length=3, max_length=500)
    source_title: str = Field(..., min_length=2, max_length=300)
    source_url: str = Field(..., min_length=8, max_length=2048)
    snippet: str = Field(default="", max_length=800)
    published_at: str = Field(default="", max_length=80)
    fetched_at: str = Field(default="", max_length=80)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    provenance: Literal["web", "user", "fallback"] = "web"
    tags: List[str] = Field(default_factory=list, max_length=12)


class ResearchGap(BaseModel):
    """Detected information gap before structured enrichment."""

    code: Literal[
        "audience",
        "purpose",
        "style",
        "required_facts",
        "time_range",
        "geography",
        "citations",
    ]
    severity: Literal["low", "medium", "high"] = "medium"
    message: str = Field(..., min_length=3, max_length=500)
    query_hint: str = Field(default="", max_length=500)


class ResearchRequest(BaseModel):
    """Input payload for research context generation."""

    topic: str = Field(..., min_length=2, max_length=500)
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    audience: str = Field(default="general", max_length=200)
    purpose: str = Field(default="presentation", max_length=200)
    style_preference: str = Field(default="professional", max_length=200)
    constraints: List[str] = Field(default_factory=list, max_length=20)
    required_facts: List[str] = Field(default_factory=list, max_length=20)
    geography: str = Field(default="", max_length=120)
    time_range: str = Field(default="", max_length=120)
    domain_terms: List[str] = Field(default_factory=list, max_length=20)
    web_enrichment: bool = True
    min_completeness: float = Field(default=0.4, ge=0.3, le=1.0)
    desired_citations: int = Field(default=3, ge=1, le=12)
    max_web_queries: int = Field(default=4, ge=1, le=8)
    max_search_results: int = Field(default=5, ge=3, le=10)

    @field_validator("constraints", "required_facts", "domain_terms")
    @classmethod
    def dedup_list_items(cls, value: List[str]) -> List[str]:
        dedup: List[str] = []
        seen = set()
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            dedup.append(text)
        return dedup


class ResearchContext(BaseModel):
    """Research result used as source of truth for planning."""

    topic: str = Field(..., min_length=2, max_length=500)
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    audience: str = Field(..., min_length=1, max_length=200)
    purpose: str = Field(..., min_length=1, max_length=200)
    style_preference: str = Field(..., min_length=1, max_length=200)
    constraints: List[str] = Field(default_factory=list, max_length=20)
    required_facts: List[str] = Field(default_factory=list, max_length=20)
    geography: str = Field(default="", max_length=120)
    time_range: str = Field(default="", max_length=120)
    domain_terms: List[str] = Field(default_factory=list, max_length=20)
    key_data_points: List[str] = Field(default_factory=list, min_length=3, max_length=30)
    reference_materials: List[Dict[str, str]] = Field(default_factory=list, max_length=20)
    evidence: List[ResearchEvidence] = Field(default_factory=list, max_length=40)
    gap_report: List[ResearchGap] = Field(default_factory=list, max_length=20)
    completeness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    enrichment_applied: bool = False
    enrichment_strategy: Literal["none", "web", "web+fallback"] = "none"
    questions: List[ResearchQuestion] = Field(default_factory=list, min_length=3, max_length=8)

    @model_validator(mode="after")
    def validate_reference_materials(self) -> "ResearchContext":
        for idx, item in enumerate(self.reference_materials):
            if not isinstance(item, dict):
                raise ValueError(f"reference_materials[{idx}] must be an object")
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                raise ValueError(
                    f"reference_materials[{idx}] must include non-empty title and url"
                )
        for idx, item in enumerate(self.evidence):
            if not item.source_url.startswith(("http://", "https://")):
                raise ValueError(f"evidence[{idx}].source_url must be absolute http(s) url")
        return self
