from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

import pdfplumber

from dbthatdoc.models import (
    ExtractionResult,
    PageContent,
    ProcessingInfo,
    SourceInfo,
)


def calculate_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def extract_pdf_text(file_path: str | Path) -> ExtractionResult:
    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")

    if not path.is_file():
        raise ValueError(f"Pfad ist keine Datei: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Nicht unterstützter Dateityp: {path.suffix}")

    media_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
    pages: list[PageContent] = []
    warnings: list[str] = []

    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            if not text.strip():
                warnings.append(
                    f"Seite {page_number} enthält keinen extrahierbaren Text."
                )

            pages.append(
                PageContent(
                    page_number=page_number,
                    text=text,
                    width=float(page.width),
                    height=float(page.height),
                )
            )

    combined_text = "\n\n".join(
        page.text for page in pages if page.text.strip()
    )

    if not combined_text.strip():
        warnings.append(
            "Die PDF enthält keinen eingebetteten Text. OCR ist vermutlich erforderlich."
        )

    return ExtractionResult(
        source=SourceInfo(
            filename=path.name,
            path=str(path),
            media_type=media_type,
            source_type="pdf",
            file_size_bytes=path.stat().st_size,
            sha256=calculate_sha256(path),
        ),
        pages=pages,
        text=combined_text,
        warnings=warnings,
        processing=ProcessingInfo(
    		extractor="pdfplumber",
    		extractor_version=getattr(pdfplumber, "__version__", None),
    		page_count=len(pages),
    		extraction_method=(
        		"embedded_text"
        		if combined_text.strip()
        		else "no_text_layer"
    		),
    		text_extracted=bool(combined_text.strip()),
	),
    )