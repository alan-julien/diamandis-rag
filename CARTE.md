# Carte — Diamandis RAG

## Dans le projet
- `README.md` : présentation (dépôt public).
- `db/` : base ChromaDB (collection `diamandis_articles`, environ 10 Mo), committée.
- `data/` : articles traités, `processed_email_ids.json`, `system_prompts.json`.
- `.env` : clés (`VOYAGE_API_KEY`, et pour la mise à jour : Anthropic, Gmail). Jamais sur Git.
- `query_rag.py` : point d'entrée en ligne de commande.

## En ligne
- Code : https://github.com/alan-julien/diamandis-rag (**public**).
- Application : Streamlit Cloud (secrets dans Settings > Secrets).

## Autour
- Projet parent `..\` (blog) : préparation de conférences avec `/plan-review`, qui interroge cette base.
