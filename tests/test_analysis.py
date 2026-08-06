from pathlib import Path

from dbthatdoc.analysis import analyze_content
from dbthatdoc.models import (
    AnalysisCandidate,
    DocumentContent,
    DocumentPage,
    TextBlock,
    TextPosition,
)
from dbthatdoc.pipeline import analyze_file


SAMPLES_DIR = Path(__file__).parent.parent / "samples"


def _block(
    text: str,
    x0: float | None,
    y0: float | None,
    x1: float | None,
    y1: float | None,
    confidence: float | None = 0.8,
) -> TextBlock:
    position = None

    if None not in (x0, y0, x1, y1):
        position = TextPosition(
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
        )

    return TextBlock(
        text=text,
        page_number=1,
        source="test-source",
        confidence=confidence,
        position=position,
    )


def _content(blocks: list[TextBlock]) -> DocumentContent:
    return DocumentContent(
        source_file="analysis.pdf",
        pages=[
            DocumentPage(
                page_number=1,
                width=200.0,
                height=100.0,
                blocks=blocks,
            ),
        ],
        full_text="\n".join(block.text for block in blocks),
        extraction_methods=["test-source"],
    )


def test_analysis_extracts_inline_key_value_candidate() -> None:
    content = _content([
        _block("Label: Value", 10.0, 10.0, 80.0, 20.0),
    ])

    result = analyze_content(content)

    assert result.source_file == "analysis.pdf"
    assert len(result.candidates) == 1
    assert result.analyzers[0].name == "key_value"
    assert result.analyzers[0].version == "1.1"

    candidate = result.candidates[0]

    assert candidate.kind == "key_value"
    assert candidate.label == "Label"
    assert candidate.value == "Value"
    assert candidate.relation == "inline"
    assert candidate.confidence == 0.8
    assert len(candidate.evidence) == 1
    assert candidate.evidence[0].page_number == 1
    assert candidate.evidence[0].block_index == 0
    assert candidate.evidence[0].text == "Label: Value"
    assert candidate.evidence[0].position is not None


def test_analysis_matches_nearest_value_to_the_right() -> None:
    content = _content([
        _block("Label:", 10.0, 10.0, 50.0, 20.0, 0.8),
        _block("Value", 90.0, 10.0, 125.0, 20.0, 0.6),
        _block("Far value", 150.0, 10.0, 195.0, 20.0, 0.9),
    ])

    result = analyze_content(content)

    assert len(result.candidates) == 1

    candidate = result.candidates[0]

    assert candidate.label == "Label"
    assert candidate.value == "Value"
    assert candidate.relation == "right"
    assert candidate.confidence == 0.7
    assert [
        evidence.block_index for evidence in candidate.evidence
    ] == [0, 1]


def test_analysis_matches_value_below_label() -> None:
    content = _content([
        _block("Label:", 10.0, 10.0, 50.0, 20.0),
        _block("Value below", 10.0, 30.0, 75.0, 40.0),
    ])

    result = analyze_content(content)

    assert len(result.candidates) == 1
    assert result.candidates[0].relation == "below"
    assert result.candidates[0].value == "Value below"


def test_analysis_ignores_distant_or_invalid_spatial_values() -> None:
    content = _content([
        _block("First:", 10.0, 10.0, 45.0, 20.0),
        _block("Distant", 160.0, 80.0, 195.0, 90.0),
        TextBlock(
            text="Second:",
            page_number=1,
            source="test-source",
            confidence=0.8,
            position=TextPosition(
                x0=10.0,
                y0=50.0,
                x1=10.0,
                y1=50.0,
            ),
        ),
    ])

    result = analyze_content(content)

    assert result.candidates == []


def test_analysis_supports_unpositioned_inline_evidence() -> None:
    content = _content([
        _block("Label: Value", None, None, None, None, None),
    ])

    result = analyze_content(content)

    assert len(result.candidates) == 1
    assert result.candidates[0].confidence is None
    assert result.candidates[0].evidence[0].position is None


def test_analysis_ignores_sentence_length_labels() -> None:
    content = _content([
        _block(
            "This is ordinary prose with many words before: more prose",
            10.0,
            10.0,
            190.0,
            20.0,
        ),
    ])

    result = analyze_content(content)

    assert result.candidates == []


def test_analysis_accepts_long_structured_label_with_numeric_value() -> None:
    content = _content([_block(
        "Datum der letzten verbindlichen schriftlichen Mitteilung an den Kunden: 01.02.2026",
        10.0,
        10.0,
        190.0,
        20.0,
    )])

    result = analyze_content(content)

    assert len(result.candidates) == 1
    assert result.candidates[0].value == "01.02.2026"


def test_analysis_does_not_bridge_a_wide_column_gap() -> None:
    content = _content([
        _block("Referenz:", 10.0, 10.0, 40.0, 20.0),
        _block("12345", 101.0, 10.0, 130.0, 20.0),
    ])
    content.pages[0].width = 1000.0

    result = analyze_content(content)

    assert result.candidates == []


def test_analysis_does_not_treat_uri_schemes_as_labels() -> None:
    content = _content([
        _block(
            "Resource https://example.test/path",
            10.0,
            10.0,
            150.0,
            20.0,
        ),
        _block(
            "Website: https://example.test/path",
            10.0,
            30.0,
            180.0,
            40.0,
        ),
        _block(
            "OCR resource http:/example.test/path",
            10.0,
            50.0,
            180.0,
            60.0,
        ),
    ])

    result = analyze_content(content)

    assert len(result.candidates) == 1
    assert result.candidates[0].label == "Website"
    assert result.candidates[0].value == "https://example.test/path"


def test_analysis_ignores_non_textual_placeholders() -> None:
    content = _content([
        _block("Label:", 10.0, 10.0, 50.0, 20.0),
        _block("________", 10.0, 22.0, 80.0, 30.0),
    ])

    result = analyze_content(content)

    assert result.candidates == []


def test_analysis_accepts_custom_analyzers() -> None:
    class StaticAnalyzer:
        name = "static"
        version = "test"

        def analyze(
            self,
            content: DocumentContent,
        ) -> list[AnalysisCandidate]:
            assert content.source_file == "analysis.pdf"
            return []

    result = analyze_content(
        _content([]),
        analyzers=[StaticAnalyzer()],
    )

    assert result.candidates == []
    assert result.analyzers[0].name == "static"
    assert result.analyzers[0].version == "test"


def test_analysis_respects_an_explicit_empty_analyzer_list() -> None:
    result = analyze_content(
        _content([
            _block("Label: Value", 10.0, 10.0, 80.0, 20.0),
        ]),
        analyzers=[],
        entity_analyzers=[],
    )

    assert result.candidates == []
    assert result.analyzers == []


def test_analyze_file_runs_the_complete_pipeline() -> None:
    result = analyze_file(
        SAMPLES_DIR / "invoices" / "2" / "sample_invoice_2.pdf"
    )

    assert result.source_file == "sample_invoice_2.pdf"
    assert result.analyzers[0].name == "key_value"
    assert result.candidates
    assert all(candidate.evidence for candidate in result.candidates)
    assert result.entities
