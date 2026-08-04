import pytest
from pydantic import ValidationError

from dbthatdoc.models import ExtractedElement, PageContent


def test_page_content_defaults_to_empty_elements() -> None:
    page = PageContent(
        page_number=1,
        text="Beispieltext",
    )

    assert page.elements == []


def test_extracted_element_accepts_position_and_confidence() -> None:
    element = ExtractedElement(
        text="Rechnung",
        element_type="word",
        confidence=0.95,
        x0=10.0,
        y0=20.0,
        x1=80.0,
        y1=35.0,
    )

    assert element.text == "Rechnung"
    assert element.element_type == "word"
    assert element.confidence == 0.95
    assert element.x0 == 10.0
    assert element.y0 == 20.0
    assert element.x1 == 80.0
    assert element.y1 == 35.0


def test_extracted_element_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        ExtractedElement(
            text="Rechnung",
            element_type="word",
            confidence=1.5,
        )
