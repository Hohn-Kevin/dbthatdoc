from __future__ import annotations

from pathlib import Path

from dbthatdoc.analysis import analyze_content
from dbthatdoc.extractors import extract_pdf_ocr, extract_pdf_text
from dbthatdoc.models import AnalysisResult, ExtractionResult
from dbthatdoc.normalization import normalize_extraction


def inspect_file(
    file_path: str | Path,
    *,
    ocr_page_segmentation_mode: int = 3,
) -> ExtractionResult:
    path = Path(file_path)

    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"Nicht unterstützter Dateityp: {path.suffix or 'ohne Dateiendung'}"
        )

    text_result = extract_pdf_text(path)

    if text_result.processing.text_extracted:
        return text_result

    return extract_pdf_ocr(
        path,
        page_segmentation_mode=ocr_page_segmentation_mode,
    )


def analyze_file(
    file_path: str | Path,
    *,
    ocr_page_segmentation_mode: int = 3,
) -> AnalysisResult:
    extraction = inspect_file(
        file_path,
        ocr_page_segmentation_mode=ocr_page_segmentation_mode,
    )
    content = normalize_extraction(extraction)
    return analyze_content(content)
