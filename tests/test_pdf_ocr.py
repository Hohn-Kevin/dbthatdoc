from pathlib import Path

import pytest

from dbthatdoc.extractors import extract_pdf_ocr


SAMPLES_DIR = (
    Path(__file__).parent.parent / "samples" / "invoices" / "1"
)


def test_extracts_positioned_elements_from_scan_pdf() -> None:
    result = extract_pdf_ocr(
        SAMPLES_DIR / "sample_invoice_1_scan.pdf"
    )

    assert result.processing.extraction_method == "ocr"
    assert result.processing.text_extracted is True
    assert result.processing.page_count == 2
    assert result.text != ""

    first_page = result.pages[0]

    assert first_page.width is not None
    assert first_page.height is not None
    assert first_page.elements

    for element in first_page.elements:
        assert element.element_type == "word"
        assert element.text != ""

        assert element.x0 is not None
        assert element.y0 is not None
        assert element.x1 is not None
        assert element.y1 is not None

        assert 0 <= element.x0 < element.x1 <= first_page.width
        assert 0 <= element.y0 < element.y1 <= first_page.height

        if element.confidence is not None:
            assert 0.0 <= element.confidence <= 1.0


def test_extract_pdf_ocr_rejects_unknown_page_segmentation_mode() -> None:
    with pytest.raises(ValueError, match="between 0 and 13"):
        extract_pdf_ocr("unused.pdf", page_segmentation_mode=14)
