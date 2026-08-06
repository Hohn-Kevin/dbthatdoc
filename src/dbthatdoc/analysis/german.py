from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re

from dbthatdoc.models import (
    AnalysisCandidate,
    AnalysisEntity,
    AnalysisEvidence,
    DocumentContent,
    TextBlock,
    ValidationCheck,
)


_IBAN_PATTERN = re.compile(r"\bDE(?:[ -]?\d){15,25}\b", re.IGNORECASE)
_TAX_NUMBER_PATTERN = re.compile(
    r"\b(?:Steuer(?:nummer|-Nr\.?)|St\.?\s*-?\s*Nr\.?)"
    r"\s*:?\s*(?P<number>\d(?:[\d /-]*\d)?)",
    re.IGNORECASE,
)
_MONEY_PATTERN = re.compile(
    r"(?<![\w.,])"
    r"(?P<amount>(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,3})?)"
    r"\s*(?:EUR|Euro|€)(?!\w)",
    re.IGNORECASE,
)
_NUMERIC_DATE_PATTERN = re.compile(
    r"\b(?P<day>\d{1,2})\.\s*"
    r"(?P<month>\d{1,2})\.\s*"
    r"(?P<year>\d{2}|\d{4})\b"
)
_MONTHS = {
    "januar": 1,
    "februar": 2,
    "maerz": 3,
    "märz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}
_TEXT_DATE_PATTERN = re.compile(
    r"\b(?P<day>\d{1,2})\.\s*"
    rf"(?P<month>{'|'.join(map(re.escape, _MONTHS))})\s+"
    r"(?P<year>\d{2}|\d{4})\b",
    re.IGNORECASE,
)
_OWNER_LABEL_PATTERN = re.compile(
    r"(?:^|\s)(?:Inh\.?|Inhaber|Inhaberin)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _EntityMatch:
    start: int
    kind: str
    value: str
    normalized_value: str
    validation_status: str
    validation: tuple[ValidationCheck, ...]
    roles: tuple[str, ...] = ()


class GermanEntityAnalyzer:
    name = "german_document_entities"
    version = "1.0"

    def analyze(
        self,
        content: DocumentContent,
        candidates: Sequence[AnalysisCandidate],
    ) -> list[AnalysisEntity]:
        entities: list[AnalysisEntity] = []
        entity_by_key: dict[tuple[str, str], AnalysisEntity] = {}

        def add_match(
            match: _EntityMatch,
            evidence: AnalysisEvidence,
        ) -> None:
            key = (match.kind, match.normalized_value)
            existing = entity_by_key.get(key)

            if existing is not None:
                if not _contains_evidence(existing, evidence):
                    existing.evidence.append(evidence)
                    existing.confidence = _average_confidence(
                        existing.evidence
                    )
                for role in match.roles:
                    if role not in existing.roles:
                        existing.roles.append(role)
                return

            entity = AnalysisEntity(
                id=_entity_id(match.kind, match.normalized_value),
                kind=match.kind,
                value=match.value,
                normalized_value=match.normalized_value,
                validation_status=match.validation_status,
                validation=list(match.validation),
                roles=list(match.roles),
                confidence=evidence.confidence,
                evidence=[evidence],
            )
            entities.append(entity)
            entity_by_key[key] = entity

        for page in content.pages:
            for block_index, block in enumerate(page.blocks):
                evidence = _evidence(block, block_index)

                for match in _find_matches(block.text):
                    add_match(match, evidence)

        for candidate in candidates:
            party_match = _party_match(candidate)

            if party_match is not None:
                add_match(party_match, candidate.evidence[-1])

        return entities


def _find_matches(text: str) -> list[_EntityMatch]:
    matches = [
        *(_iban_match(match) for match in _IBAN_PATTERN.finditer(text)),
        *(
            _tax_number_match(match)
            for match in _TAX_NUMBER_PATTERN.finditer(text)
        ),
        *(_money_match(match) for match in _MONEY_PATTERN.finditer(text)),
        *(
            _date_match(match, numeric_month=True)
            for match in _NUMERIC_DATE_PATTERN.finditer(text)
        ),
        *(
            _date_match(match, numeric_month=False)
            for match in _TEXT_DATE_PATTERN.finditer(text)
        ),
    ]
    return sorted(matches, key=lambda match: match.start)


def _entity_id(kind: str, normalized_value: str) -> str:
    fingerprint = sha256(
        f"{kind}\0{normalized_value}".encode("utf-8")
    ).hexdigest()[:12]
    return f"de-{kind.replace('_', '-')}-{fingerprint}"


def _party_match(
    candidate: AnalysisCandidate,
) -> _EntityMatch | None:
    if not _OWNER_LABEL_PATTERN.search(candidate.label.strip()):
        return None

    value = " ".join(candidate.value.split())
    words = value.split()
    name_shape_valid = (
        2 <= len(words) <= 6
        and all(any(character.isalpha() for character in word) for word in words)
        and not any(character.isdigit() for character in value)
    )

    if not name_shape_valid:
        return None

    return _EntityMatch(
        start=0,
        kind="party",
        value=value,
        normalized_value=value.casefold(),
        validation_status="plausible",
        validation=(
            ValidationCheck(
                rule="de_party_name_shape",
                passed=True,
                details="Name-like value associated with an owner label",
            ),
            ValidationCheck(
                rule="official_identity",
                passed=None,
                details="No external identity verification was performed",
            ),
        ),
        roles=("owner",),
    )


def _iban_match(match: re.Match[str]) -> _EntityMatch:
    value = match.group(0).strip()
    normalized = re.sub(r"[ -]", "", value).upper()
    structure_valid = bool(re.fullmatch(r"DE\d{20}", normalized))
    checksum_valid = structure_valid and _iban_checksum_valid(normalized)

    return _EntityMatch(
        start=match.start(),
        kind="iban",
        value=value,
        normalized_value=normalized,
        validation_status="valid" if checksum_valid else "invalid",
        validation=(
            ValidationCheck(
                rule="de_iban_structure",
                passed=structure_valid,
                details="DE country code followed by 20 digits",
            ),
            ValidationCheck(
                rule="iban_mod_97",
                passed=checksum_valid,
                details="ISO 13616 MOD-97 checksum",
            ),
        ),
    )


def _iban_checksum_valid(value: str) -> bool:
    rearranged = value[4:] + value[:4]
    numeric = "".join(
        character if character.isdigit() else str(ord(character) - 55)
        for character in rearranged
    )
    return int(numeric) % 97 == 1


def _tax_number_match(match: re.Match[str]) -> _EntityMatch:
    value = match.group("number").strip()
    normalized = re.sub(r"[ /-]", "", value)
    plausible_length = len(normalized) in {10, 11, 13}

    return _EntityMatch(
        start=match.start("number"),
        kind="tax_number",
        value=value,
        normalized_value=normalized,
        validation_status=(
            "plausible" if plausible_length else "invalid"
        ),
        validation=(
            ValidationCheck(
                rule="de_tax_number_length",
                passed=plausible_length,
                details=(
                    "10 or 11 digits in a state schema, or 13 digits in "
                    "the unified federal schema"
                ),
            ),
            ValidationCheck(
                rule="de_tax_number_state_checksum",
                passed=None,
                details=(
                    "Requires the federal state and its applicable "
                    "check-digit procedure"
                ),
            ),
        ),
    )


def _money_match(match: re.Match[str]) -> _EntityMatch:
    value = match.group(0).strip()
    raw_amount = match.group("amount")
    decimal_places = (
        len(raw_amount.rsplit(",", maxsplit=1)[1])
        if "," in raw_amount
        else 0
    )

    try:
        amount = Decimal(raw_amount.replace(".", "").replace(",", "."))
        syntax_valid = decimal_places <= 2
        normalized = (
            f"{amount:.2f} EUR"
            if syntax_valid
            else f"{amount:f} EUR"
        )
    except InvalidOperation:
        syntax_valid = False
        normalized = value.upper()

    return _EntityMatch(
        start=match.start(),
        kind="money",
        value=value,
        normalized_value=normalized,
        validation_status="valid" if syntax_valid else "invalid",
        validation=(
            ValidationCheck(
                rule="de_money_notation",
                passed=syntax_valid,
                details=(
                    "German decimal notation with EUR, Euro, or euro sign"
                ),
            ),
        ),
    )


def _date_match(
    match: re.Match[str],
    *,
    numeric_month: bool,
) -> _EntityMatch:
    value = match.group(0).strip()
    day = int(match.group("day"))
    month_text = match.group("month")
    month = (
        int(month_text)
        if numeric_month
        else _MONTHS[month_text.casefold()]
    )
    year_text = match.group("year")

    if len(year_text) == 2:
        calendar_valid = _calendar_date_valid(2000, month, day)
        status = "plausible" if calendar_valid else "invalid"
        normalized = f"{day:02d}.{month:02d}.{year_text}"
        year_check: bool | None = None
        year_details = "Two-digit year is inherently ambiguous"
    else:
        year = int(year_text)
        calendar_valid = _calendar_date_valid(year, month, day)
        status = "valid" if calendar_valid else "invalid"
        normalized = f"{year:04d}-{month:02d}-{day:02d}"
        year_check = True
        year_details = "Four-digit year permits ISO normalization"

    return _EntityMatch(
        start=match.start(),
        kind="date",
        value=value,
        normalized_value=normalized,
        validation_status=status,
        validation=(
            ValidationCheck(
                rule="gregorian_calendar_date",
                passed=calendar_valid,
                details="Day and month form a possible calendar date",
            ),
            ValidationCheck(
                rule="unambiguous_year",
                passed=year_check,
                details=year_details,
            ),
        ),
    )


def _calendar_date_valid(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _evidence(block: TextBlock, block_index: int) -> AnalysisEvidence:
    return AnalysisEvidence(
        page_number=block.page_number,
        block_index=block_index,
        text=block.text,
        source=block.source,
        confidence=block.confidence,
        position=block.position,
    )


def _contains_evidence(
    entity: AnalysisEntity,
    evidence: AnalysisEvidence,
) -> bool:
    return any(
        item.page_number == evidence.page_number
        and item.block_index == evidence.block_index
        for item in entity.evidence
    )


def _average_confidence(
    evidence: list[AnalysisEvidence],
) -> float | None:
    confidences = [
        item.confidence
        for item in evidence
        if item.confidence is not None
    ]
    if not confidences:
        return None
    return sum(confidences) / len(confidences)
