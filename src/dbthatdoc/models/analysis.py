from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

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

    @model_validator(mode="after")
    def validate_offsets(self) -> Self:
        _validate_offset_pair(
            "evidence",
            self.start_offset,
            self.end_offset,
            len(self.text),
        )
        return self


class AnalysisCandidate(BaseModel):
    kind: Literal["key_value"] = "key_value"
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    relation: Literal["inline", "right", "below"]
    candidate_type: Literal["colon_structure", "spatial_key_value"]
    source_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    evidence: list[AnalysisEvidence] = Field(min_length=1)
    entity_ids: list[str] = Field(default_factory=list)
    label_start_offset: int | None = Field(default=None, ge=0)
    label_end_offset: int | None = Field(default=None, ge=0)
    value_start_offset: int | None = Field(default=None, ge=0)
    value_end_offset: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> Self:
        label_text = self.evidence[0].text
        value_text = (
            self.evidence[0].text
            if self.relation == "inline"
            else self.evidence[-1].text
        )
        _validate_offset_pair(
            "label",
            self.label_start_offset,
            self.label_end_offset,
            len(label_text),
        )
        _validate_offset_pair(
            "value",
            self.value_start_offset,
            self.value_end_offset,
            len(value_text),
        )
        if (
            self.relation == "inline"
            and self.label_end_offset is not None
            and self.value_start_offset is not None
            and self.label_end_offset > self.value_start_offset
        ):
            raise ValueError("inline label and value offsets must not overlap")
        return self


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
    party_type: Literal[
        "person",
        "organization",
        "unresolved",
    ] | None = None
    validation: list[ValidationCheck] = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    source_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
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


def _validate_offset_pair(
    name: str,
    start: int | None,
    end: int | None,
    text_length: int,
) -> None:
    if (start is None) != (end is None):
        raise ValueError(f"{name} offsets must be provided together")
    if start is None or end is None:
        return
    if start >= end:
        raise ValueError(f"{name} start offset must be before end offset")
    if end > text_length:
        raise ValueError(f"{name} end offset exceeds evidence text")
