from __future__ import annotations

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    text: str
    page_number: int = Field(ge=1)

    source: str
    confidence: float | None = None

    x0: float | None = None
    y0: float | None = None
    x1: float | None = None
    y1: float | None = None


class DocumentPage(BaseModel):
    page_number: int = Field(ge=1)
    width: float | None = None
    height: float | None = None

    blocks: list[TextBlock] = Field(default_factory=list)


class DocumentContent(BaseModel):
    source_file: str
    pages: list[DocumentPage] = Field(default_factory=list)

    full_text: str = ""

    extraction_methods: list[str] = Field(default_factory=list)