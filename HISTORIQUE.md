# Historique — Diamandis RAG

- **2026-03-30** — Première version : 89 articles extraits de .docx (titre/date par Claude Haiku, séparateur `###ARTICLE###`), ChromaDB + Voyage AI `voyage-4`, TOP_K = 15, interface Streamlit qui générait des réponses avec Claude Sonnet. Voyage AI appelé en HTTP direct (`requests`) à cause d'un bug d'authentification du client officiel.
- **Après mars 2026** — Ajout de l'ingestion Gmail et de la segmentation par `###SECTION###` ; l'application devient un outil de récupération pure (plus de génération de réponse), top N 35 par défaut.
- **2026-10-18** — Mémoires de Claude transférées dans `ETAT.md`, `CARTE.md`, `HISTORIQUE.md` et `AGENTS.md`.
