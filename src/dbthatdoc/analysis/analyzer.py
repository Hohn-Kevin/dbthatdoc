from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
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
from dbthatdoc.analysis.layout import (
    LayoutConfig,
    is_below_neighbor,
    is_right_neighbor,
)


@dataclass(frozen=True)
class KeyValueConfig:
    preferred_maximum_label_words: int = 7
    maximum_label_words: int = 16
    minimum_label_score: int = 5
    layout: LayoutConfig = field(default_factory=LayoutConfig)


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
    version = "1.1"

    def __init__(self, config: KeyValueConfig | None = None) -> None:
        self.config = config or KeyValueConfig()

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
                    self.config,
                )

                if inline_candidate is not None:
                    candidates.append(inline_candidate)
                    continue

                label = block.text.strip()

                if (
                    not label.endswith(":")
                    or not label[:-1].strip()
                ):
                    continue

                value_match = _nearest_spatial_value(
                    page,
                    block_index,
                    self.config.layout,
                )

                if value_match is None:
                    continue

                value_index, value_block, relation = value_match
                if not _is_candidate_label(
                    label[:-1],
                    value_block.text,
                    self.config,
                ):
                    continue
                candidates.append(
                    AnalysisCandidate(
                        label=label[:-1].strip(),
                        value=value_block.text.strip(),
                        relation=relation,
                        confidence=_average_confidence(
                            [block, value_block]
                        ),
                        evidence=[
                            _evidence(
                                block,
                                block_index,
                                0,
                                len(block.text),
                            ),
                            _evidence(
                                value_block,
                                value_index,
                                0,
                                len(value_block.text),
                            ),
                        ],
                        label_start_offset=0,
                        label_end_offset=len(label) - 1,
                        value_start_offset=0,
                        value_end_offset=len(value_block.text),
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
    config: KeyValueConfig,
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

    raw_label = block.text[:separator_index]
    raw_value = block.text[separator_index + 1:]
    label = raw_label.strip()
    value = raw_value.strip()
    label_start = len(raw_label) - len(raw_label.lstrip())
    label_end = len(raw_label.rstrip())
    value_start = (
        separator_index
        + 1
        + len(raw_value)
        - len(raw_value.lstrip())
    )
    value_end = len(block.text.rstrip())

    if (
        not _is_candidate_label(label, value, config)
        or not value
        or not any(character.isalnum() for character in value)
    ):
        return None

    return AnalysisCandidate(
        label=label,
        value=value,
        relation="inline",
        confidence=block.confidence,
        evidence=[
            _evidence(
                block,
                block_index,
                label_start,
                value_end,
            )
        ],
        label_start_offset=label_start,
        label_end_offset=label_end,
        value_start_offset=value_start,
        value_end_offset=value_end,
    )


def _nearest_spatial_value(
    page: DocumentPage,
    label_index: int,
    layout: LayoutConfig,
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

        if is_right_neighbor(
            label_position,
            value_block.position,
            layout,
        ):
            right_matches.append((
                _horizontal_gap(label_position, value_block.position),
                value_index,
                value_block,
            ))
            continue

        if is_below_neighbor(
            label_position,
            value_block.position,
            layout,
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


def _is_candidate_label(
    text: str,
    value: str,
    config: KeyValueConfig,
) -> bool:
    label = text.strip()

    if not label or not any(character.isalnum() for character in label):
        return False

    word_count = len(label.split())
    score = 2
    score += 1 if word_count <= config.preferred_maximum_label_words else 0
    score += 1 if len(label) <= 80 else 0
    score += 1 if not any(mark in label for mark in ",;!?") else 0
    score += 1 if any(character.isdigit() for character in value) else 0

    if word_count > config.maximum_label_words:
        score -= 3
    if (
        word_count > config.preferred_maximum_label_words
        and len(value.split()) > 3
    ):
        score -= 2

    return score >= config.minimum_label_score


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


def _evidence(
    block: TextBlock,
    block_index: int,
    start_offset: int | None = None,
    end_offset: int | None = None,
) -> AnalysisEvidence:
    return AnalysisEvidence(
        page_number=block.page_number,
        block_index=block_index,
        text=block.text,
        source=block.source,
        confidence=block.confidence,
        position=block.position,
        start_offset=start_offset,
        end_offset=end_offset,
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
    entities_by_block: dict[
        tuple[int, int],
        list[tuple[str, AnalysisEvidence]],
    ] = {}

    for entity in entities:
        for evidence in entity.evidence:
            key = (evidence.page_number, evidence.block_index)
            entities_by_block.setdefault(key, []).append((
                entity.id,
                evidence,
            ))

    enriched: list[AnalysisCandidate] = []

    for candidate in candidates:
        value_evidence = (
            candidate.evidence[0]
            if candidate.relation == "inline"
            else candidate.evidence[-1]
        )
        key = (
            value_evidence.page_number,
            value_evidence.block_index,
        )
        overlapping_ids = {
            entity_id
            for entity_id, entity_evidence in entities_by_block.get(key, [])
            if _evidence_overlaps_candidate_value(
                candidate,
                entity_evidence,
            )
        }
        entity_ids = (
            list(overlapping_ids)
            if len(overlapping_ids) == 1
            else []
        )

        enriched.append(candidate.model_copy(
            update={"entity_ids": entity_ids}
        ))

    return enriched


def _evidence_overlaps_candidate_value(
    candidate: AnalysisCandidate,
    evidence: AnalysisEvidence,
) -> bool:
    if (
        candidate.value_start_offset is None
        or candidate.value_end_offset is None
        or evidence.start_offset is None
        or evidence.end_offset is None
    ):
        return False

    return (
        evidence.start_offset < candidate.value_end_offset
        and evidence.end_offset > candidate.value_start_offset
    )


def _validation_warnings(
    entities: list[AnalysisEntity],
) -> list[str]:
    return [
        (
            f"{_recognition_warning_label(entity.recognition_status)} "
            f"{entity.kind} at page "
            f"{entity.evidence[0].page_number}, block "
            f"{entity.evidence[0].block_index}."
        )
        for entity in entities
        if entity.validation_status == "invalid"
    ]


def _recognition_warning_label(status: str) -> str:
    if status == "suspected_ocr_corruption":
        return "Suspected OCR corruption in"
    return "Recognized invalid"
