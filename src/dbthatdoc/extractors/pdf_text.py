from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

import pdfplumber
from pdfminer.pdftypes import PDFObjRef, resolve1
from pdfminer.psparser import literal_name
from pdfminer.utils import decode_text

from dbthatdoc.models import (
    ExtractedElement,
    ExtractionResult,
    PageContent,
    ProcessingInfo,
    SourceInfo,
)


def calculate_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def _pdf_text(value: object) -> str:
    resolved = resolve1(value)

    if isinstance(resolved, bytes):
        return decode_text(resolved).strip()
    if isinstance(resolved, str):
        return resolved.strip()
    return ""


def _field_widgets(
    field_reference: object,
    inherited: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    field = resolve1(field_reference)

    if not isinstance(field, dict):
        return []

    properties = dict(inherited or {})
    properties.update({
        key: field[key]
        for key in ("FT", "T", "TU", "V")
        if key in field
    })
    widgets: list[dict[str, object]] = []

    if (
        "Subtype" in field
        and literal_name(field["Subtype"]) == "Widget"
    ):
        widget = dict(field)
        widget.update(properties)
        widgets.append(widget)

    for child in resolve1(field.get("Kids", [])) or []:
        widgets.extend(_field_widgets(child, properties))

    return widgets


def _extract_form_fields(
    pdf: pdfplumber.PDF,
) -> dict[int, list[ExtractedElement]]:
    acroform_reference = pdf.doc.catalog.get("AcroForm")

    if acroform_reference is None:
        return {}

    acroform = resolve1(acroform_reference)

    if not isinstance(acroform, dict):
        return {}

    page_by_object_id = {
        page.page_obj.pageid: (page_number, page)
        for page_number, page in enumerate(pdf.pages, start=1)
    }
    elements_by_page: dict[int, list[ExtractedElement]] = {}

    for field_reference in resolve1(acroform.get("Fields", [])) or []:
        for widget in _field_widgets(field_reference):
            field_type = widget.get("FT")

            if field_type is None or literal_name(field_type) != "Tx":
                continue

            value = _pdf_text(widget.get("V", ""))
            label = _pdf_text(
                widget.get("TU", widget.get("T", ""))
            ).rstrip(":").strip()
            page_reference = widget.get("P")
            rect = resolve1(widget.get("Rect"))

            if (
                not value
                or not label
                or not isinstance(page_reference, PDFObjRef)
                or page_reference.objid not in page_by_object_id
                or not isinstance(rect, list)
                or len(rect) != 4
            ):
                continue

            page_number, page = page_by_object_id[page_reference.objid]
            x0, bottom, x1, top = map(float, rect)
            elements_by_page.setdefault(page_number, []).append(
                ExtractedElement(
                    text=f"{label}: {value}",
                    element_type="form_field",
                    confidence=None,
                    x0=min(x0, x1),
                    y0=float(page.height) - max(bottom, top),
                    x1=max(x0, x1),
                    y1=float(page.height) - min(bottom, top),
                )
            )

    return elements_by_page


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
        form_fields_by_page = _extract_form_fields(pdf)

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
            form_fields = form_fields_by_page.get(page_number, [])
            elements.extend(form_fields)

            if form_fields:
                form_text = "\n".join(
                    element.text for element in form_fields
                )
                text = "\n".join(
                    part for part in (text, form_text) if part.strip()
                )

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
