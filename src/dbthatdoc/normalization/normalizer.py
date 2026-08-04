from __future__ import annotations

from dbthatdoc.models import (
    DocumentContent,
    DocumentPage,
    ExtractionResult,
    TextBlock,
    TextPosition,
)


def normalize_extraction(
    result: ExtractionResult,
) -> DocumentContent:
    pages: list[DocumentPage] = []

    for page in result.pages:
        blocks: list[TextBlock] = [
            TextBlock(
                text=element.text,
                page_number=page.page_number,
                source=result.processing.extractor,
                confidence=element.confidence,
                position=TextPosition(
                    x0=element.x0,
                    y0=element.y0,
                    x1=element.x1,
                    y1=element.y1,
                ),
            )
            for element in page.elements
        ]

        if not blocks and page.text.strip():
            blocks = [
                TextBlock(
                    text=page.text,
                    page_number=page.page_number,
                    source=result.processing.extractor,
                    confidence=None,
                    position=None,
                )
            ]

        pages.append(
            DocumentPage(
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                blocks=blocks,
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
