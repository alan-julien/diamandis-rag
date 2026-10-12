# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

RAG (Retrieval-Augmented Generation) system for querying Peter Diamandis blog articles. Articles come from Gmail IMAP, are processed through a cleaning/segmentation pipeline, indexed into ChromaDB with Voyage AI embeddings, and queried via a Streamlit chat interface backed by Codex Sonnet.

## Environment Setup

```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Required `.env` variables: `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `GMAIL_FOLDER`, `DIAMANDIS_SENDER_EMAIL`.

## Commands

```bash
# Run the chat interface
streamlit run app.py

# Fetch new emails and ingest them incrementally (run locally, then redeploy)
python fetch_emails.py
```

## Architecture

### Email Pipeline

```
Gmail IMAP
  → fetch_emails.py
      → clean_articles.py   (strips headers, navigation, disclaimers)
      → segment_articles.py (Codex Haiku inserts ###SECTION### markers)
      → ingest.py           (Voyage AI embeddings → ChromaDB)
```

Processed email IDs are tracked in `data/processed_email_ids.json` to avoid reindexing.

### Query Interface (`app.py`)

1. User query → Voyage AI embedding
2. ChromaDB retrieval (top 8 chunks, cosine similarity)
3. Context formatted with source metadata
4. Streamed response from `Codex-sonnet-4-20250514` with conversation history

The system prompt instructs Codex to respond in French and cite specific articles.

### Key Design Decisions

- **Chunking boundary**: `###SECTION###` markers inserted by `segment_articles.py` define chunk splits in `ingest.py`. Sections are identified by the first 6 words of each thematic break.
- **Fuzzy matching**: Section boundary detection progressively relaxes from 6 → 5 → 4 → 3 word matches, with Unicode normalization (curly quotes, dashes, ellipsis variants).
- **Incremental ingest**: `ingest.py` checks existing ChromaDB IDs before indexing — safe to re-run.
- **Models**: Codex Haiku for pipeline tasks (segmentation); Codex Sonnet for final generation; Voyage AI `voyage-4` for embeddings.
- **Voyage AI**: Called via raw `requests` (REST API), not an SDK. Batch size 8, max 3 retries.

## Deployment (Streamlit Cloud)

- `db/` (ChromaDB, ~10 Mo) is committed to git and served as-is.
- Secrets (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, etc.) are set in Streamlit Cloud dashboard under Advanced settings → Secrets.
- `fetch_emails.py` is run locally to update the index, then the updated `db/` is committed and pushed to redeploy.

## Prochaines étapes

1. Créer le repo GitHub et pousser le code
2. Déployer sur Streamlit Community Cloud
3. Configurer les secrets dans le dashboard Streamlit
