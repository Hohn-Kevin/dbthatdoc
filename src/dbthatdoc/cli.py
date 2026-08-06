from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Annotated

import typer

from dbthatdoc.pipeline import analyze_file, inspect_file
from dbthatdoc.normalization import normalize_extraction

app = typer.Typer(
    name="dbthatdoc",
    help="Lokale Informationsgewinnung aus Dateien und Medien.",
    no_args_is_help=True,
)

@app.callback()
def main() -> None:
    """dbthatdoc verarbeitet Dateien und Medien lokal."""

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


@app.command()
def inspect(
    file_path: Annotated[
        Path,
        typer.Argument(
            help="Pfad zu der zu untersuchenden Datei.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    pretty: Annotated[
        bool,
        typer.Option(
            "--pretty/--compact",
            help="JSON formatiert oder kompakt ausgeben.",
        ),
    ] = True,
    ocr_psm: Annotated[
        int,
        typer.Option(
            "--ocr-psm",
            min=0,
            max=13,
            help="Tesseract-Seitensegmentierungsmodus fuer OCR.",
        ),
    ] = 3,
) -> None:
    """Untersucht eine Datei und gibt das Ergebnis als JSON aus."""

    try:
        result = inspect_file(
            file_path,
            ocr_page_segmentation_mode=ocr_psm,
        )
    except (FileNotFoundError, ValueError) as error:
        typer.echo(f"Fehler: {error}", err=True)
        raise typer.Exit(code=1) from error
    except Exception as error:
        typer.echo(
            f"Die Datei konnte nicht verarbeitet werden: {error}",
            err=True,
        )
        raise typer.Exit(code=2) from error

    output = result.model_dump(mode="json")

    typer.echo(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2 if pretty else None,
        )
    )

@app.command()
def normalize(
    file_path: Path,
    ocr_psm: Annotated[
        int,
        typer.Option("--ocr-psm", min=0, max=13),
    ] = 3,
) -> None:
    """Extrahiert eine Datei und gibt die normalisierte Struktur aus."""

    result = inspect_file(
        file_path,
        ocr_page_segmentation_mode=ocr_psm,
    )
    content = normalize_extraction(result)

    typer.echo(
        json.dumps(
            content.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command()
def analyze(
    file_path: Path,
    ocr_psm: Annotated[
        int,
        typer.Option("--ocr-psm", min=0, max=13),
    ] = 3,
) -> None:
    """Analysiert die normalisierte Struktur einer Datei."""

    result = analyze_file(
        file_path,
        ocr_page_segmentation_mode=ocr_psm,
    )

    typer.echo(
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
