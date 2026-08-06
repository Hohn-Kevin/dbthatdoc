from pathlib import Path

from dbthatdoc.extractors import extract_pdf_text


SAMPLES_DIR = (
    Path(__file__).parent.parent / "samples" / "invoices" / "1"
)


def test_extracts_text_from_digital_pdf() -> None:
    result = extract_pdf_text(
        SAMPLES_DIR / "sample_invoice_1.pdf"
    )

    assert result.source.source_type == "pdf"
    assert result.processing.extraction_method == "embedded_text"
    assert result.processing.text_extracted is True
    assert result.processing.page_count == 2
    assert "Rechnung" in result.text
    assert result.warnings == []

    first_page = result.pages[0]

    assert first_page.elements
    assert first_page.elements[0].element_type == "word"
    assert first_page.elements[0].text != ""
    assert first_page.width is not None
    assert first_page.height is not None

    for element in first_page.elements:
        assert element.x0 is not None
        assert element.y0 is not None
        assert element.x1 is not None
        assert element.y1 is not None

        assert 0 <= element.x0 < element.x1 <= first_page.width
        assert 0 <= element.y0 < element.y1 <= first_page.height


def test_detects_pdf_without_text_layer() -> None:
    result = extract_pdf_text(
        SAMPLES_DIR / "sample_invoice_1_scan.pdf"
    )

    assert result.source.source_type == "pdf"
    assert result.processing.extraction_method == "no_text_layer"
    assert result.processing.text_extracted is False
    assert result.processing.page_count == 2
    assert result.text == ""
    assert any("OCR" in warning for warning in result.warnings)
    assert result.pages[0].elements == []


def test_extracts_positioned_acroform_text_values() -> None:
    result = extract_pdf_text(
        SAMPLES_DIR.parent.parent
        / "forms"
        / "2"
        / "sample_form_2.pdf"
    )

    form_fields = [
        element
        for page in result.pages
        for element in page.elements
        if element.element_type == "form_field"
    ]

    assert form_fields
    assert any(
        element.text == "Datum der Einführung: 2018-05-21"
        for element in form_fields
    )
    assert all(element.x0 is not None for element in form_fields)
    assert all(element.y0 is not None for element in form_fields)
