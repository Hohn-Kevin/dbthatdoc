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
        "IBAN: DE00123456789012345678 Steuer-Nr.: 123456789"
    ))

    assert len(result.candidates) == 1
    assert len(result.entities) == 2

    iban, tax_number = result.entities

    assert iban.kind == "iban"
    assert iban.normalized_value == "DE00123456789012345678"
    assert iban.validation_status == "invalid"
    assert tax_number.kind == "tax_number"
    assert tax_number.normalized_value == "123456789"
    assert tax_number.validation_status == "invalid"
    assert result.candidates[0].entity_ids == []
    assert iban.evidence[0].start_offset is not None
    assert tax_number.evidence[0].start_offset is not None
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
    assert entities[0].source_confidence == pytest.approx(0.85)
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
        "plausible",
        "plausible",
        "invalid",
    ]


def test_german_dates_use_calendar_validation() -> None:
    result = analyze_content(_content(
        "Rechnungsdatum: 7.8.2015",
        "Termin: 1. März 2024",
        "Kurzdatum: 03.04.25",
        "Unmöglich: 31.02.2024",
        "ISO-Datum: 2018-05-21",
    ))

    dates = [
        entity for entity in result.entities if entity.kind == "date"
    ]

    assert [entity.normalized_value for entity in dates] == [
        "2015-08-07",
        "2024-03-01",
        "03.04.25",
        "2024-02-31",
        "2018-05-21",
    ]
    assert [entity.validation_status for entity in dates] == [
        "valid",
        "valid",
        "plausible",
        "invalid",
        "valid",
    ]
    assert dates[2].validation[1].passed is None


def test_postal_codes_require_shape_and_address_context() -> None:
    result = analyze_content(_content(
        "Postleitzahl: 54321",
        "Beispielweg 1 | 54321 Neustadt",
        "Keine PLZ: 7911",
        "Referenznummer: 123456",
    ))

    postal_codes = [
        entity
        for entity in result.entities
        if entity.kind == "postal_code"
    ]

    assert len(postal_codes) == 1
    assert postal_codes[0].normalized_value == "54321"
    assert postal_codes[0].validation_status == "plausible"
    assert postal_codes[0].validation[1].passed is None
    assert len(postal_codes[0].evidence) == 2


def test_postal_code_can_use_a_positioned_label() -> None:
    content = _content("Postleitzahl", "54321")
    label, value = content.pages[0].blocks
    assert label.position is not None
    assert value.position is not None
    label.position.x0 = 10.0
    label.position.x1 = 60.0
    value.position.x0 = 80.0
    value.position.x1 = 110.0
    value.position.y0 = label.position.y0
    value.position.y1 = label.position.y1

    result = analyze_content(content)

    postal_code = next(
        entity
        for entity in result.entities
        if entity.kind == "postal_code"
    )
    assert postal_code.normalized_value == "54321"
    assert len(postal_code.evidence) == 1


def test_entity_can_span_adjacent_positioned_blocks() -> None:
    content = _content("42,50", "EUR")
    amount, currency = content.pages[0].blocks
    assert amount.position is not None
    assert currency.position is not None
    amount.position.x0 = 10.0
    amount.position.x1 = 50.0
    currency.position.x0 = 60.0
    currency.position.x1 = 90.0
    currency.position.y0 = amount.position.y0
    currency.position.y1 = amount.position.y1

    result = analyze_content(content)

    money = next(
        entity for entity in result.entities if entity.kind == "money"
    )
    assert money.normalized_value == "42.50 EUR"
    assert len(money.evidence) == 2


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
        "Firma Inh.: Erika Musterfrau",
        "Kontoinhaber: Erika Musterfrau",
        "Firma Inh.: Erika Musterfrau",
    ))

    parties = [
        entity for entity in result.entities if entity.kind == "party"
    ]

    assert len(parties) == 1
    assert parties[0].value == "Erika Musterfrau"
    assert parties[0].normalized_value == "erika musterfrau"
    assert parties[0].validation_status == "plausible"
    assert parties[0].party_type == "person"
    assert parties[0].roles == ["owner", "account_holder"]
    assert parties[0].validation[2].passed is None
    assert len(parties[0].evidence) == 3
    assert result.candidates[0].entity_ids == [parties[0].id]
    assert result.candidates[2].entity_ids == [parties[0].id]

    later_result = analyze_content(_content(
        "Inhaber: Erika Musterfrau"
    ))
    later_party = next(
        entity
        for entity in later_result.entities
        if entity.kind == "party"
    )

    assert later_party.id == parties[0].id


