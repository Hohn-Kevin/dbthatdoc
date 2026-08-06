from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re

from dbthatdoc.analysis.layout import LayoutConfig, is_right_neighbor
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
_AMOUNT = r"(?:\d{1,3}(?:[. ]\d{3})+|\d+)(?:,\d{1,3})?"
_MONEY_SUFFIX_PATTERN = re.compile(
    rf"(?<![\w.,])(?P<sign>-)?(?P<amount>{_AMOUNT})"
    r"\s*(?P<currency>EUR|Euro|\u20ac)(?P<trailing_sign>-)?(?!\w)",
    re.IGNORECASE,
)
_MONEY_PREFIX_PATTERN = re.compile(
    rf"(?<!\w)(?P<currency>EUR|Euro|\u20ac)\s*"
    rf"(?P<sign>-)?(?P<amount>{_AMOUNT})(?![\w.,])",
    re.IGNORECASE,
)
_AMOUNT_ONLY_PATTERN = re.compile(rf"(?P<sign>-)?{_AMOUNT}(?P<trailing_sign>-)?")
_CURRENCY_ONLY_PATTERN = re.compile(r"(?:EUR|Euro|\u20ac)", re.IGNORECASE)
_NUMERIC_DATE_PATTERN = re.compile(
    r"\b(?P<day>\d{1,2})\.\s*(?P<month>\d{1,2})\.\s*"
    r"(?P<year>\d{2}|\d{4})\b"
)
_ISO_DATE_PATTERN = re.compile(
    r"\b(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b"
)
_MONTHS = {
    "januar": 1,
    "februar": 2,
    "maerz": 3,
    "m\u00e4rz": 3,
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
_PARTY_ROLE_PATTERNS = {
    "owner": re.compile(
        r"(?:\bInh\.?(?=\s|$)|\bInhaber(?:in)?\b)", re.IGNORECASE
    ),
    "account_holder": re.compile(
        r"Kontoinhaber(?:in)?", re.IGNORECASE
    ),
    "issuer": re.compile(
        r"(?:Absender|Rechnungsaussteller(?:in)?)", re.IGNORECASE
    ),
    "recipient": re.compile(
        r"(?:Empf\u00e4nger|Empfaenger|Rechnungs(?:empf\u00e4nger|empfaenger)|"
        r"Zahlungs(?:empf\u00e4nger|empfaenger))(?:in)?",
        re.IGNORECASE,
    ),
    "client": re.compile(r"Auftraggeber(?:in)?", re.IGNORECASE),
    "policy_holder": re.compile(
        r"Versicherungsnehmer(?:in)?", re.IGNORECASE
    ),
    "tenant": re.compile(r"Mieter(?:in)?", re.IGNORECASE),
    "landlord": re.compile(r"Vermieter(?:in)?", re.IGNORECASE),
    "managing_director": re.compile(
        r"Gesch\u00e4ftsf\u00fchrer(?:in)?|Geschaeftsfuehrer(?:in)?",
        re.IGNORECASE,
    ),
    "buyer": re.compile(r"K\u00e4ufer(?:in)?|Kaeufer(?:in)?", re.IGNORECASE),
    "seller": re.compile(r"Verk\u00e4ufer(?:in)?|Verkaeufer(?:in)?", re.IGNORECASE),
}
_POSTAL_LABEL_PATTERN = re.compile(r"(?:PLZ|Postleitzahl)", re.IGNORECASE)
_LABELED_POSTAL_CODE_PATTERN = re.compile(
    r"\b(?:PLZ|Postleitzahl)(?:\s+[\w.\u00c4-\u00df-]+){0,4}"
    r"\s*:\s*(?P<postal_code>\d{5})\b",
    re.IGNORECASE,
)
_ADDRESS_POSTAL_CODE_PATTERN = re.compile(
    r"(?<!\d)(?P<postal_code>\d{5})\s+"
    r"[A-Z\u00c4\u00d6\u00dc][A-Za-z\u00c4-\u00df-]+"
    r"(?:\s+[A-Za-z\u00c4-\u00df-]+){0,3}(?=\s*(?:[|,\n]|$))"
)


@dataclass(frozen=True)
class GermanEntityConfig:
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    ocr_corruption_confidence_threshold: float = 0.75


@dataclass(frozen=True)
class _EntityMatch:
    start: int
    end: int
    kind: str
    value: str
    normalized_value: str
    validation_status: str
    validation: tuple[ValidationCheck, ...]
    roles: tuple[str, ...] = ()


class GermanEntityAnalyzer:
    name = "german_document_entities"
    version = "1.1"

    def __init__(self, config: GermanEntityConfig | None = None) -> None:
        self.config = config or GermanEntityConfig()

    def analyze(
        self,
        content: DocumentContent,
        candidates: Sequence[AnalysisCandidate],
    ) -> list[AnalysisEntity]:
        entities: list[AnalysisEntity] = []
        entity_by_key: dict[tuple[str, str], AnalysisEntity] = {}

        def add_match(match: _EntityMatch, evidence: AnalysisEvidence) -> None:
            key = (match.kind, match.normalized_value)
            existing = entity_by_key.get(key)
            recognition_status = _recognition_status(
                match.validation_status,
                evidence.confidence,
                self.config.ocr_corruption_confidence_threshold,
            )

            if existing is not None:
                if not _contains_evidence(existing, evidence):
                    existing.evidence.append(evidence)
                    existing.confidence = _average_confidence(existing.evidence)
                for role in match.roles:
                    if role not in existing.roles:
                        existing.roles.append(role)
                if recognition_status == "recognized_invalid":
                    existing.recognition_status = recognition_status
                return

            entity = AnalysisEntity(
                id=_entity_id(match.kind, match.normalized_value),
                kind=match.kind,
                value=match.value,
                normalized_value=match.normalized_value,
                validation_status=match.validation_status,
                recognition_status=recognition_status,
                validation=list(match.validation),
                roles=list(match.roles),
                confidence=evidence.confidence,
                evidence=[evidence],
            )
            entities.append(entity)
            entity_by_key[key] = entity

        for page in content.pages:
            for block_index, block in enumerate(page.blocks):
                for match in _find_matches(block.text):
                    add_match(
                        match,
                        _evidence(block, block_index, match.start, match.end),
                    )

            for left_index, right_index in _money_fragment_pairs(
                page.blocks, self.config.layout
            ):
                left = page.blocks[left_index]
                right = page.blocks[right_index]
                money_match = _split_money_match(left.text, right.text)
                assert money_match is not None
                add_match(
                    money_match,
                    _evidence(left, left_index, 0, len(left.text)),
                )
                add_match(
                    money_match,
                    _evidence(right, right_index, 0, len(right.text)),
                )

            for left_index, right_index in _adjacent_right_pairs(
                page.blocks, self.config.layout
            ):
                left = page.blocks[left_index]
                right = page.blocks[right_index]
                postal_match = _split_postal_match(left.text, right.text)
                if postal_match is not None:
                    add_match(
                        postal_match,
                        _evidence(right, right_index, 0, len(right.text)),
                    )

        for candidate in candidates:
            party_match = _party_match(candidate)
            if party_match is not None:
                add_match(
                    party_match,
                    _evidence_from_candidate_value(candidate),
                )

        return entities


def _find_matches(text: str) -> list[_EntityMatch]:
    matches = [
        *(_iban_match(match) for match in _IBAN_PATTERN.finditer(text)),
        *(_tax_number_match(match) for match in _TAX_NUMBER_PATTERN.finditer(text)),
        *(_money_match(match) for match in _MONEY_SUFFIX_PATTERN.finditer(text)),
        *(_money_match(match) for match in _MONEY_PREFIX_PATTERN.finditer(text)),
        *(
            _date_match(match, numeric_month=True)
            for match in _NUMERIC_DATE_PATTERN.finditer(text)
        ),
        *(_iso_date_match(match) for match in _ISO_DATE_PATTERN.finditer(text)),
        *(
            _date_match(match, numeric_month=False)
            for match in _TEXT_DATE_PATTERN.finditer(text)
        ),
        *(
            _postal_code_match(match)
            for match in _LABELED_POSTAL_CODE_PATTERN.finditer(text)
        ),
        *(
            _postal_code_match(match)
            for match in _ADDRESS_POSTAL_CODE_PATTERN.finditer(text)
        ),
    ]
    unique = {(match.kind, match.start, match.end): match for match in matches}
    return sorted(unique.values(), key=lambda match: match.start)


def _entity_id(kind: str, normalized_value: str) -> str:
    fingerprint = sha256(f"{kind}\0{normalized_value}".encode()).hexdigest()[:12]
    return f"de-{kind.replace('_', '-')}-{fingerprint}"


def _party_match(candidate: AnalysisCandidate) -> _EntityMatch | None:
    label = candidate.label.strip()
    roles = tuple(
        role
        for role, pattern in _PARTY_ROLE_PATTERNS.items()
        if pattern.search(label)
    )
    if not roles:
        return None

    value = " ".join(candidate.value.split())
    words = value.split()
    name_shape_valid = (
        2 <= len(words) <= 8
        and all(any(character.isalpha() for character in word) for word in words)
        and not any(character.isdigit() for character in value)
        and not any(separator in value for separator in ",;|/")
    )
    if not name_shape_valid:
        return None

    start = candidate.value_start_offset or 0
    end = candidate.value_end_offset or len(candidate.evidence[-1].text)
    return _EntityMatch(
        start=start,
        end=end,
        kind="party",
        value=value,
        normalized_value=value.casefold(),
        validation_status="plausible",
        validation=(
            ValidationCheck(
                rule="de_party_name_shape",
                dimension="structure",
                passed=True,
                details="Name-like value associated with a recognized party role",
            ),
            ValidationCheck(
                rule="official_identity",
                dimension="external",
                passed=None,
                details="No external identity verification was performed",
            ),
        ),
        roles=roles,
    )


def _iban_match(match: re.Match[str]) -> _EntityMatch:
    value = match.group(0).strip()
    normalized = re.sub(r"[ -]", "", value).upper()
    structure_valid = bool(re.fullmatch(r"DE\d{20}", normalized))
    checksum_valid = structure_valid and _iban_checksum_valid(normalized)
    return _EntityMatch(
        start=match.start(),
        end=match.end(),
        kind="iban",
        value=value,
        normalized_value=normalized,
        validation_status="valid" if checksum_valid else "invalid",
        validation=(
            ValidationCheck(
                rule="de_iban_structure",
                dimension="structure",
                passed=structure_valid,
                details="DE country code followed by 20 digits",
            ),
            ValidationCheck(
                rule="iban_mod_97",
                dimension="checksum",
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
        end=match.end("number"),
        kind="tax_number",
        value=value,
        normalized_value=normalized,
        validation_status="plausible" if plausible_length else "invalid",
        validation=(
            ValidationCheck(
                rule="de_tax_number_length",
                dimension="structure",
                passed=plausible_length,
                details=(
                    "10 or 11 state-schema digits, or 13 unified "
                    "federal digits"
                ),
            ),
            ValidationCheck(
                rule="de_tax_number_state_checksum",
                dimension="checksum",
                passed=None,
                details=(
                    "Requires the federal state and applicable "
                    "check-digit procedure"
                ),
            ),
        ),
    )


def _money_match(match: re.Match[str]) -> _EntityMatch:
    value = match.group(0).strip()
    raw_amount = match.group("amount")
    negative = bool(
        match.groupdict().get("sign")
        or match.groupdict().get("trailing_sign")
    )
    decimal_places = (
        len(raw_amount.rsplit(",", 1)[1]) if "," in raw_amount else 0
    )
    try:
        amount = Decimal(
            raw_amount.replace(".", "").replace(" ", "").replace(",", ".")
        )
        if negative:
            amount = -amount
        syntax_valid = decimal_places <= 2
        normalized = f"{amount:.2f} EUR" if syntax_valid else f"{amount:f} EUR"
    except InvalidOperation:
        syntax_valid = False
        normalized = value.upper()
    return _EntityMatch(
        start=match.start(),
        end=match.end(),
        kind="money",
        value=value,
        normalized_value=normalized,
        validation_status="plausible" if syntax_valid else "invalid",
        validation=(
            ValidationCheck(
                rule="de_money_notation",
                dimension="syntax",
                passed=syntax_valid,
                details=(
                    "German decimal notation with EUR, Euro, or euro sign"
                ),
            ),
            ValidationCheck(
                rule="money_semantic_role",
                dimension="semantic",
                passed=None,
                details=(
                    "The amount's accounting role is not inferred from "
                    "notation alone"
                ),
            ),
        ),
    )


def _date_match(match: re.Match[str], *, numeric_month: bool) -> _EntityMatch:
    value = match.group(0).strip()
    day = int(match.group("day"))
    month_text = match.group("month")
    month = int(month_text) if numeric_month else _MONTHS[month_text.casefold()]
    year_text = match.group("year")
    if len(year_text) == 2:
        calendar_valid = _calendar_date_valid(2000, month, day)
        status = "plausible" if calendar_valid else "invalid"
        normalized = f"{day:02d}.{month:02d}.{year_text}"
        year_check = None
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
        end=match.end(),
        kind="date",
        value=value,
        normalized_value=normalized,
        validation_status=status,
        validation=(
            ValidationCheck(
                rule="gregorian_calendar_date",
                dimension="structure",
                passed=calendar_valid,
                details="Day and month form a possible calendar date",
            ),
            ValidationCheck(
                rule="unambiguous_year",
                dimension="semantic",
                passed=year_check,
                details=year_details,
            ),
        ),
    )


def _iso_date_match(match: re.Match[str]) -> _EntityMatch:
    value = match.group(0)
    year, month, day = (
        int(match.group(name)) for name in ("year", "month", "day")
    )
    calendar_valid = _calendar_date_valid(year, month, day)
    return _EntityMatch(
        start=match.start(),
        end=match.end(),
        kind="date",
        value=value,
        normalized_value=f"{year:04d}-{month:02d}-{day:02d}",
        validation_status="valid" if calendar_valid else "invalid",
        validation=(
            ValidationCheck(
                rule="iso_8601_calendar_date",
                dimension="structure",
                passed=calendar_valid,
                details=(
                    "ISO-style date with a valid Gregorian calendar day"
                ),
            ),
        ),
    )


def _postal_code_match(match: re.Match[str]) -> _EntityMatch:
    value = match.group("postal_code")
    return _postal_entity(
        value,
        match.start("postal_code"),
        match.end("postal_code"),
    )


def _postal_entity(value: str, start: int, end: int) -> _EntityMatch:
    return _EntityMatch(
        start=start,
        end=end,
        kind="postal_code",
        value=value,
        normalized_value=value,
        validation_status="plausible",
        validation=(
            ValidationCheck(
                rule="de_postal_code_shape",
                dimension="structure",
                passed=True,
                details=(
                    "Five digits in an explicit postal-code or address context"
                ),
            ),
            ValidationCheck(
                rule="de_postal_code_directory",
                dimension="external",
                passed=None,
                details="No licensed local postal directory was configured",
            ),
        ),
    )


def _adjacent_right_pairs(
    blocks: list[TextBlock],
    layout: LayoutConfig,
) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for left_index in range(len(blocks) - 1):
        right_index = left_index + 1
        left, right = blocks[left_index], blocks[right_index]
        if (
            left.position
            and right.position
            and is_right_neighbor(left.position, right.position, layout)
        ):
            pairs.append((left_index, right_index))
    return pairs


def _money_fragment_pairs(
    blocks: list[TextBlock],
    layout: LayoutConfig,
) -> list[tuple[int, int]]:
    fragment_layout = LayoutConfig(
        minimum_vertical_overlap_ratio=layout.minimum_vertical_overlap_ratio,
        maximum_right_gap_line_heights=(
            layout.maximum_fragment_gap_line_heights
        ),
        maximum_fragment_gap_line_heights=(
            layout.maximum_fragment_gap_line_heights
        ),
        maximum_below_gap_line_heights=(
            layout.maximum_below_gap_line_heights
        ),
        maximum_below_start_offset_line_heights=(
            layout.maximum_below_start_offset_line_heights
        ),
    )
    pairs: list[tuple[int, int]] = []

    for first_index, first in enumerate(blocks):
        if first.position is None:
            continue
        for second_index in range(first_index + 1, len(blocks)):
            second = blocks[second_index]
            if second.position is None:
                continue
            if _split_money_match(first.text, second.text) is None:
                continue

            if first.position.x0 is None or second.position.x0 is None:
                continue
            left_index, right_index = (
                (first_index, second_index)
                if first.position.x0 <= second.position.x0
                else (second_index, first_index)
            )
            left = blocks[left_index]
            right = blocks[right_index]
            assert left.position is not None
            assert right.position is not None
            if is_right_neighbor(
                left.position,
                right.position,
                fragment_layout,
            ) and not _has_intervening_block(
                blocks,
                left_index,
                right_index,
            ):
                pairs.append((left_index, right_index))

    return pairs


def _has_intervening_block(
    blocks: list[TextBlock],
    left_index: int,
    right_index: int,
) -> bool:
    left = blocks[left_index].position
    right = blocks[right_index].position
    if left is None or right is None or None in (
        left.x1,
        left.y0,
        left.y1,
        right.x0,
        right.y0,
        right.y1,
    ):
        return True

    assert left.x1 is not None
    assert left.y0 is not None
    assert left.y1 is not None
    assert right.x0 is not None
    assert right.y0 is not None
    assert right.y1 is not None

    row_top = max(left.y0, right.y0)
    row_bottom = min(left.y1, right.y1)
    for block_index, block in enumerate(blocks):
        position = block.position
        if block_index in {left_index, right_index} or position is None:
            continue
        if None in (position.x0, position.x1, position.y0, position.y1):
            continue

        assert position.x0 is not None
        assert position.x1 is not None
        assert position.y0 is not None
        assert position.y1 is not None
        between = position.x0 >= left.x1 and position.x1 <= right.x0
        overlaps_row = position.y0 < row_bottom and position.y1 > row_top
        if between and overlaps_row:
            return True

    return False


def _split_money_match(left: str, right: str) -> _EntityMatch | None:
    left_text, right_text = left.strip(), right.strip()
    if (
        _AMOUNT_ONLY_PATTERN.fullmatch(left_text)
        and _CURRENCY_ONLY_PATTERN.fullmatch(right_text)
    ) or (
        _CURRENCY_ONLY_PATTERN.fullmatch(left_text)
        and _AMOUNT_ONLY_PATTERN.fullmatch(right_text)
    ):
        matches = _find_matches(f"{left_text} {right_text}")
        return next((match for match in matches if match.kind == "money"), None)
    return None


def _split_postal_match(label: str, value: str) -> _EntityMatch | None:
    label_text = label.strip().rstrip(":").strip()
    value_text = value.strip()
    if (
        _POSTAL_LABEL_PATTERN.fullmatch(label_text)
        and re.fullmatch(r"\d{5}", value_text)
    ):
        return _postal_entity(value_text, 0, len(value))
    return None


def _recognition_status(
    validation_status: str,
    confidence: float | None,
    threshold: float,
) -> str:
    if validation_status != "invalid":
        return "recognized"
    if confidence is not None and confidence < threshold:
        return "suspected_ocr_corruption"
    return "recognized_invalid"


def _calendar_date_valid(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _evidence(
    block: TextBlock,
    block_index: int,
    start: int,
    end: int,
) -> AnalysisEvidence:
    return AnalysisEvidence(
        page_number=block.page_number, block_index=block_index,
        text=block.text, source=block.source, confidence=block.confidence,
        position=block.position, start_offset=start, end_offset=end,
    )


def _evidence_from_candidate_value(
    candidate: AnalysisCandidate,
) -> AnalysisEvidence:
    evidence = (
        candidate.evidence[0]
        if candidate.relation == "inline"
        else candidate.evidence[-1]
    )
    return evidence.model_copy(
        update={
            "start_offset": candidate.value_start_offset,
            "end_offset": candidate.value_end_offset,
        }
    )


def _contains_evidence(entity: AnalysisEntity, evidence: AnalysisEvidence) -> bool:
    return any(
        item.page_number == evidence.page_number
        and item.block_index == evidence.block_index
        and item.start_offset == evidence.start_offset
        and item.end_offset == evidence.end_offset
        for item in entity.evidence
    )


def _average_confidence(evidence: list[AnalysisEvidence]) -> float | None:
    confidences = [item.confidence for item in evidence if item.confidence is not None]
    return sum(confidences) / len(confidences) if confidences else None
