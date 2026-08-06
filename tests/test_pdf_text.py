from pathlib import Path

from dbthatdoc.extractors import extract_pdf_text
from dbthatdoc.extractors.pdf_text import (
    _form_field_text,
    _is_visible_duplicate,
)
from dbthatdoc.models import ExtractedElement


SAMPLES_DIR = (
    Path(__file__).parent.parent / "samples" / "invoices" / "1"
)
FORM_SAMPLES_DIR = (
    Path(__file__).parent.parent / "samples" / "forms" / "2"
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


def test_extracts_acroform_values_as_positioned_elements() -> None:
    result = extract_pdf_text(
        FORM_SAMPLES_DIR / "sample_form_2.pdf"
    )

    form_elements = [
        element
        for page in result.pages
        for element in page.elements
        if element.element_type == "form_field"
    ]

    assert any(
        element.text == "2018-05-21"
        for element in form_elements
    )
    assert all(element.text != "On" for element in form_elements)

    for element in form_elements:
        assert element.x0 is not None
        assert element.y0 is not None
        assert element.x1 is not None
        assert element.y1 is not None


def test_acroform_values_inherit_properties_from_parent_fields() -> None:
    parent = {
        "FT": "/Tx",
        "T": b"invoice_date",
        "V": b"2018-05-21",
    }

    assert _form_field_text({"Parent": parent}) == "2018-05-21"


def test_acroform_text_uses_pdf_string_decoding() -> None:
    assert _form_field_text({
        "FT": "/Tx",
        "V": b"\xfe\xff\x00M\x00\xfc\x00l\x00l\x00e\x00r",
    }) == "M\u00fcller"


def test_acroform_choice_and_button_values_are_supported() -> None:
    assert _form_field_text({
        "FT": "/Ch",
        "V": [b"Alpha", b"Beta"],
    }) == "Alpha Beta"
    assert _form_field_text({
        "FT": "/Btn",
        "T": b"newsletter",
        "V": "/Yes",
        "AS": "/Yes",
    }) == "newsletter"
    assert _form_field_text({
        "FT": "/Btn",
        "T": b"newsletter",
        "V": "/Off",
    }) == ""
    assert _form_field_text({"FT": "/Sig", "V": b"signed"}) == ""


def test_visible_duplicate_requires_geometric_proximity() -> None:
    form_element = ExtractedElement(
        text="2018",
        element_type="form_field",
        x0=100.0,
        y0=10.0,
        x1=150.0,
        y1=20.0,
    )
    distant_word = ExtractedElement(
        text="2018",
        element_type="word",
        x0=10.0,
        y0=70.0,
        x1=40.0,
        y1=80.0,
    )
    overlapping_word = distant_word.model_copy(update={
        "x0": 105.0,
        "y0": 11.0,
        "x1": 135.0,
        "y1": 19.0,
    })

    assert not _is_visible_duplicate(form_element, [distant_word])
    assert _is_visible_duplicate(form_element, [overlapping_word])
