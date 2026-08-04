from pathlib import Path

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    filename: str
    path: str
    media_type: str
    source_type: str
    file_size_bytes: int
    sha256: str


class ExtractedElement(BaseModel):
    text: str
    element_type: str
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    x0: float | None = None
    y0: float | None = None
    x1: float | None = None
    y1: float | None = None


class PageContent(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    width: float | None = None
    height: float | None = None
    elements: list[ExtractedElement] = Field(default_factory=list)


class ProcessingInfo(BaseModel):
    extractor: str
    extractor_version: str | None = None
    page_count: int = Field(ge=0)
    extraction_method: str
    text_extracted: bool


class ExtractionResult(BaseModel):
    source: SourceInfo
    pages: list[PageContent]
    text: str
    warnings: list[str] = Field(default_factory=list)
    processing: ProcessingInfo

    @property
    def source_path(self) -> Path:
        return Path(self.source.path)