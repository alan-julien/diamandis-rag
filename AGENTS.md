# AGENTS.md

This file guides AI coding agents (Claude Code, Codex) that work with code in this repository.

## Project overview

Semantic search engine over Peter Diamandis newsletter articles (Metatrends, Abundance Insider). Articles come from Gmail IMAP or DOCX exports. A cleaning and segmentation pipeline processes them, and Voyage AI embeddings index them into ChromaDB. A Streamlit interface retrieves the closest chunks.

The app is a pure retrieval tool: it doesn't generate answers. You copy the retrieved chunks, with a system prompt, into the LLM of your choice.

## Environment setup

```bash
# Activate the virtual environment (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

`.env` variables:

- To run the app: `VOYAGE_API_KEY` only.
- To update the database: also `ANTHROPIC_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `GMAIL_FOLDER`, and `DIAMANDIS_SENDER_EMAIL`.

## Commands

```bash
# Run the Streamlit interface
streamlit run app.py

# Fetch new emails and ingest them incrementally (run locally, then commit db/ to redeploy)
python fetch_emails.py

# Query the database from another folder; prints one JSON object per retrieved chunk
python query_rag.py "<query>" --k 15
```

## Architecture

### Ingestion pipeline

```
Gmail IMAP / DOCX files
  → fetch_emails.py / parse_docs.py
      → clean_articles.py   (strips headers, navigation, disclaimers)
      → segment_articles.py (Claude Haiku inserts ###SECTION### markers)
      → ingest.py           (Voyage AI embeddings → ChromaDB)
```

`data/processed_email_ids.json` tracks processed email IDs to avoid reindexing.

### Query interface (`app.py`)

- **Explorer** tab: query → Voyage AI embedding → ChromaDB retrieval (top N, default 35) → chunks displayed with score, title, and date, ready to copy.
- **Prompts système** tab: library of editable system prompts, persisted in `data/system_prompts.json`.

### Key design decisions

- **Chunking boundary**: `###SECTION###` markers inserted by `segment_articles.py` define chunk splits in `ingest.py`. The first six words of each thematic break identify a section.
- **Fuzzy matching**: section boundary detection progressively relaxes from 6 → 5 → 4 → 3 word matches, with Unicode normalization (curly quotes, dashes, ellipsis variants).
- **Incremental ingest**: `ingest.py` checks existing ChromaDB IDs before indexing, so you can safely run it again.
- **Models**: Claude Haiku (`claude-haiku-4-5-20251001`) segments articles in the pipeline, and Voyage AI `voyage-4` produces embeddings. No model generates answers.
- **Voyage AI**: called through raw `requests` (REST API), not an SDK. Batch size 8, maximum three retries.

## Deployment (Streamlit Cloud)

- `db/` (ChromaDB, about 10 MB) is committed to Git and served as is.
- Set secrets in the Streamlit Cloud dashboard (**Settings > Secrets**). The app requires only `VOYAGE_API_KEY`.
- To update the index, run `fetch_emails.py` locally, then commit and push the updated `db/`.

## Running on Windows

`python` isn't on the PATH, and `chromadb` is installed only in the virtual environment. Use the venv interpreter and force UTF-8 output, or special characters (→, accents) crash the script (cp1252):

```powershell
$ragDir = "C:\Users\Alan_JULIEN\projets\partages\blog\diamandis-rag"
$env:PYTHONIOENCODING = "utf-8"
& "$ragDir\.venv\Scripts\python.exe" "$ragDir\query_rag.py" "<query>" --k 15
```

## Project context

- `ETAT.md`: current state and next steps. Read it at the start of each session; rewrite it at the end.
- `CARTE.md`: where documents and resources live.
- `HISTORIQUE.md`: past decisions and their reasons (read only when needed).
