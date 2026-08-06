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
