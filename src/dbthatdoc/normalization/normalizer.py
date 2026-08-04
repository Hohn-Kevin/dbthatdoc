from __future__ import annotations

from dbthatdoc.models import (
    DocumentContent,
    DocumentPage,
    ExtractedElement,
    ExtractionResult,
    TextBlock,
    TextPosition,
)


def _has_position(element: ExtractedElement) -> bool:
    return (
        element.x0 is not None
        and element.y0 is not None
        and element.x1 is not None
        and element.y1 is not None
    )


def _vertical_center(element: ExtractedElement) -> float:
    assert element.y0 is not None
    assert element.y1 is not None
    return (element.y0 + element.y1) / 2


def _height(element: ExtractedElement) -> float:
    assert element.y0 is not None
    assert element.y1 is not None
    return element.y1 - element.y0


def _group_elements_by_line(
    elements: list[ExtractedElement],
) -> list[list[ExtractedElement]]:
    positioned_elements = [
        element for element in elements
        if element.text.strip() and _has_position(element)
    ]

    sorted_elements = sorted(
        positioned_elements,
        key=lambda element: (
            _vertical_center(element),
            element.x0 if element.x0 is not None else 0,
        ),
    )

    lines: list[list[ExtractedElement]] = []

    for element in sorted_elements:
        if not lines:
            lines.append([element])
            continue

        current_line = lines[-1]
        line_center = sum(
            _vertical_center(line_element)
            for line_element in current_line
        ) / len(current_line)
        line_height = max(
            _height(line_element)
            for line_element in current_line
        )
        threshold = max(2.0, max(line_height, _height(element)) * 0.75)

        if abs(_vertical_center(element) - line_center) <= threshold:
            current_line.append(element)
        else:
            lines.append([element])

    return [
        sorted(
            line,
            key=lambda element: (
                element.x0 if element.x0 is not None else 0
            ),
        )
        for line in lines
    ]


def _line_to_text_block(
    line: list[ExtractedElement],
    page_number: int,
    source: str,
) -> TextBlock:
    x0_values = [element.x0 for element in line if element.x0 is not None]
    y0_values = [element.y0 for element in line if element.y0 is not None]
    x1_values = [element.x1 for element in line if element.x1 is not None]
    y1_values = [element.y1 for element in line if element.y1 is not None]
    confidences = [
        element.confidence
        for element in line
        if element.confidence is not None
    ]

    return TextBlock(
        text=" ".join(element.text for element in line),
        page_number=page_number,
        source=source,
        confidence=(
            sum(confidences) / len(confidences)
            if confidences
            else None
        ),
        position=TextPosition(
            x0=min(x0_values),
            y0=min(y0_values),
            x1=max(x1_values),
            y1=max(y1_values),
        ),
    )


def normalize_extraction(
    result: ExtractionResult,
) -> DocumentContent:
    pages: list[DocumentPage] = []

    for page in result.pages:
        blocks: list[TextBlock] = [
            _line_to_text_block(
                line=line,
                page_number=page.page_number,
                source=result.processing.extractor,
            )
            for line in _group_elements_by_line(page.elements)
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
