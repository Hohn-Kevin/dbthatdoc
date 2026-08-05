from pathlib import Path

import pytest

from dbthatdoc.models import (
    ExtractedElement,
    ExtractionResult,
    PageContent,
    ProcessingInfo,
    SourceInfo,
)
from dbthatdoc.normalization import normalize_extraction
from dbthatdoc.pipeline import inspect_file


SAMPLES_DIR = Path(__file__).parent.parent / "samples"


@pytest.mark.parametrize(
    ("filename", "expected_terms"),
    [
        ("sample_invoice_1.pdf", ("MUSTER", "Rechnung")),
        ("sample_invoice_2.pdf", ("Firmenname",)),
        ("sample_invoice_3.pdf", ("Firmenname",)),
        ("sample_invoice_4.pdf", ("Firmenname", "Dienstleistungen")),
    ],
)
def test_pdf_result_can_be_normalized(
    filename: str,
    expected_terms: tuple[str, ...],
) -> None:
    extraction = inspect_file(
        SAMPLES_DIR / filename
    )

    content = normalize_extraction(extraction)

    assert content.source_file == filename
    assert len(content.pages) == 2
    assert content.full_text != ""
    assert content.full_text == "\n\n".join(
        "\n".join(block.text for block in page.blocks)
        for page in content.pages
    )
    assert len(content.extraction_methods) == 1

    first_page = content.pages[0]
    first_block = first_page.blocks[0]
    leading_text = " ".join(
        block.text for block in first_page.blocks[:3]
    )

    assert len(first_page.blocks) < len(extraction.pages[0].elements)
    assert len(first_page.blocks) > 1
    assert any(term in leading_text for term in expected_terms)
    assert first_block.source == "pdfplumber"
    assert first_block.confidence is None
    assert first_block.position is not None
    assert first_block.position.x0 is not None
    assert first_block.position.y0 is not None
    assert first_block.position.x1 is not None
    assert first_block.position.y1 is not None


@pytest.mark.parametrize(
    ("filename", "expected_terms"),
    [
        ("sample_invoice_1_scan.pdf", ("MUSTER", "Rechnung")),
        ("sample_invoice_2_scan.pdf", ("Professionelle", "Beratung")),
        ("sample_invoice_3_scan.pdf", ("Firmenname",)),
        ("sample_invoice_4_scan.pdf", ("Sachen", "Dienstleistungen")),
    ],
)
def test_ocr_result_can_be_normalized(
    filename: str,
    expected_terms: tuple[str, ...],
) -> None:
    extraction = inspect_file(
        SAMPLES_DIR / filename
    )

    content = normalize_extraction(extraction)

    assert content.source_file == filename
    assert len(content.pages) == 2
    assert content.full_text != ""
    assert content.full_text == "\n\n".join(
        "\n".join(block.text for block in page.blocks)
        for page in content.pages
    )

    first_page = content.pages[0]
    first_block = first_page.blocks[0]
    leading_text = " ".join(
        block.text for block in first_page.blocks[:3]
    )

    assert len(first_page.blocks) < len(extraction.pages[0].elements)
    assert len(first_page.blocks) > 1
    assert len(first_block.text.strip()) > 2
    assert any(term in leading_text for term in expected_terms)
    assert first_block.source == "tesseract+pypdfium2"
    assert first_block.position is not None
    assert first_block.position.x0 is not None
    assert first_block.position.y0 is not None
    assert first_block.position.x1 is not None
    assert first_block.position.y1 is not None

    block_with_confidence = next(
        block for block in first_page.blocks
        if block.confidence is not None
    )

    assert block_with_confidence.confidence is not None
    assert 0.0 <= block_with_confidence.confidence <= 1.0
    assert all(
        0.0 <= block.confidence <= 1.0
        for block in first_page.blocks
        if block.confidence is not None
    )


