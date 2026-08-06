from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from dbthatdoc.extractors import extract_pdf_ocr


SAMPLES_DIR = (
    Path(__file__).parent.parent / "samples"
)


def test_extracts_positioned_elements_from_scan_pdf() -> None:
    result = extract_pdf_ocr(
        SAMPLES_DIR / "invoices" / "1" / "sample_invoice_1_scan.pdf"
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


@pytest.mark.parametrize(
    ("relative_path", "required_text", "forbidden_text"),
    [
        ("invoices/4/sample_invoice_4_scan.pdf", "12345", "12885"),
        ("forms/2/sample_form_2_scan.pdf", "2018-05-21", None),
        ("forms/7/sample_form_7_scan.pdf", "79111", None),
    ],
)
def test_automatic_page_segmentation_regression_matrix(
    relative_path: str,
    required_text: str,
    forbidden_text: str | None,
) -> None:
    result = extract_pdf_ocr(SAMPLES_DIR / relative_path)

    assert required_text in result.text
    if forbidden_text is not None:
        assert forbidden_text not in result.text


def _write_synthetic_layout_pdf(
    destination: Path,
    layout: str,
) -> None:
    font_size = 30 if layout == "receipt" else 40
    font = ImageFont.load_default(size=font_size)

    if layout == "receipt":
        image = Image.new("RGB", (520, 1500), "white")
        lines = [
            "MARKT MITTE",
            "KASSENBON",
            "Brot 2,49 EUR",
            "Milch 1,29 EUR",
            "SUMME 3,78 EUR",
            "BELEG R-4821",
        ]
    else:
        image = Image.new("RGB", (1200, 1600), "white")
        lines = [
            "Musterfirma GmbH",
            "Hauptstrasse 12",
            "12345 Musterstadt",
            "Betreff Vertragsunterlagen",
            "Referenz LETTER-ALPHA-731",
            "Mit freundlichen Gruessen",
        ]

    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text(
            (50, 60 + index * 90),
            line,
            fill="black",
            font=font,
        )

    if layout == "rotated_letter":
        image = image.rotate(90, expand=True)

    image.save(destination, "PDF", resolution=150.0)


@pytest.mark.parametrize(
    ("layout", "required_text"),
    [
        ("letter", "LETTER-ALPHA-731"),
        ("receipt", "R-4821"),
        ("rotated_letter", "LETTER-ALPHA-731"),
    ],
)
def test_automatic_page_segmentation_handles_additional_layouts(
    tmp_path: Path,
    layout: str,
    required_text: str,
) -> None:
    pdf_path = tmp_path / f"{layout}.pdf"
    _write_synthetic_layout_pdf(pdf_path, layout)

    result = extract_pdf_ocr(pdf_path, scale=2.0)

    assert required_text in result.text
