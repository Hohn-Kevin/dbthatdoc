from __future__ import annotations

from dbthatdoc.models import (
    DocumentContent,
    DocumentPage,
    ExtractionResult,
    TextBlock,
)


def normalize_extraction(
    result: ExtractionResult,
) -> DocumentContent:
    pages: list[DocumentPage] = []

    for page in result.pages:
        block = TextBlock(
            text=page.text,
            page_number=page.page_number,
            source=result.processing.extractor,
            confidence=None,
            x0=None,
            y0=None,
            x1=None,
            y1=None,
        )

        pages.append(
            DocumentPage(
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                blocks=[block] if page.text.strip() else [],
            )
        )

    return DocumentContent(
        source_file=result.source.filename,
        pages=pages,
        full_text=result.text,
        extraction_methods=[
            result.processing.extractor
        ],
    )