from collections import Counter
from pathlib import Path

from dbthatdoc.models import AnalysisEntity
from dbthatdoc.pipeline import analyze_file


SAMPLES_DIR = Path(__file__).parent.parent / "samples"
EMBEDDED_PDFS = tuple(sorted(
    path
    for path in SAMPLES_DIR.glob("*/*/*.pdf")
    if not path.stem.endswith("_scan")
))


def _signature(entity: AnalysisEntity) -> tuple[object, ...]:
    return (
        entity.id,
        entity.kind,
        entity.normalized_value,
        entity.validation_status,
        tuple(entity.roles),
        tuple(
            (check.rule, check.passed)
            for check in entity.validation
        ),
    )


def test_all_sample_pairs_have_identical_semantic_entities() -> None:
    assert len(EMBEDDED_PDFS) == 11
    entity_kind_coverage: Counter[str] = Counter()
    validation_rule_coverage: Counter[str] = Counter()

    for embedded_path in EMBEDDED_PDFS:
        scan_path = embedded_path.with_name(
            f"{embedded_path.stem}_scan.pdf"
        )
        embedded = analyze_file(embedded_path)
        scan = analyze_file(scan_path)
        embedded_signatures = {
            _signature(entity) for entity in embedded.entities
        }
        scan_signatures = {
            _signature(entity) for entity in scan.entities
        }

        assert embedded_signatures == scan_signatures, (
            embedded_path.relative_to(SAMPLES_DIR),
            embedded_signatures - scan_signatures,
            scan_signatures - embedded_signatures,
        )

        document_kinds = {
            entity.kind for entity in embedded.entities
        }
        document_rules = {
            check.rule
            for entity in embedded.entities
            for check in entity.validation
        }
        entity_kind_coverage.update(document_kinds)
        validation_rule_coverage.update(document_rules)

    assert entity_kind_coverage
    assert all(
        document_count >= 2
        for document_count in entity_kind_coverage.values()
    ), entity_kind_coverage
    assert validation_rule_coverage
    assert all(
        document_count >= 2
        for document_count in validation_rule_coverage.values()
    ), validation_rule_coverage
