from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from dbthatdoc.models.content import TextPosition


class AnalysisEvidence(BaseModel):
    page_number: int = Field(ge=1)
    block_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    position: TextPosition | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)


class AnalysisCandidate(BaseModel):
    kind: Literal["key_value"] = "key_value"
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    relation: Literal["inline", "right", "below"]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[AnalysisEvidence] = Field(min_length=1)
    entity_ids: list[str] = Field(default_factory=list)
    label_start_offset: int | None = Field(default=None, ge=0)
    label_end_offset: int | None = Field(default=None, ge=0)
    value_start_offset: int | None = Field(default=None, ge=0)
    value_end_offset: int | None = Field(default=None, ge=0)


class ValidationCheck(BaseModel):
    rule: str = Field(min_length=1)
    dimension: Literal[
        "syntax",
        "structure",
        "checksum",
        "semantic",
        "external",
    ]
    passed: bool | None = None
    details: str = Field(min_length=1)


class AnalysisEntity(BaseModel):
    id: str = Field(min_length=1)
    kind: Literal[
        "iban",
        "tax_number",
        "money",
        "date",
        "postal_code",
        "party",
    ]
    value: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1)
    validation_status: Literal["valid", "plausible", "invalid"]
    recognition_status: Literal[
        "recognized",
        "recognized_invalid",
        "suspected_ocr_corruption",
    ] = "recognized"
    validation: list[ValidationCheck] = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[AnalysisEvidence] = Field(min_length=1)


class AnalyzerInfo(BaseModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class AnalysisResult(BaseModel):
    source_file: str
    candidates: list[AnalysisCandidate] = Field(default_factory=list)
    entities: list[AnalysisEntity] = Field(default_factory=list)
    analyzers: list[AnalyzerInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
