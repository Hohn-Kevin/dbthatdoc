from pathlib import Path

from dbthatdoc.extractors import extract_pdf_text


SAMPLES_DIR = Path(__file__).parent.parent / "samples"


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