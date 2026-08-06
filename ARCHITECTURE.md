# dbthatdoc Architecture

## Purpose

dbthatdoc is a local-first platform for document analysis.

The goal is to process, analyze, classify, and search documents while keeping document data inside the user's local environment.

## Core Principles

### Local First

All required processing should happen locally. The project should not require mandatory cloud services or external document processing.

### Modular Design

Individual processing components should be replaceable without redesigning the entire system.

Examples include:

- OCR engines
- Text extraction methods
- Classification models
- Storage backends
- Embedding models

### Explicit Processing Steps

Document processing should be understandable and inspectable. Each stage should have a clear input, output, and responsibility.

## Processing Pipeline

```text
Document Input
       |
       v
Document Detection
       |
       +----------------------+
       |                      |
       v                      v
Native PDF Text          Image Processing
       |                      |
       |                      v
       |                  OCR Engine
       |                      |
       +----------------------+
                  |
                  v
           Text Processing
                  |
                  v
          Document Analysis
                  |
                  v
           Classification
                  |
                  v
          Semantic Indexing
```

## Components

### Document Input

Supported document sources may include:

- PDF files
- Images
- Future document formats

### Text Extraction

The extraction priority is:

1. Extract existing embedded document text.
2. Use OCR as a fallback for image-based documents.

### OCR Layer

OCR functionality should be implemented through replaceable backends.

Possible engines include:

- Tesseract OCR
- PaddleOCR

### Document Analysis

Analysis consumes normalized `DocumentContent` and produces explicit candidates
rather than modifying extraction or normalization results. Each candidate retains
its source block indices, page, extraction source, source confidence, and
position so
downstream classification and entity extraction can inspect its evidence.

`source_confidence` describes only the underlying extraction or OCR evidence;
it is not confidence in an Analysis interpretation. Inline colon-separated
observations are exposed as `colon_structure`, including sentence-like prose.
Positioned label/value observations are exposed as `spatial_key_value`. Both
remain candidates rather than asserted semantic facts.

Analyzers are replaceable components. The initial analyzer identifies generic
key-value structures from inline separators and nearby positioned blocks; it
does not encode document types, field names, or sample-specific vocabulary.
Spatial relationships use configurable distances relative to the observed line
height. Entity analysis does not concatenate arbitrary neighboring blocks: it
only composes adjacent same-line fragments for complementary amount/currency
tokens or an explicit postal-code label followed by five digits.

German document entities are a separate, locale-specific analysis component.
It normalizes IBANs, tax numbers, monetary values, and dates and reports each
result as `valid`, `plausible`, or `invalid`. `Plausible` is intentionally
different from `valid`: for example, a German tax number can have an accepted
length while its state-specific check-digit procedure remains unknown.

Role-bearing candidates can also produce party entities. A German owner label
such as `Inh.` may associate a name-like value with the `owner` role, but the
entity remains `plausible` because document context cannot prove a real-world
identity by itself.

Repeated normalized entities are represented once with multiple evidence
locations. Raw key-value candidates reference entities found in their source
blocks, allowing later role and identity resolution without discarding the
original document text.
Evidence and candidates carry exact character offsets. A candidate references
an entity only when its value span overlaps exactly one entity span; ambiguous
multi-entity values remain unlinked rather than claiming a false association.
Offsets are always relative to the `text` of their individual evidence block;
they are neither page-global nor document-global positions.

Validation checks declare whether they concern syntax, structure, checksum,
semantics, or external reference data. Recognition is recorded separately:
an invalid high-confidence observation remains recognized-but-invalid, while
an invalid low-confidence OCR observation is marked as suspected OCR damage.
Money notation alone is therefore plausible, not valid, because it does not
establish the amount's accounting meaning.

Party observations distinguish `person`, `organization`, and `unresolved`
forms. Organization structure permits common legal forms, punctuation such as
`&`, and digits. The form is still a structural classification rather than
proof of legal identity.

Layout distances and the OCR-corruption confidence boundary are configurable
technical heuristics. They are defaults for the current rule-based analyzer,
not calibrated probabilities or universally valid document measurements.

Entity IDs are deterministic fingerprints of entity type and normalized value.
Separate analysis runs can therefore reference the same normalized observation
without exposing its clear value in the ID. For parties, this links equal name
observations only; it does not assert that two real people with the same name
are identical. The fingerprints are not anonymization and must not be treated
as privacy-preserving identifiers for predictable value domains.

The initial German rules follow primary public references:

- [German IBAN structure (Deutsche Bundesbank)](https://www.bundesbank.de/de/aufgaben/unbarer-zahlungsverkehr/serviceangebot/iban-regeln)
- [German tax-number schemas (ELSTER)](https://www.elster.de/eportal/helpGlobal?themaGlobal=wo_ist_meine_steuernummer)
- [State-specific tax-number checks (ELSTER)](https://download.elster.de/download/schnittstellen/Pruefung_der_Steuer_und_Steueridentifikatsnummer.pdf)

German postal codes are `plausible` only when five digits occur in an explicit
postal-code field or address context. The core does not claim directory-level
validity: complete original postal data is licensed by Deutsche Post, BKG
access is restricted, and the public Destatis municipality directory contains
the postal code of the administrative seat rather than a complete delivery
directory. A licensed local directory can be added later as an optional
validator without introducing a network requirement.

The sample regression matrix compares semantic entity signatures across all
11 embedded/scan pairs and against a fixed reviewed ground-truth fixture,
reporting global and per-entity-kind precision and recall. It also requires
every entity kind and
validation rule to occur in at least two document families. This development
set is supplemented by synthetic boundary and counterexample tests; it is not
an independent holdout corpus.

- [Postal reference data (Deutsche Post)](https://www.deutschepost.de/de/d/deutsche-post-direkt/datafactory.html)
- [Licensed postal-code areas (BKG)](https://gdz.bkg.bund.de/index.php/default/wfs-postleitzahlgebiete-wfs-plz.html)
- [Municipality directory scope (Destatis)](https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/_inhalt.html)

### Semantic Layer

Documents may be represented using embeddings after text has been extracted and normalized.

Potential use cases include:

- Semantic document search
- Similar document detection
- Document clustering
- Automated classification

### Storage

All processed data should remain local.

Possible storage solutions include:

- SQLite
- Local vector databases
- File-based storage

## Non-Goals

dbthatdoc is currently not intended to be:

- A cloud OCR service
- A complete document management system
- A mandatory AI assistant

Additional functionality may be added in future versions.