def test_party_role_does_not_depend_on_an_owner_example() -> None:
    result = analyze_content(_content(
        "Kontoinhaber: Erika Musterfrau"
    ))

    party = next(entity for entity in result.entities if entity.kind == "party")

    assert party.roles == ["account_holder"]
    assert party.party_type == "person"


def test_party_role_rejects_enumerated_recipient_categories() -> None:
    result = analyze_content(_content(
        "Empf\u00e4nger: Steuerberater, Bank, Kreditversicherung"
    ))

    assert not any(entity.kind == "party" for entity in result.entities)


@pytest.mark.parametrize(
    "name",
    [
        "Muster GmbH & Co. KG",
        "Autohaus Mueller GmbH",
        "Kanzlei Schmidt PartG mbB",
        "Gemeinde Grafschaft",
        "Versicherung24 AG",
        "Mueller Bau GmbH & Co KG",
    ],
)
def test_party_roles_accept_organization_structures(name: str) -> None:
    result = analyze_content(_content(f"Rechnungsaussteller: {name}"))

    party = next(entity for entity in result.entities if entity.kind == "party")

    assert party.value == name
    assert party.party_type == "organization"
    assert party.roles == ["issuer"]


def test_money_supports_prefix_spaces_and_negative_notation() -> None:
    result = analyze_content(_content(
        "Betrag A: EUR 1.234,56",
        "Betrag B: \u20ac 20,00",
        "Betrag C: 1 234,56 EUR",
        "Betrag D: -12,50 EUR",
        "Betrag E: 12,50 EUR-",
    ))

    money = [entity for entity in result.entities if entity.kind == "money"]

    assert [entity.normalized_value for entity in money] == [
        "1234.56 EUR",
        "20.00 EUR",
        "-12.50 EUR",
    ]
    assert all(entity.validation_status == "plausible" for entity in money)
    assert [len(entity.evidence) for entity in money] == [2, 1, 2]


def test_money_fragments_on_different_rows_are_not_combined() -> None:
    content = _content("15,00", "EUR")
    amount, currency = content.pages[0].blocks
    assert amount.position is not None
    assert currency.position is not None
    amount.position.x0 = 10.0
    amount.position.x1 = 50.0
    currency.position.x0 = 60.0
    currency.position.x1 = 90.0

    result = analyze_content(content)

    assert not any(entity.kind == "money" for entity in result.entities)


def test_money_fragments_with_an_intervening_cell_are_not_combined() -> None:
    content = _content("15,00", "Menge", "EUR")
    amount, middle, currency = content.pages[0].blocks
    for block, x0, x1 in (
        (amount, 10.0, 40.0),
        (middle, 45.0, 55.0),
        (currency, 60.0, 90.0),
    ):
        assert block.position is not None
        block.position.x0 = x0
        block.position.x1 = x1
        block.position.y0 = 10.0
        block.position.y1 = 20.0

    result = analyze_content(content)

    assert not any(entity.kind == "money" for entity in result.entities)


def test_invalid_low_confidence_entity_is_marked_as_possible_ocr_damage() -> None:
    content = _content("IBAN: DE00123456789012345678")
    content.pages[0].blocks[0].confidence = 0.4

    result = analyze_content(content)
    iban = next(entity for entity in result.entities if entity.kind == "iban")

    assert iban.recognition_status == "suspected_ocr_corruption"
    assert result.warnings[0].startswith("Suspected OCR corruption")
    assert {check.dimension for check in iban.validation} == {
        "structure",
        "checksum",
    }
