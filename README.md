# Diamandis RAG

Moteur de recherche sémantique sur les newsletters de Peter Diamandis (Metatrends / Abundance Insider). Permet d'interroger en langage naturel l'ensemble des articles depuis juillet 2024.

## Ce que ça fait

Une interface Streamlit avec deux onglets :

- **Explorer** : pose une question → les articles les plus proches sont retrouvés par similarité vectorielle (Voyage AI) → les chunks sont affichés avec score, titre, date, et peuvent être copiés pour être collés dans un LLM externe
- **Prompts système** : bibliothèque de prompts personnalisables, persistés en JSON, à coller avec les sources récupérées

> L'app est un outil de **retrieval pur** — elle ne génère pas de réponse. C'est l'utilisateur qui colle les sources dans le LLM de son choix avec le prompt système approprié.

## Stack

| Rôle | Outil |
|---|---|
| Interface | Streamlit |
| Embeddings | Voyage AI (`voyage-4`) |
| Base vectorielle | ChromaDB (persistée dans `db/`) |
| Pipeline de construction | Claude Haiku (segmentation des articles) |
| Stockage articles | JSON (`data/parsed/`, non versionné) |

## Architecture

```
Gmail IMAP / fichiers DOCX
  └── fetch_emails.py / parse_docs.py
        └── clean_articles.py         # nettoyage contenu
              └── segment_articles.py # découpe en sections via Claude Haiku
                    └── ingest.py     # embeddings Voyage AI → ChromaDB

app.py                                # interface Streamlit (Voyage AI uniquement)
```

Les prompts système sont persistés dans `data/system_prompts.json`.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

### Pour lancer l'application uniquement

Seule `VOYAGE_API_KEY` est nécessaire :

```
VOYAGE_API_KEY=...
```

### Pour mettre à jour la base (fetch emails)

Variables supplémentaires requises :

```
ANTHROPIC_API_KEY=...           # utilisé par Claude Haiku pour segmenter les articles
GMAIL_ADDRESS=...
GMAIL_APP_PASSWORD=...          # mot de passe d'application Gmail, pas le principal
GMAIL_FOLDER=INBOX
DIAMANDIS_SENDER_EMAIL=...      # ex: metatrends@substack.com
```

## Lancer l'application

```bash
streamlit run app.py
```

## Mettre à jour la base (nouveaux emails)

```bash
python fetch_emails.py
```

Ce script récupère uniquement les emails non encore traités (registre dans `data/processed_email_ids.json`), les nettoie, les segmente via Claude Haiku et les indexe de façon incrémentale. Ensuite committer `db/` pour mettre à jour Streamlit Cloud.

## Déploiement (Streamlit Cloud)

La base vectorielle (`db/`) est committée dans git (~10 Mo) et servie directement.

Les secrets sont à configurer dans le dashboard Streamlit Cloud : **Settings → Secrets**. Seule `VOYAGE_API_KEY` est obligatoire pour l'app.

## Sources de données

| Fichier DOCX | Période couverte |
|---|---|
| `1. blog mails - 24-07 - 25-07.docx` | Juillet 2024 → Juillet 2025 |
| `2. blog mails - 25-08 - 25-12.docx` | Août → Décembre 2025 |
| `3. blog mails - 26-01 - 26-03.docx` | Janvier → Mars 2026 |

Les emails suivants sont récupérés directement depuis Gmail via IMAP.
