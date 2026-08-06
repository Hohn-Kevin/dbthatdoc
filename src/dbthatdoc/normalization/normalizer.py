from __future__ import annotations

from math import isfinite

from dbthatdoc.models import (
    DocumentContent,
    DocumentPage,
    ExtractedElement,
    ExtractionResult,
    TextBlock,
    TextPosition,
)


_POSITIONED_TEXT_ELEMENT_TYPES = {"word", "form_field"}


def _has_position(element: ExtractedElement) -> bool:
    return (
        element.x0 is not None
        and element.y0 is not None
        and element.x1 is not None
        and element.y1 is not None
    )


def _has_no_position(element: ExtractedElement) -> bool:
    return (
        element.x0 is None
        and element.y0 is None
        and element.x1 is None
        and element.y1 is None
    )


def _usable_page_dimension(value: float | None) -> float | None:
    if value is None or not isfinite(value) or value <= 0:
        return None

    return value


def _has_plausible_position(element: ExtractedElement) -> bool:
    if not _has_position(element):
        return False

    assert element.x0 is not None
    assert element.y0 is not None
    assert element.x1 is not None
    assert element.y1 is not None

    coordinates = (element.x0, element.y0, element.x1, element.y1)

    return (
        all(isfinite(coordinate) for coordinate in coordinates)
        and element.x1 > element.x0
        and element.y1 > element.y0
    )


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


def _median(values: list[float]) -> float | None:
    if not values:
        return None

    sorted_values = sorted(values)
    middle_index = len(sorted_values) // 2

    if len(sorted_values) % 2 == 1:
        return sorted_values[middle_index]

    return (
        sorted_values[middle_index - 1]
        + sorted_values[middle_index]
    ) / 2


