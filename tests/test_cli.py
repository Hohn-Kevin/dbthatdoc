import json
from pathlib import Path

from typer.testing import CliRunner

from dbthatdoc.cli import app


SAMPLE = (
    Path(__file__).parent.parent
    / "samples"
    / "invoices"
    / "1"
    / "sample_invoice_1.pdf"
)


def test_normalize_cli_writes_unicode_json() -> None:
    result = CliRunner().invoke(app, ["normalize", str(SAMPLE)])

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["source_file"] == SAMPLE.name
    assert "\u27a2" in output["full_text"]


def test_analyze_cli_exposes_configurable_ocr_psm() -> None:
    result = CliRunner().invoke(app, ["analyze", "--help"])

    assert result.exit_code == 0
    assert "--ocr-psm" in result.stdout