def test_normalization_groups_words_into_line_blocks_and_ignores_noise() -> None:
    extraction = ExtractionResult(
        source=SourceInfo(
            filename="lines.pdf",
            path="lines.pdf",
            media_type="application/pdf",
            source_type="pdf",
            file_size_bytes=1,
            sha256="abc",
        ),
        pages=[
            PageContent(
                page_number=1,
                text="Hello world\nNext",
                width=200.0,
                height=100.0,
                elements=[
                    ExtractedElement(
                        text="}",
                        element_type="word",
                        confidence=0.02,
                        x0=0.0,
                        y0=0.0,
                        x1=2.0,
                        y1=11.0,
                    ),
                    ExtractedElement(
                        text="Er",
                        element_type="word",
                        confidence=0.44,
                        x0=195.0,
                        y0=0.0,
                        x1=200.0,
                        y1=4.0,
                    ),
                    ExtractedElement(
                        text="ee",
                        element_type="word",
                        confidence=0.18,
                        x0=0.0,
                        y0=0.0,
                        x1=200.0,
                        y1=11.0,
                    ),
                    ExtractedElement(
                        text="artifact",
                        element_type="word",
                        confidence=0.44,
                        x0=10.0,
                        y0=24.0,
                        x1=190.0,
                        y1=26.0,
                    ),
                    ExtractedElement(
                        text="world",
                        element_type="word",
                        confidence=0.7,
                        x0=40.0,
                        y0=10.0,
                        x1=70.0,
                        y1=20.0,
                    ),
                    ExtractedElement(
                        text="Hello",
                        element_type="word",
                        confidence=0.5,
                        x0=10.0,
                        y0=10.0,
                        x1=35.0,
                        y1=20.0,
                    ),
                    ExtractedElement(
                        text="-",
                        element_type="word",
                        confidence=0.84,
                        x0=36.0,
                        y0=13.0,
                        x1=39.0,
                        y1=17.0,
                    ),
                    ExtractedElement(
                        text="Next",
                        element_type="word",
                        confidence=None,
                        x0=10.0,
                        y0=30.0,
                        x1=35.0,
                        y1=40.0,
                    ),
                ],
            ),
        ],
        text="Hello world\nNext",
        processing=ProcessingInfo(
            extractor="test-extractor",
            page_count=1,
            extraction_method="test",
            text_extracted=True,
        ),
    )

    content = normalize_extraction(extraction)

    assert len(content.pages[0].blocks) == 2

    first_block = content.pages[0].blocks[0]

    assert first_block.text == "Hello - world"
    assert first_block.confidence == pytest.approx(0.68)
    assert first_block.position is not None
    assert first_block.position.x0 == 10.0
    assert first_block.position.y0 == 10.0
    assert first_block.position.x1 == 70.0
    assert first_block.position.y1 == 20.0

    second_block = content.pages[0].blocks[1]

    assert second_block.text == "Next"
    assert second_block.confidence is None
    assert second_block.position is not None
    assert second_block.position.x0 == 10.0
    assert second_block.position.y0 == 30.0
    assert second_block.position.x1 == 35.0
    assert second_block.position.y1 == 40.0


def test_normalization_does_not_merge_lines_through_oversized_words() -> None:
    extraction = ExtractionResult(
        source=SourceInfo(
            filename="different-heights.pdf",
            path="different-heights.pdf",
            media_type="application/pdf",
            source_type="pdf",
            file_size_bytes=1,
            sha256="abc",
        ),
        pages=[
            PageContent(
                page_number=1,
                text="top\nTALL\nnext",
                width=200.0,
                height=100.0,
                elements=[
                    ExtractedElement(
                        text="top",
                        element_type="word",
                        confidence=0.9,
                        x0=10.0,
                        y0=0.0,
                        x1=30.0,
                        y1=10.0,
                    ),
                    ExtractedElement(
                        text="TALL",
                        element_type="word",
                        confidence=0.9,
                        x0=40.0,
                        y0=0.0,
                        x1=70.0,
                        y1=40.0,
                    ),
                    ExtractedElement(
                        text="next",
                        element_type="word",
                        confidence=0.9,
                        x0=10.0,
                        y0=30.0,
                        x1=35.0,
                        y1=40.0,
                    ),
                ],
            ),
        ],
        text="top\nTALL\nnext",
        processing=ProcessingInfo(
            extractor="test-extractor",
            page_count=1,
            extraction_method="test",
            text_extracted=True,
        ),
    )

    content = normalize_extraction(extraction)

    assert [
        block.text for block in content.pages[0].blocks
    ] == ["top", "TALL", "next"]
    assert content.full_text == "top\nTALL\nnext"


@pytest.mark.parametrize("scale", [1.0, 3.0])
def test_normalization_splits_distant_text_runs_at_any_scale(
    scale: float,
) -> None:
    def scaled(value: float) -> float:
        return value * scale

    extraction = ExtractionResult(
        source=SourceInfo(
            filename="columns.pdf",
            path="columns.pdf",
            media_type="application/pdf",
            source_type="pdf",
            file_size_bytes=1,
            sha256="abc",
        ),
        pages=[
            PageContent(
                page_number=1,
                text="Left side Right side",
                width=scaled(200.0),
                height=scaled(100.0),
                elements=[
                    ExtractedElement(
                        text=text,
                        element_type="word",
                        confidence=0.9,
                        x0=scaled(x0),
                        y0=scaled(9.5 if x0 > 100.0 else 10.0),
                        x1=scaled(x1),
                        y1=scaled(19.5 if x0 > 100.0 else 20.0),
                    )
                    for text, x0, x1 in [
                        ("Left", 10.0, 30.0),
                        ("side", 35.0, 55.0),
                        ("Right", 130.0, 155.0),
                        ("side", 160.0, 180.0),
                    ]
                ],
            ),
        ],
        text="Left side Right side",
        processing=ProcessingInfo(
            extractor="test-extractor",
            page_count=1,
            extraction_method="test",
            text_extracted=True,
        ),
    )

    content = normalize_extraction(extraction)

    assert [
        block.text for block in content.pages[0].blocks
    ] == ["Left side", "Right side"]
    assert content.full_text == "Left side\nRight side"


