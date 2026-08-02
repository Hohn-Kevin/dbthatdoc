from __future__ import annotations

from pathlib import Path

from dbthatdoc.extractors import extract_pdf_ocr, extract_pdf_text
from dbthatdoc.models import ExtractionResult


def inspect_file(file_path: str | Path) -> ExtractionResult:
    path = Path(file_path)

    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"Nicht unterstützter Dateityp: {path.suffix or 'ohne Dateiendung'}"
        )

    text_result = extract_pdf_text(path)

    if text_result.processing.text_extracted:
        return text_result

    return extract_pdf_ocr(path)