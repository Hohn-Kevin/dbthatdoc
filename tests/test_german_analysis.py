import pytest

from dbthatdoc.analysis import analyze_content
from dbthatdoc.models import (
    DocumentContent,
    DocumentPage,
    TextBlock,
    TextPosition,
)


def _content(*texts: str) -> DocumentContent:
    blocks = [
        TextBlock(
            text=text,
            page_number=1,
            source="test-source",
            confidence=0.9 - index * 0.1,
            position=TextPosition(
                x0=10.0,
                y0=10.0 + index * 20.0,
                x1=190.0,
                y1=20.0 + index * 20.0,
            ),
        )
        for index, text in enumerate(texts)
    ]
    return DocumentContent(
        source_file="german.pdf",
        pages=[
            DocumentPage(
                page_number=1,
                width=200.0,
                height=200.0,
                blocks=blocks,
            ),
        ],
        full_text="\n".join(texts),
        extraction_methods=["test-source"],
    )


def test_german_entities_separate_combined_financial_fields() -> None:
    result = analyze_content(_content(
        "IBAN: DE3712345679999 9999 99 Steuer-Nr.: 12345613"
    ))

    assert len(result.candidates) == 1
    assert len(result.entities) == 2

    iban, tax_number = result.entities

    assert iban.kind == "iban"
    assert iban.normalized_value == "DE3712345679999999999"
    assert iban.validation_status == "invalid"
    assert tax_number.kind == "tax_number"
    assert tax_number.normalized_value == "12345613"
    assert tax_number.validation_status == "invalid"
    assert result.candidates[0].entity_ids == [iban.id, tax_number.id]
    assert len(result.warnings) == 2


def test_valid_iban_is_normalized_checked_and_referenced_once() -> None:
    iban = "DE89 3704 0044 0532 0130 00"
    result = analyze_content(_content(
        f"IBAN: {iban}",
        f"Bankverbindung: {iban}",
    ))

    entities = [
        entity for entity in result.entities if entity.kind == "iban"
    ]

    assert len(entities) == 1
    assert entities[0].normalized_value == "DE89370400440532013000"
    assert entities[0].validation_status == "valid"
    assert all(check.passed for check in entities[0].validation)
    assert len(entities[0].evidence) == 2
    assert entities[0].confidence == pytest.approx(0.85)
    assert all(
        candidate.entity_ids == [entities[0].id]
        for candidate in result.candidates
    )


def test_tax_number_validation_distinguishes_plausibility() -> None:
    result = analyze_content(_content(
        "Steuernummer: 12/345/67890",
        "Steuer-Nr.: 1234567890123",
        "Steuernummer: 12345678",
    ))

    tax_numbers = [
        entity
        for entity in result.entities
        if entity.kind == "tax_number"
    ]

    assert [
        entity.validation_status for entity in tax_numbers
    ] == ["plausible", "plausible", "invalid"]
    assert tax_numbers[0].normalized_value == "1234567890"
    assert tax_numbers[0].validation[1].passed is None


def test_german_money_values_are_normalized_and_validated() -> None:
    result = analyze_content(_content(
        "Gesamtbetrag: 1.234,56 EUR",
        "Zahlbetrag: 20 Euro",
        "Fehlerhafter Betrag: 12,345 €",
    ))

    money = [
        entity for entity in result.entities if entity.kind == "money"
    ]

    assert [entity.normalized_value for entity in money] == [
        "1234.56 EUR",
        "20.00 EUR",
        "12.345 EUR",
    ]
    assert [entity.validation_status for entity in money] == [
        "valid",
        "valid",
        "invalid",
    ]


def test_german_dates_use_calendar_validation() -> None:
    result = analyze_content(_content(
        "Rechnungsdatum: 7.8.2015",
        "Termin: 1. März 2024",
        "Kurzdatum: 03.04.25",
        "Unmöglich: 31.02.2024",
    ))

    dates = [
        entity for entity in result.entities if entity.kind == "date"
    ]

    assert [entity.normalized_value for entity in dates] == [
        "2015-08-07",
        "2024-03-01",
        "03.04.25",
        "2024-02-31",
    ]
    assert [entity.validation_status for entity in dates] == [
        "valid",
        "valid",
        "plausible",
        "invalid",
    ]
    assert dates[2].validation[1].passed is None


def test_entity_analysis_can_be_disabled_explicitly() -> None:
    result = analyze_content(
        _content("IBAN: DE89 3704 0044 0532 0130 00"),
        entity_analyzers=[],
    )

    assert result.entities == []
    assert result.candidates[0].entity_ids == []
    assert [analyzer.name for analyzer in result.analyzers] == [
        "key_value"
    ]


def test_repeated_owner_references_share_a_party_entity() -> None:
    result = analyze_content(_content(
        "Firma Inh.: Max Mustermann",
        "Kontoinhaber: Max Mustermann",
        "Firma Inh.: Max Mustermann",
    ))

    parties = [
        entity for entity in result.entities if entity.kind == "party"
    ]

    assert len(parties) == 1
    assert parties[0].value == "Max Mustermann"
    assert parties[0].normalized_value == "max mustermann"
    assert parties[0].validation_status == "plausible"
    assert parties[0].roles == ["owner"]
    assert parties[0].validation[1].passed is None
    assert len(parties[0].evidence) == 2
    assert result.candidates[0].entity_ids == [parties[0].id]
    assert result.candidates[2].entity_ids == [parties[0].id]

    later_result = analyze_content(_content(
        "Inhaber: Max Mustermann"
    ))
    later_party = next(
        entity
        for entity in later_result.entities
        if entity.kind == "party"
    )

    assert later_party.id == parties[0].id
