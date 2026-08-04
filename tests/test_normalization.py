from pathlib import Path

from dbthatdoc.models import (
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
    first_element = extraction.pages[0].elements[0]
    first_block = first_page.blocks[0]

    assert len(first_page.blocks) == len(extraction.pages[0].elements)
    assert len(first_page.blocks) > 1
    assert first_block.text == first_element.text
    assert first_block.source == "pdfplumber"
    assert first_block.confidence is None
    assert first_block.position is not None
    assert first_block.position.x0 == first_element.x0
    assert first_block.position.y0 == first_element.y0
    assert first_block.position.x1 == first_element.x1
    assert first_block.position.y1 == first_element.y1


def test_ocr_result_can_be_normalized() -> None:
    extraction = inspect_file(
        SAMPLES_DIR / "sample_invoice_1_scan.pdf"
    )

    content = normalize_extraction(extraction)

    assert content.source_file == "sample_invoice_1_scan.pdf"
    assert len(content.pages) == 2
    assert content.full_text != ""

    first_page = content.pages[0]
    first_element = extraction.pages[0].elements[0]
    first_block = first_page.blocks[0]

    assert len(first_page.blocks) == len(extraction.pages[0].elements)
    assert len(first_page.blocks) > 1
    assert first_block.text == first_element.text
    assert first_block.source == "tesseract+pypdfium2"
    assert first_block.position is not None
    assert first_block.position.x0 == first_element.x0
    assert first_block.position.y0 == first_element.y0
    assert first_block.position.x1 == first_element.x1
    assert first_block.position.y1 == first_element.y1

    block_with_confidence = next(
        block for block in first_page.blocks
        if block.confidence is not None
    )

    assert block_with_confidence.confidence is not None
    assert 0.0 <= block_with_confidence.confidence <= 1.0


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
