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
its source block indices, page, extraction source, confidence, and position so
downstream classification and entity extraction can inspect its evidence.

Analyzers are replaceable components. The initial analyzer identifies generic
key-value structures from inline separators and nearby positioned blocks; it
does not encode document types, field names, or sample-specific vocabulary.

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

Entity IDs are deterministic fingerprints of entity type and normalized value.
Separate analysis runs can therefore reference the same normalized observation
without exposing its clear value in the ID. For parties, this links equal name
observations only; it does not assert that two real people with the same name
are identical.

The initial German rules follow primary public references:

- [German IBAN structure (Deutsche Bundesbank)](https://www.bundesbank.de/de/aufgaben/unbarer-zahlungsverkehr/serviceangebot/iban-regeln)
- [German tax-number schemas (ELSTER)](https://www.elster.de/eportal/helpGlobal?themaGlobal=wo_ist_meine_steuernummer)
- [State-specific tax-number checks (ELSTER)](https://download.elster.de/download/schnittstellen/Pruefung_der_Steuer_und_Steueridentifikatsnummer.pdf)

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