def _is_geometric_noise(
    element: ExtractedElement,
    page_width: float | None,
    page_height: float | None,
    typical_word_width: float | None,
    typical_word_height: float | None,
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
    is_low_edge_confidence = (
        element.confidence is not None
        and element.confidence <= 0.50
    )
    is_non_alphanumeric = not any(
        character.isalnum() for character in text
    )
    is_narrow_edge_mark = _width(element) <= max(
        3.0,
        typical_word_width * 0.10
        if typical_word_width is not None
        else 0.0,
    )
    is_edge_speck = (
        typical_word_width is not None
        and typical_word_height is not None
        and _width(element) <= max(3.0, typical_word_width * 0.25)
        and _height(element) <= max(3.0, typical_word_height * 0.50)
    )
    non_whitespace_character_count = sum(
        not character.isspace() for character in text
    )
    is_sparse_wide_mark = (
        non_whitespace_character_count > 0
        and typical_word_height is not None
        and page_width is not None
        and _width(element) >= page_width * 0.50
        and _height(element) <= typical_word_height * 1.50
        and (
            _width(element)
            / (_height(element) * non_whitespace_character_count)
            >= 8.0
        )
    )
    edge_padding_x = (
        max(3.0, page_width * 0.005)
        if page_width is not None
        else 3.0
    )
    edge_padding_y = (
        max(3.0, page_height * 0.005)
        if page_height is not None
        else 3.0
    )
    is_near_page_edge = (
        element.x0 <= edge_padding_x
        or element.y0 <= edge_padding_y
        or (
            page_width is not None
            and element.x1 >= page_width - edge_padding_x
        )
        or (
            page_height is not None
            and element.y1 >= page_height - edge_padding_y
        )
    )

    if is_low_edge_confidence and is_edge_speck and is_near_page_edge:
        return True

    if is_low_edge_confidence and is_sparse_wide_mark:
        return True

    return (
        is_non_alphanumeric
        and is_narrow_edge_mark
        and is_low_confidence
        and is_near_page_edge
    )


def _group_elements_by_line(
    elements: list[ExtractedElement],
    page_width: float | None = None,
    page_height: float | None = None,
) -> list[list[ExtractedElement]]:
    usable_page_width = _usable_page_dimension(page_width)
    usable_page_height = _usable_page_dimension(page_height)
    plausible_elements = [
        element
        for element in elements
        if (
            element.element_type in _POSITIONED_TEXT_ELEMENT_TYPES
            and element.text.strip()
            and _has_plausible_position(element)
        )
    ]
    typical_word_width = _median([
        _width(element) for element in plausible_elements
    ])
    typical_word_height = _median([
        _height(element) for element in plausible_elements
    ])

    positioned_elements = [
        element
        for element in plausible_elements
        if (
            not _is_geometric_noise(
                element,
                usable_page_width,
                usable_page_height,
                typical_word_width,
                typical_word_height,
            )
        )
    ]

    sorted_elements = sorted(
        positioned_elements,
        key=lambda element: (
            element.y0 if element.y0 is not None else 0,
            element.x0 if element.x0 is not None else 0,
        ),
    )

    lines: list[list[ExtractedElement]] = []

    for element in sorted_elements:
        matching_lines: list[
            tuple[float, list[ExtractedElement]]
        ] = []

        for line in lines:
            line_y0 = _median([
                line_element.y0
                for line_element in line
                if line_element.y0 is not None
            ])
            line_y1 = _median([
                line_element.y1
                for line_element in line
                if line_element.y1 is not None
            ])
            line_center = _median([
                _vertical_center(line_element)
                for line_element in line
            ])
            line_height = _median([
                _height(line_element)
                for line_element in line
            ])

            assert line_y0 is not None
            assert line_y1 is not None
            assert line_center is not None
            assert line_height is not None
            assert element.y0 is not None
            assert element.y1 is not None

            overlap = max(
                0.0,
                min(line_y1, element.y1)
                - max(line_y0, element.y0),
            )
            overlap_ratio = overlap / min(
                line_height,
                _height(element),
            )
            center_distance = abs(
                _vertical_center(element) - line_center
            )
            baseline_distance = abs(element.y1 - line_y1)
            reference_height = typical_word_height or min(
                line_height,
                _height(element),
            )
            line_is_oversized = (
                line_height > reference_height * 3.0
            )
            element_is_oversized = (
                _height(element) > reference_height * 3.0
            )

            # Extreme height outliers must not bridge adjacent text rows.
            if line_is_oversized != element_is_oversized:
                continue

            if line_is_oversized:
                belongs_to_line = (
                    overlap_ratio >= 0.50
                    and center_distance
                    <= max(line_height, _height(element)) * 0.50
                )
            else:
                belongs_to_line = (
                    (
                        overlap_ratio >= 0.50
                        and center_distance
                        <= max(2.0, reference_height * 0.85)
                    )
                    or baseline_distance
                    <= max(2.0, reference_height * 0.35)
                )

            if belongs_to_line:
                matching_lines.append((center_distance, line))

        if not matching_lines:
            lines.append([element])
            continue

        _, best_line = min(
            matching_lines,
            key=lambda match: match[0],
        )
        best_line.append(element)

    sorted_lines = sorted(
        [
            sorted(
                line,
                key=lambda element: (
                    element.x0 if element.x0 is not None else 0
                ),
            )
            for line in lines
        ],
        key=lambda line: _median([
            _vertical_center(element) for element in line
        ]) or 0.0,
    )
    horizontal_gap_threshold = max(
        usable_page_width * 0.03
        if usable_page_width is not None
        else 0.0,
        typical_word_height * 2.0
        if typical_word_height is not None
        else 0.0,
        3.0,
    )
    text_runs: list[list[ExtractedElement]] = []

    for line in sorted_lines:
        current_run = [line[0]]

        for element in line[1:]:
            previous_element = current_run[-1]
            assert previous_element.x1 is not None
            assert element.x0 is not None

            if (
                element.element_type != previous_element.element_type
                or element.element_type == "form_field"
                or previous_element.element_type == "form_field"
                or element.x0 - previous_element.x1
                > horizontal_gap_threshold
            ):
                text_runs.append(current_run)
                current_run = [element]
            else:
                current_run.append(element)

        text_runs.append(current_run)

    return text_runs


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


def _unpositioned_elements_to_text_block(
    elements: list[ExtractedElement],
    page_number: int,
    source: str,
) -> TextBlock | None:
    unpositioned_words = [
        element
        for element in elements
        if (
            element.element_type in _POSITIONED_TEXT_ELEMENT_TYPES
            and element.text.strip()
            and _has_no_position(element)
        )
    ]

    if not unpositioned_words:
        return None

    confidences = [
        element.confidence
        for element in unpositioned_words
        if element.confidence is not None
    ]

    return TextBlock(
        text=" ".join(
            element.text for element in unpositioned_words
        ),
        page_number=page_number,
        source=source,
        confidence=(
            sum(confidences) / len(confidences)
            if confidences
            else None
        ),
        position=None,
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
        unpositioned_block = _unpositioned_elements_to_text_block(
            page.elements,
            page.page_number,
            result.processing.extractor,
        )

        if unpositioned_block is not None:
            blocks.append(unpositioned_block)

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

    normalized_full_text = "\n\n".join(
        "\n".join(block.text for block in page.blocks)
        for page in pages
    ).strip()

    return DocumentContent(
        source_file=result.source.filename,
        pages=pages,
        full_text=normalized_full_text,
        extraction_methods=[
            result.processing.extractor
        ],
    )