def test_normalization_splits_sparse_columns() -> None:
    extraction = ExtractionResult(
        source=SourceInfo(
            filename="sparse-columns.pdf",
            path="sparse-columns.pdf",
            media_type="application/pdf",
            source_type="pdf",
            file_size_bytes=1,
            sha256="abc",
        ),
        pages=[
            PageContent(
                page_number=1,
                text="Left Right",
                width=200.0,
                height=100.0,
                elements=[
                    ExtractedElement(
                        text="Left",
                        element_type="word",
                        confidence=0.9,
                        x0=10.0,
                        y0=10.0,
                        x1=35.0,
                        y1=20.0,
                    ),
                    ExtractedElement(
                        text="Right",
                        element_type="word",
                        confidence=0.9,
                        x0=140.0,
                        y0=10.0,
                        x1=170.0,
                        y1=20.0,
                    ),
                ],
            ),
        ],
        text="Left Right",
        processing=ProcessingInfo(
            extractor="test-extractor",
            page_count=1,
            extraction_method="test",
            text_extracted=True,
        ),
    )

    content = normalize_extraction(extraction)

    assert [
        block.text for block in content.pages[0].blocks
    ] == ["Left", "Right"]
    assert content.full_text == "Left\nRight"


def test_normalization_enforces_the_element_and_position_contract() -> None:
    extraction = ExtractionResult(
        source=SourceInfo(
            filename="contract.pdf",
            path="contract.pdf",
            media_type="application/pdf",
            source_type="pdf",
            file_size_bytes=1,
            sha256="abc",
        ),
        pages=[
            PageContent(
                page_number=1,
                text="kept orphan",
                width=200.0,
                height=100.0,
                elements=[
                    ExtractedElement(
                        text="kept",
                        element_type="word",
                        confidence=0.9,
                        x0=10.0,
                        y0=10.0,
                        x1=35.0,
                        y1=20.0,
                    ),
                    ExtractedElement(
                        text="orphan",
                        element_type="word",
                        confidence=0.4,
                    ),
                    ExtractedElement(
                        text="caption",
                        element_type="image",
                        confidence=0.9,
                        x0=40.0,
                        y0=10.0,
                        x1=80.0,
                        y1=20.0,
                    ),
                    ExtractedElement(
                        text="infinite",
                        element_type="word",
                        confidence=0.9,
                        x0=90.0,
                        y0=10.0,
                        x1=float("inf"),
                        y1=20.0,
                    ),
                    ExtractedElement(
                        text="partial",
                        element_type="word",
                        confidence=0.9,
                        x0=90.0,
                    ),
                ],
            ),
        ],
        text="kept orphan",
        processing=ProcessingInfo(
            extractor="test-extractor",
            page_count=1,
            extraction_method="test",
            text_extracted=True,
        ),
    )

    content = normalize_extraction(extraction)

    assert [
        block.text for block in content.pages[0].blocks
    ] == ["kept", "orphan"]
    assert content.pages[0].blocks[1].position is None
    assert content.pages[0].blocks[1].confidence == 0.4
    assert content.full_text == "kept\norphan"


def test_normalization_keeps_full_page_fallback_without_elements() -> None:
    extraction = ExtractionResult(
        source=SourceInfo(
            filename="fallback.pdf",
            path="fallback.pdf",
            media_type="application/pdf",
            source_type="pdf",
            file_size_bytes=1,
            sha256="abc",
        ),
        pages=[
            PageContent(
                page_number=1,
                text="Fallback text",
            ),
            PageContent(
                page_number=2,
                text="",
            ),
        ],
        text="Fallback text",
        processing=ProcessingInfo(
            extractor="test-extractor",
            page_count=2,
            extraction_method="test",
            text_extracted=True,
        ),
    )

    content = normalize_extraction(extraction)

    assert len(content.pages[0].blocks) == 1
    assert content.pages[0].blocks[0].text == "Fallback text"
    assert content.pages[0].blocks[0].source == "test-extractor"
    assert content.pages[0].blocks[0].confidence is None
    assert content.pages[0].blocks[0].position is None
    assert content.pages[1].blocks == []
    assert content.full_text == "Fallback text"
