from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
import pytesseract

from dbthatdoc.extractors.pdf_text import calculate_sha256
from dbthatdoc.models import (
    ExtractionResult,
    PageContent,
    ProcessingInfo,
    SourceInfo,
)


def extract_pdf_ocr(
    file_path: str | Path,
    language: str = "deu+eng",
    scale: float = 3.0,
) -> ExtractionResult:
    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")

    if not path.is_file():
        raise ValueError(f"Pfad ist keine Datei: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Nicht unterstützter Dateityp: {path.suffix}")

    pages: list[PageContent] = []
    warnings: list[str] = []

    pdf = pdfium.PdfDocument(str(path))

    try:
        for page_number in range(len(pdf)):
            page = pdf[page_number]
            image = page.render(scale=scale).to_pil()

            text = pytesseract.image_to_string(
                image,
                lang=language,
                config="--psm 6",
            ).strip()

            if not text:
                warnings.append(
                    f"OCR konnte auf Seite {page_number + 1} keinen Text erkennen."
                )

            width, height = image.size

            pages.append(
                PageContent(
                    page_number=page_number + 1,
                    text=text,
                    width=float(width),
                    height=float(height),
                )
            )
    finally:
        pdf.close()

    combined_text = "\n\n".join(
        page.text for page in pages if page.text.strip()
    )

    if not combined_text:
        warnings.append("OCR hat in der gesamten PDF keinen Text erkannt.")

    return ExtractionResult(
        source=SourceInfo(
            filename=path.name,
            path=str(path),
            media_type="application/pdf",
            source_type="pdf",
            file_size_bytes=path.stat().st_size,
            sha256=calculate_sha256(path),
        ),
        pages=pages,
        text=combined_text,
        warnings=warnings,
        processing=ProcessingInfo(
            extractor="tesseract+pypdfium2",
            extractor_version=str(
                pytesseract.get_tesseract_version()
            ),
            page_count=len(pages),
            extraction_method="ocr",
            text_extracted=bool(combined_text),
        ),
    )