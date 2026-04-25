# Diamandis RAG

Moteur de recherche sémantique sur les newsletters de Peter Diamandis (Metatrends / Abundance Insider). Permet d'interroger en langage naturel l'ensemble des articles depuis juillet 2024.

## Ce que ça fait

Une interface Streamlit avec deux modes :

- **Exploration RAG** : pose une question → les articles les plus proches sont retrouvés par similarité vectorielle (Voyage AI) → Claude Sonnet génère une réponse sourcée avec citations
- **Prompts système** : gestion de plusieurs prompts système personnalisables, sélectionnables à la volée et persistés en JSON

## Stack

| Rôle | Outil |
|---|---|
| Interface | Streamlit |
| Embeddings | Voyage AI (`voyage-4`) |
| Base vectorielle | ChromaDB (persistée dans `db/`) |
| Génération | Claude Sonnet (`claude-sonnet-4-20250514`) |
| Pipeline emails | Claude Haiku (segmentation) |
| Stockage articles | JSON (`data/parsed/`) |

## Architecture

```
Gmail IMAP / fichiers DOCX
  └── fetch_emails.py / parse_docs.py
        └── clean_articles.py       # nettoyage contenu
              └── segment_articles.py  # découpe en sections via Claude Haiku
                    └── ingest.py       # embeddings Voyage AI → ChromaDB

app.py                               # interface Streamlit
```

Les articles sont stockés à trois stades dans `data/parsed/` :
- `all_articles.json` — brut
- `all_articles_clean.json` — nettoyé
- `all_articles_segmented.json` — découpé en sections (source de vérité pour l'indexation)

Les prompts système sont persistés dans `data/system_prompts.json`.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

Créer un fichier `.env` à la racine :

```
ANTHROPIC_API_KEY=...
VOYAGE_API_KEY=...
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

Ce script récupère uniquement les emails non encore traités (registre dans `data/processed_email_ids.json`), les nettoie, les segmente et les indexe de façon incrémentale. Ensuite committer `db/` et `data/parsed/` pour mettre à jour Streamlit Cloud.

## Déploiement (Streamlit Cloud)

La base vectorielle (`db/`) est committée dans git (~10 Mo) et servie directement.

Les secrets sont à configurer dans le dashboard Streamlit Cloud : **Settings → Secrets**.

`fetch_emails.py` se lance en local pour enrichir la base, puis `db/` est committé et poussé pour redéployer.

## Sources de données

| Fichier DOCX | Période couverte |
|---|---|
| `1. blog mails - 24-07 - 25-07.docx` | Juillet 2024 → Juillet 2025 |
| `2. blog mails - 25-08 - 25-12.docx` | Août → Décembre 2025 |
| `3. blog mails - 26-01 - 26-03.docx` | Janvier → Mars 2026 |

Les emails suivants sont récupérés directement depuis Gmail via IMAP.
