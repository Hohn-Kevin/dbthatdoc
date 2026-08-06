from __future__ import annotations

from dataclasses import dataclass

from dbthatdoc.models import TextPosition


@dataclass(frozen=True)
class LayoutConfig:
    minimum_vertical_overlap_ratio: float = 0.5
    maximum_right_gap_line_heights: float = 6.0
    maximum_fragment_gap_line_heights: float = 1.5
    maximum_below_gap_line_heights: float = 1.0
    maximum_below_start_offset_line_heights: float = 2.0


def is_right_neighbor(
    left: TextPosition,
    right: TextPosition,
    config: LayoutConfig,
) -> bool:
    if not _has_box(left) or not _has_box(right):
        return False

    assert left.y0 is not None
    assert left.y1 is not None
    assert left.x1 is not None
    assert right.y0 is not None
    assert right.y1 is not None
    assert right.x0 is not None

    left_height = left.y1 - left.y0
    right_height = right.y1 - right.y0
    minimum_height = min(left_height, right_height)

    if minimum_height <= 0 or left_height <= 0:
        return False

    overlap = max(
        0.0,
        min(left.y1, right.y1) - max(left.y0, right.y0),
    )
    gap = right.x0 - left.x1
    return (
        gap >= 0
        and gap <= left_height * config.maximum_right_gap_line_heights
        and overlap / minimum_height
        >= config.minimum_vertical_overlap_ratio
    )


def is_below_neighbor(
    label: TextPosition,
    value: TextPosition,
    config: LayoutConfig,
) -> bool:
    if not _has_box(label) or not _has_box(value):
        return False

    assert label.x0 is not None
    assert label.y0 is not None
    assert label.x1 is not None
    assert label.y1 is not None
    assert value.x0 is not None
    assert value.y0 is not None
    assert value.x1 is not None
    assert value.y1 is not None

    label_height = label.y1 - label.y0

    if label_height <= 0 or value.y1 <= value.y0:
        return False

    horizontal_overlap = max(
        0.0,
        min(label.x1, value.x1) - max(label.x0, value.x0),
    )
    starts_near_label = (
        abs(value.x0 - label.x0)
        <= label_height * config.maximum_below_start_offset_line_heights
    )
    return (
        value.y0 >= label.y1
        and value.y0 - label.y1
        <= label_height * config.maximum_below_gap_line_heights
        and (horizontal_overlap > 0 or starts_near_label)
    )


def _has_box(position: TextPosition) -> bool:
    return None not in (
        position.x0,
        position.y0,
        position.x1,
        position.y1,
    )
