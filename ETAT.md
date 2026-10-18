# État — Diamandis RAG

*Mis à jour le 2026-10-18.*

## Avancement
Moteur de recherche sémantique fonctionnel (récupération pure, sans génération de réponse), déployé sur Streamlit Cloud, interrogeable en ligne de commande avec `query_rag.py`.

## Prochaines étapes
1. Ingérer les nouveaux articles avec `fetch_emails.py`, puis committer `db/` pour redéployer.

## À vérifier avant de tester
L'état de `db/` et la validité de la clé Voyage AI (`VOYAGE_API_KEY` dans `.env`).
