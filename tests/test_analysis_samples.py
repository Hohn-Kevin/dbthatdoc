from collections import Counter
import json
from pathlib import Path

from dbthatdoc.models import AnalysisEntity
from dbthatdoc.pipeline import analyze_file


SAMPLES_DIR = Path(__file__).parent.parent / "samples"
EMBEDDED_PDFS = tuple(sorted(
    path
    for path in SAMPLES_DIR.glob("*/*/*.pdf")
    if not path.stem.endswith("_scan")
))
GROUND_TRUTH = json.loads(
    (Path(__file__).parent / "fixtures" / "analysis_ground_truth.json")
    .read_text(encoding="utf-8")
)


def _signature(entity: AnalysisEntity) -> tuple[object, ...]:
    return (
        entity.id,
        entity.kind,
        entity.normalized_value,
        entity.validation_status,
        tuple(entity.roles),
        tuple(
            (check.rule, check.dimension, check.passed)
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


def test_all_sample_pairs_match_fixed_entity_ground_truth() -> None:
    assert set(GROUND_TRUTH) == {
        path.relative_to(SAMPLES_DIR).as_posix()
        for path in EMBEDDED_PDFS
    }

    true_positives = false_positives = false_negatives = 0
    metrics_by_kind: dict[str, Counter[str]] = {}

    for embedded_path in EMBEDDED_PDFS:
        relative_path = embedded_path.relative_to(SAMPLES_DIR).as_posix()
        expected = {
            (kind, value, status, tuple(roles))
            for kind, value, status, roles in GROUND_TRUTH[relative_path]
        }

        for path in (
            embedded_path,
            embedded_path.with_name(f"{embedded_path.stem}_scan.pdf"),
        ):
            actual = {
                (
                    entity.kind,
                    entity.normalized_value,
                    entity.validation_status,
                    tuple(entity.roles),
                )
                for entity in analyze_file(path).entities
            }
            true_positives += len(actual & expected)
            false_positives += len(actual - expected)
            false_negatives += len(expected - actual)
            for kind in {item[0] for item in actual | expected}:
                metrics = metrics_by_kind.setdefault(kind, Counter())
                actual_kind = {item for item in actual if item[0] == kind}
                expected_kind = {item for item in expected if item[0] == kind}
                metrics["tp"] += len(actual_kind & expected_kind)
                metrics["fp"] += len(actual_kind - expected_kind)
                metrics["fn"] += len(expected_kind - actual_kind)

    precision = true_positives / (true_positives + false_positives)
    recall = true_positives / (true_positives + false_negatives)

    assert precision == 1.0
    assert recall == 1.0
    assert metrics_by_kind
    for metrics in metrics_by_kind.values():
        kind_precision = metrics["tp"] / (metrics["tp"] + metrics["fp"])
        kind_recall = metrics["tp"] / (metrics["tp"] + metrics["fn"])
        assert kind_precision == 1.0
        assert kind_recall == 1.0
