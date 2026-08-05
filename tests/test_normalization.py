from pathlib import Path

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


def test_pdf_result_can_be_normalized() -> None:
    extraction = inspect_file(
        SAMPLES_DIR / "sample_invoice_1.pdf"
    )

    content = normalize_extraction(extraction)

    assert content.source_file == "sample_invoice_1.pdf"
    assert len(content.pages) == 2
    assert content.full_text != ""
    assert len(content.extraction_methods) == 1

    first_page = content.pages[0]
    first_block = first_page.blocks[0]

    assert len(first_page.blocks) < len(extraction.pages[0].elements)
    assert len(first_page.blocks) > 1
    assert (
        "MUSTER" in first_block.text
        or "Rechnung" in first_block.text
    )
    assert first_block.source == "pdfplumber"
    assert first_block.confidence is None
    assert first_block.position is not None
    assert first_block.position.x0 is not None
    assert first_block.position.y0 is not None
    assert first_block.position.x1 is not None
    assert first_block.position.y1 is not None


def test_ocr_result_can_be_normalized() -> None:
    extraction = inspect_file(
        SAMPLES_DIR / "sample_invoice_1_scan.pdf"
    )

    content = normalize_extraction(extraction)

    assert content.source_file == "sample_invoice_1_scan.pdf"
    assert len(content.pages) == 2
    assert content.full_text != ""

    first_page = content.pages[0]
    first_block = first_page.blocks[0]

    assert len(first_page.blocks) < len(extraction.pages[0].elements)
    assert len(first_page.blocks) > 1
    assert not first_block.text.startswith("}")
    assert (
        "MUSTER" in first_block.text
        or "Rechnung" in first_block.text
    )
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

    assert first_block.text == "Hello world"
    assert first_block.confidence == 0.6
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
