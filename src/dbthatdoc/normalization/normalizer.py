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


def _has_plausible_position(element: ExtractedElement) -> bool:
    if not _has_position(element):
        return False

    assert element.x0 is not None
    assert element.y0 is not None
    assert element.x1 is not None
    assert element.y1 is not None

    return element.x1 > element.x0 and element.y1 > element.y0


def _vertical_center(element: ExtractedElement) -> float:
    assert element.y0 is not None
    assert element.y1 is not None
    return (element.y0 + element.y1) / 2


def _width(element: ExtractedElement) -> float:
    assert element.x0 is not None
    assert element.x1 is not None
    return element.x1 - element.x0


def _height(element: ExtractedElement) -> float:
    assert element.y0 is not None
    assert element.y1 is not None
    return element.y1 - element.y0


def _is_margin_noise(
    element: ExtractedElement,
    page_width: float | None,
    page_height: float | None,
) -> bool:
    text = element.text.strip()

    if not _has_plausible_position(element):
        return True

    assert element.x0 is not None
    assert element.y0 is not None
    assert element.x1 is not None
    assert element.y1 is not None

    if page_width is not None and (
        element.x1 <= 0 or element.x0 >= page_width
    ):
        return True

    if page_height is not None and (
        element.y1 <= 0 or element.y0 >= page_height
    ):
        return True

    is_low_confidence = (
        element.confidence is not None
        and element.confidence <= 0.10
    )
    is_short_symbol = len(text) <= 2 and not any(
        character.isalnum() for character in text
    )
    is_tiny = _width(element) <= 3.0 or _height(element) <= 3.0
    is_near_page_edge = (
        element.x0 <= 3.0
        or element.y0 <= 3.0
        or (
            page_width is not None
            and element.x1 >= page_width - 3.0
        )
        or (
            page_height is not None
            and element.y1 >= page_height - 3.0
        )
    )

    return is_short_symbol and (
        is_tiny or (is_low_confidence and is_near_page_edge)
    )


def _group_elements_by_line(
    elements: list[ExtractedElement],
    page_width: float | None = None,
    page_height: float | None = None,
) -> list[list[ExtractedElement]]:
    positioned_elements = [
        element
        for element in elements
        if (
            element.text.strip()
            and _has_plausible_position(element)
            and not _is_margin_noise(element, page_width, page_height)
        )
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
            for line in _group_elements_by_line(
                page.elements,
                page.width,
                page.height,
            )
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
