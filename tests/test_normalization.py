from pathlib import Path

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
    assert content.pages[0].blocks[0].text != ""
    assert content.pages[0].blocks[0].position is None


def test_ocr_result_can_be_normalized() -> None:
    extraction = inspect_file(
        SAMPLES_DIR / "sample_invoice_1_scan.pdf"
    )

    content = normalize_extraction(extraction)

    assert content.source_file == "sample_invoice_1_scan.pdf"
    assert len(content.pages) == 2
    assert content.full_text != ""
    assert content.pages[0].blocks[0].source == "tesseract+pypdfium2"
    assert content.pages[0].blocks[0].position is None
