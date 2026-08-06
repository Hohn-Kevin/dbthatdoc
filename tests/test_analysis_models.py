import pytest
from pydantic import ValidationError

from dbthatdoc.models import AnalysisCandidate, AnalysisEvidence


def _evidence(
    *,
    start_offset: int | None = None,
    end_offset: int | None = None,
) -> AnalysisEvidence:
    return AnalysisEvidence(
        page_number=1,
        block_index=0,
        text="Label: Value",
        source="test",
        start_offset=start_offset,
        end_offset=end_offset,
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (None, 5),
        (5, None),
        (5, 5),
        (8, 7),
        (0, 13),
    ],
)
def test_analysis_evidence_rejects_invalid_offsets(
    start: int | None,
    end: int | None,
) -> None:
    with pytest.raises(ValidationError):
        _evidence(start_offset=start, end_offset=end)


def test_analysis_candidate_accepts_block_relative_offsets() -> None:
    candidate = AnalysisCandidate(
        label="Label",
        value="Value",
        relation="inline",
        candidate_type="colon_structure",
        source_confidence=0.9,
        evidence=[_evidence(start_offset=0, end_offset=12)],
        label_start_offset=0,
        label_end_offset=5,
        value_start_offset=7,
        value_end_offset=12,
    )

    assert candidate.source_confidence == 0.9


@pytest.mark.parametrize(
    ("label_start", "label_end", "value_start", "value_end"),
    [
        (0, 5, 4, 12),
        (0, 13, 7, 12),
        (0, 5, 7, 13),
        (0, None, 7, 12),
    ],
)
def test_analysis_candidate_rejects_invalid_offsets(
    label_start: int | None,
    label_end: int | None,
    value_start: int | None,
    value_end: int | None,
) -> None:
    with pytest.raises(ValidationError):
        AnalysisCandidate(
            label="Label",
            value="Value",
            relation="inline",
            candidate_type="colon_structure",
            evidence=[_evidence(start_offset=0, end_offset=12)],
            label_start_offset=label_start,
            label_end_offset=label_end,
            value_start_offset=value_start,
            value_end_offset=value_end,
        )
