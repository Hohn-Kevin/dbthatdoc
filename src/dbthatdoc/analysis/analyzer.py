from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from dbthatdoc.models import (
    AnalysisCandidate,
    AnalysisEntity,
    AnalysisEvidence,
    AnalysisResult,
    AnalyzerInfo,
    DocumentContent,
    DocumentPage,
    TextBlock,
    TextPosition,
)

from dbthatdoc.analysis.german import GermanEntityAnalyzer


_MAX_LABEL_WORDS = 7


class Analyzer(Protocol):
    name: str
    version: str

    def analyze(
        self,
        content: DocumentContent,
    ) -> list[AnalysisCandidate]: ...


class EntityAnalyzer(Protocol):
    name: str
    version: str

    def analyze(
        self,
        content: DocumentContent,
        candidates: Sequence[AnalysisCandidate],
    ) -> list[AnalysisEntity]: ...


class KeyValueAnalyzer:
    name = "key_value"
    version = "1.0"

    def analyze(
        self,
        content: DocumentContent,
    ) -> list[AnalysisCandidate]:
        candidates: list[AnalysisCandidate] = []

        for page in content.pages:
            for block_index, block in enumerate(page.blocks):
                inline_candidate = _inline_candidate(
                    block,
                    block_index,
                )

                if inline_candidate is not None:
                    candidates.append(inline_candidate)
                    continue

                label = block.text.strip()

                if (
                    not label.endswith(":")
                    or not _is_candidate_label(label[:-1])
                ):
                    continue

                value_match = _nearest_spatial_value(
                    page,
                    block_index,
                )

                if value_match is None:
                    continue

                value_index, value_block, relation = value_match
                candidates.append(
                    AnalysisCandidate(
                        label=label[:-1].strip(),
                        value=value_block.text.strip(),
                        relation=relation,
                        confidence=_average_confidence(
                            [block, value_block]
                        ),
                        evidence=[
                            _evidence(block, block_index),
                            _evidence(value_block, value_index),
                        ],
                    )
                )

        return candidates


def analyze_content(
    content: DocumentContent,
    analyzers: Sequence[Analyzer] | None = None,
    entity_analyzers: Sequence[EntityAnalyzer] | None = None,
) -> AnalysisResult:
    selected_analyzers = (
        list(analyzers)
        if analyzers is not None
        else [KeyValueAnalyzer()]
    )
    selected_entity_analyzers = (
        list(entity_analyzers)
        if entity_analyzers is not None
        else [GermanEntityAnalyzer()]
    )
    candidates: list[AnalysisCandidate] = []
    entities: list[AnalysisEntity] = []

    for analyzer in selected_analyzers:
        candidates.extend(analyzer.analyze(content))

    for analyzer in selected_entity_analyzers:
        entities.extend(analyzer.analyze(content, candidates))

    candidates = _attach_entities(candidates, entities)
    all_analyzers = [
        *selected_analyzers,
        *selected_entity_analyzers,
    ]

    return AnalysisResult(
        source_file=content.source_file,
        candidates=candidates,
        entities=entities,
        analyzers=[
            AnalyzerInfo(
                name=analyzer.name,
                version=analyzer.version,
            )
            for analyzer in all_analyzers
        ],
        warnings=_validation_warnings(entities),
    )


def _inline_candidate(
    block: TextBlock,
    block_index: int,
) -> AnalysisCandidate | None:
    separator_index = next(
        (
            index
            for index, character in enumerate(block.text)
            if (
                character == ":"
                and block.text[index + 1:index + 2] != "/"
            )
        ),
        None,
    )

    if separator_index is None:
        return None

    label = block.text[:separator_index].strip()
    value = block.text[separator_index + 1:].strip()

    if (
        not _is_candidate_label(label)
        or not value
        or not any(character.isalnum() for character in value)
    ):
        return None

    return AnalysisCandidate(
        label=label,
        value=value,
        relation="inline",
        confidence=block.confidence,
        evidence=[_evidence(block, block_index)],
    )


def _nearest_spatial_value(
    page: DocumentPage,
    label_index: int,
) -> tuple[int, TextBlock, str] | None:
    label_block = page.blocks[label_index]
    label_position = label_block.position

    if label_position is None:
        return None

    right_matches: list[tuple[float, int, TextBlock]] = []
    below_matches: list[tuple[float, int, TextBlock]] = []

    for value_index, value_block in enumerate(page.blocks):
        if value_index == label_index or value_block.position is None:
            continue

        value_text = value_block.text.strip()

        if (
            not value_text
            or value_text.endswith(":")
            or not any(character.isalnum() for character in value_text)
        ):
            continue

        if _is_right_value(
            label_position,
            value_block.position,
            page.width,
        ):
            right_matches.append((
                _horizontal_gap(label_position, value_block.position),
                value_index,
                value_block,
            ))
            continue

        if _is_below_value(
            label_position,
            value_block.position,
        ):
            below_matches.append((
                _vertical_gap(label_position, value_block.position),
                value_index,
                value_block,
            ))

    if right_matches:
        _, value_index, value_block = min(
            right_matches,
            key=lambda match: match[0],
        )
        return value_index, value_block, "right"

    if below_matches:
        _, value_index, value_block = min(
            below_matches,
            key=lambda match: match[0],
        )
        return value_index, value_block, "below"

    return None


