from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Any

import pdfplumber
from pdfminer.pdftypes import resolve1
from pdfminer.utils import decode_text

from dbthatdoc.models import (
    ExtractedElement,
    ExtractionResult,
    PageContent,
    ProcessingInfo,
    SourceInfo,
)


_TEXT_FIELD_TYPE = "Tx"
_CHOICE_FIELD_TYPE = "Ch"
_BUTTON_FIELD_TYPE = "Btn"
_SUPPORTED_FIELD_TYPES = {
    _TEXT_FIELD_TYPE,
    _CHOICE_FIELD_TYPE,
    _BUTTON_FIELD_TYPE,
}
_BUTTON_OFF_VALUES = {"", "0", "off", "no", "false"}
_INHERITABLE_FIELD_KEYS = ("FT", "T", "V")


def calculate_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def _pdf_name(value: Any) -> str:
    text = str(value)
    if text.startswith("/'") and text.endswith("'"):
        return text[2:-1]
    if text.startswith("/"):
        return text[1:]
    return text


def _decode_pdf_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, bytes):
        return decode_text(value)

    return _pdf_name(value)


def _inherited_field_attributes(
    annotation: dict[str, Any],
) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    current: Any = annotation
    visited: set[int] = set()

    while isinstance(current, dict) and id(current) not in visited:
        visited.add(id(current))
        for key in _INHERITABLE_FIELD_KEYS:
            if key not in attributes and current.get(key) is not None:
                attributes[key] = resolve1(current[key])
        current = resolve1(current.get("Parent"))

    return attributes


def _decode_choice_value(value: Any) -> str:
    resolved_value = resolve1(value)
    if isinstance(resolved_value, (list, tuple)):
        values = [
            " ".join(_decode_pdf_text(item).split())
            for item in resolved_value
        ]
        return " ".join(value for value in values if value)
    return " ".join(_decode_pdf_text(resolved_value).split())


def _form_field_text(annotation: dict[str, Any]) -> str:
    attributes = _inherited_field_attributes(annotation)
    field_type = _pdf_name(attributes.get("FT"))
    raw_value = attributes.get("V")

    if field_type not in _SUPPORTED_FIELD_TYPES or raw_value is None:
        return ""

    if field_type == _TEXT_FIELD_TYPE:
        return _decode_choice_value(raw_value)

    if field_type == _CHOICE_FIELD_TYPE:
        return _decode_choice_value(raw_value)

    if field_type == _BUTTON_FIELD_TYPE:
        selected_value = _pdf_name(
            resolve1(annotation.get("AS") or raw_value)
        ).strip()
        if selected_value.casefold() in _BUTTON_OFF_VALUES:
            return ""
        field_name = _decode_pdf_text(attributes.get("T")).strip()
        return field_name or selected_value

    return ""


def _form_field_element(
    annotation: dict[str, Any],
    page_height: float,
) -> ExtractedElement | None:
    if _pdf_name(annotation.get("Subtype")) != "Widget":
        return None

    text = _form_field_text(annotation)
    rect = resolve1(annotation.get("Rect"))

    if not text or not isinstance(rect, list) or len(rect) != 4:
        return None

    x0, bottom, x1, top = (float(value) for value in rect)

    return ExtractedElement(
        text=text,
        element_type="form_field",
        confidence=None,
        x0=min(x0, x1),
        y0=page_height - max(bottom, top),
        x1=max(x0, x1),
        y1=page_height - min(bottom, top),
    )


def _extract_form_field_elements(
    page: pdfplumber.page.Page,
    visible_elements: list[ExtractedElement],
) -> list[ExtractedElement]:
    raw_annots = resolve1(page.page_obj.attrs.get("Annots")) or []
    if not isinstance(raw_annots, list):
        raw_annots = [raw_annots]

    elements: list[ExtractedElement] = []
    for raw_annot in raw_annots:
        annotation = resolve1(raw_annot)
        if not isinstance(annotation, dict):
            continue

        element = _form_field_element(annotation, float(page.height))
        if element is None:
            continue

        if _is_visible_duplicate(element, visible_elements):
            continue

        elements.append(element)

    return elements


def _normalized_tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+", text.casefold()))


def _is_visible_duplicate(
    form_element: ExtractedElement,
    visible_elements: list[ExtractedElement],
) -> bool:
    assert form_element.x0 is not None
    assert form_element.y0 is not None
    assert form_element.x1 is not None
    assert form_element.y1 is not None

    field_height = form_element.y1 - form_element.y0
    horizontal_tolerance = max(2.0, field_height * 1.5)
    vertical_tolerance = max(1.0, field_height * 0.25)
    nearby_words = [
        element
        for element in visible_elements
        if (
            element.element_type == "word"
            and element.x0 is not None
            and element.y0 is not None
            and element.x1 is not None
            and element.y1 is not None
            and element.x1 >= form_element.x0 - horizontal_tolerance
            and element.x0 <= form_element.x1 + horizontal_tolerance
            and element.y1 >= form_element.y0 - vertical_tolerance
            and element.y0 <= form_element.y1 + vertical_tolerance
        )
    ]
    nearby_tokens = [
        token
        for element in sorted(
            nearby_words,
            key=lambda item: (item.y0 or 0.0, item.x0 or 0.0),
        )
        for token in _normalized_tokens(element.text)
    ]
    form_tokens = _normalized_tokens(form_element.text)

    if not form_tokens:
        return False

    token_count = len(form_tokens)
    return any(
        tuple(nearby_tokens[index:index + token_count]) == form_tokens
        for index in range(len(nearby_tokens) - token_count + 1)
    )


def extract_pdf_text(file_path: str | Path) -> ExtractionResult:
    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")

    if not path.is_file():
        raise ValueError(f"Pfad ist keine Datei: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Nicht unterstützter Dateityp: {path.suffix}")

    media_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
    pages: list[PageContent] = []
    warnings: list[str] = []

    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            words = page.extract_words() or []

            elements = [
                ExtractedElement(
                    text=str(word["text"]),
                    element_type="word",
                    confidence=None,
                    x0=float(word["x0"]),
                    y0=float(word["top"]),
                    x1=float(word["x1"]),
                    y1=float(word["bottom"]),
                )
                for word in words
                if str(word.get("text", "")).strip()
            ]
            elements.extend(_extract_form_field_elements(page, elements))

            if not text.strip():
                warnings.append(
                    f"Seite {page_number} enthält keinen extrahierbaren Text."
                )

            pages.append(
                PageContent(
                    page_number=page_number,
                    text=text,
                    width=float(page.width),
                    height=float(page.height),
                    elements=elements,
                )
            )

    combined_text = "\n\n".join(
        page.text for page in pages if page.text.strip()
    )

    if not combined_text.strip():
        warnings.append(
            "Die PDF enthält keinen eingebetteten Text. "
            "OCR ist vermutlich erforderlich."
        )

    return ExtractionResult(
        source=SourceInfo(
            filename=path.name,
            path=str(path),
            media_type=media_type,
            source_type="pdf",
            file_size_bytes=path.stat().st_size,
            sha256=calculate_sha256(path),
        ),
        pages=pages,
        text=combined_text,
        warnings=warnings,
        processing=ProcessingInfo(
            extractor="pdfplumber",
            extractor_version=getattr(pdfplumber, "__version__", None),
            page_count=len(pages),
            extraction_method=(
                "embedded_text"
                if combined_text.strip()
                else "no_text_layer"
            ),
            text_extracted=bool(combined_text.strip()),
        ),
    )