def _is_right_value(
    label: TextPosition,
    value: TextPosition,
    page_width: float | None,
) -> bool:
    if None in (
        label.x0,
        label.y0,
        label.x1,
        label.y1,
        value.x0,
        value.y0,
        value.x1,
        value.y1,
    ):
        return False

    assert label.x0 is not None
    assert label.y0 is not None
    assert label.x1 is not None
    assert label.y1 is not None
    assert value.x0 is not None
    assert value.y0 is not None
    assert value.x1 is not None
    assert value.y1 is not None

    overlap = max(
        0.0,
        min(label.y1, value.y1) - max(label.y0, value.y0),
    )
    minimum_height = min(
        label.y1 - label.y0,
        value.y1 - value.y0,
    )

    if minimum_height <= 0:
        return False

    maximum_gap = max(
        (page_width or 0.0) * 0.25,
        (label.y1 - label.y0) * 10.0,
    )

    return (
        value.x0 >= label.x1
        and overlap / minimum_height >= 0.50
        and _horizontal_gap(label, value) <= maximum_gap
    )


def _is_below_value(
    label: TextPosition,
    value: TextPosition,
) -> bool:
    if None in (
        label.x0,
        label.y0,
        label.x1,
        label.y1,
        value.x0,
        value.y0,
        value.x1,
        value.y1,
    ):
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

    maximum_gap = label_height
    horizontal_overlap = max(
        0.0,
        min(label.x1, value.x1) - max(label.x0, value.x0),
    )
    starts_near_label = abs(value.x0 - label.x0) <= label_height * 2.0

    return (
        value.y0 >= label.y1
        and _vertical_gap(label, value) <= maximum_gap
        and (horizontal_overlap > 0 or starts_near_label)
    )


def _horizontal_gap(
    label: TextPosition,
    value: TextPosition,
) -> float:
    assert label.x1 is not None
    assert value.x0 is not None
    return value.x0 - label.x1


def _vertical_gap(
    label: TextPosition,
    value: TextPosition,
) -> float:
    assert label.y1 is not None
    assert value.y0 is not None
    return value.y0 - label.y1


def _is_candidate_label(text: str) -> bool:
    label = text.strip()
    return (
        bool(label)
        and any(character.isalnum() for character in label)
        # Labels identify values; sentence-length prose is not a stable key.
        and len(label.split()) <= _MAX_LABEL_WORDS
    )


def _evidence(
    block: TextBlock,
    block_index: int,
) -> AnalysisEvidence:
    return AnalysisEvidence(
        page_number=block.page_number,
        block_index=block_index,
        text=block.text,
        source=block.source,
        confidence=block.confidence,
        position=block.position,
    )


def _average_confidence(
    blocks: list[TextBlock],
) -> float | None:
    confidences = [
        block.confidence
        for block in blocks
        if block.confidence is not None
    ]

    if not confidences:
        return None

    return sum(confidences) / len(confidences)


def _attach_entities(
    candidates: list[AnalysisCandidate],
    entities: list[AnalysisEntity],
) -> list[AnalysisCandidate]:
    entity_ids_by_block: dict[tuple[int, int], list[str]] = {}

    for entity in entities:
        for evidence in entity.evidence:
            key = (evidence.page_number, evidence.block_index)
            entity_ids_by_block.setdefault(key, []).append(entity.id)

    enriched: list[AnalysisCandidate] = []

    for candidate in candidates:
        entity_ids: list[str] = []

        for evidence in candidate.evidence:
            key = (evidence.page_number, evidence.block_index)
            for entity_id in entity_ids_by_block.get(key, []):
                if entity_id not in entity_ids:
                    entity_ids.append(entity_id)

        enriched.append(candidate.model_copy(
            update={"entity_ids": entity_ids}
        ))

    return enriched


def _validation_warnings(
    entities: list[AnalysisEntity],
) -> list[str]:
    return [
        (
            f"Invalid {entity.kind} candidate at page "
            f"{entity.evidence[0].page_number}, block "
            f"{entity.evidence[0].block_index}."
        )
        for entity in entities
        if entity.validation_status == "invalid"
    ]
