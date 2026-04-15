"""
ingest.py
---------
Charge data/parsed/all_articles_segmented.json, découpe chaque article en
chunks (sections délimitées par ###SECTION###), génère les embeddings via
l'API Voyage AI (modèle voyage-4) en HTTP direct et les indexe dans ChromaDB.

Métadonnées stockées : titre, date, source_file, article_id, chunk_index, n_chunks.
Progression affichée chunk par chunk avec numéro et titre.
"""

import json
import os
import time
from pathlib import Path

import chromadb
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────
PARSED_FILE     = Path("data/parsed/all_articles_segmented.json")
DB_DIR          = Path("db")
COLLECTION_NAME = "diamandis_articles"
VOYAGE_MODEL    = "voyage-4"
VOYAGE_URL      = "https://api.voyageai.com/v1/embeddings"
BATCH_SIZE      = 8
MAX_RETRIES     = 3


def _get_api_key() -> str:
    key = os.getenv("VOYAGE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "VOYAGE_API_KEY introuvable. "
            "Vérifie que la clé est bien définie dans .env"
        )
    return key


# ── 1. Chargement et découpage en chunks ──────────────────────────────────────

def load_articles(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def split_into_chunks(article: dict) -> list[dict]:
    """
    Découpe un article en chunks sur le marqueur ###SECTION###.
    Chaque chunk hérite des métadonnées de l'article + chunk_index / n_chunks.
    """
    parts = article["contenu"].split("###SECTION###")
    parts = [p.strip() for p in parts if p.strip()]
    n = len(parts)
    return [
        {
            "id":          f"{article['id']}_s{i:03d}",
            "article_id":  article["id"],
            "titre":       article.get("titre")       or "",
            "date":        article.get("date")        or "",
            "source_file": article.get("source_file") or "",
            "chunk_index": i,
            "n_chunks":    n,
            "contenu":     part,
        }
        for i, part in enumerate(parts)
    ]


# ── 2. Embeddings via HTTP (pas de client voyageai) ───────────────────────────

def embed_batch(texts: list[str], api_key: str) -> list[list[float]]:
    """
    Appelle directement l'endpoint REST Voyage AI.
    Renvoie une liste d'embeddings (floats).
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model":      VOYAGE_MODEL,
        "input":      texts,
        "input_type": "document",   # optimisé pour l'indexation RAG
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(VOYAGE_URL, headers=headers, json=payload, timeout=60)

            if resp.status_code == 200:
                data = resp.json()
                # L'API renvoie {"data": [{"embedding": [...], "index": 0}, ...]}
                items = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in items]

            # Erreur HTTP explicite
            raise RuntimeError(
                f"HTTP {resp.status_code} — {resp.text[:200]}"
            )

        except RuntimeError:
            raise   # on ne retente pas les erreurs HTTP (clé invalide, quota…)
        except Exception as exc:
            print(f"\n    [tentative {attempt}/{MAX_RETRIES}] {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(2)

    raise RuntimeError(f"Échec de l'embedding après {MAX_RETRIES} tentatives.")


def embed_all(chunks: list[dict], api_key: str) -> list[list[float]]:
    """Génère les embeddings par lots avec progression chunk par chunk."""
    all_embeddings: list[list[float]] = []
    total = len(chunks)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = chunks[batch_start : batch_start + BATCH_SIZE]

        for i, chunk in enumerate(batch):
            num   = batch_start + i + 1
            titre = (chunk.get("titre") or "sans titre")[:45]
            ci    = chunk["chunk_index"] + 1
            cn    = chunk["n_chunks"]
            print(f"  [{num:>3}/{total}] {titre}  §{ci}/{cn}")

        texts      = [c["contenu"] for c in batch]
        embeddings = embed_batch(texts, api_key)
        all_embeddings.extend(embeddings)

    return all_embeddings


# ── 3. Indexation ChromaDB ────────────────────────────────────────────────────

def _get_or_create_collection(chroma: chromadb.PersistentClient) -> chromadb.Collection:
    try:
        return chroma.get_collection(COLLECTION_NAME)
    except Exception:
        return chroma.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )


def ingest_articles(articles: list[dict], incremental: bool = True) -> int:
    """
    Indexe une liste d'articles (déjà segmentés avec ###SECTION###) dans ChromaDB.

    - incremental=True  : ouvre la collection existante, ne réindexe pas les chunks
                          déjà présents (identifiés par leur id). Retourne le nombre
                          de nouveaux chunks ajoutés.
    - incremental=False : supprime et recrée la collection (full reindex).

    Retourne le nombre de chunks effectivement ingérés.
    """
    api_key = _get_api_key()

    # Découpage en chunks
    chunks = []
    for article in articles:
        chunks.extend(split_into_chunks(article))

    if not chunks:
        print("Aucun chunk à indexer.")
        return 0

    chroma = chromadb.PersistentClient(path=str(DB_DIR))

    if incremental:
        collection = _get_or_create_collection(chroma)
        # Filtrer les chunks déjà présents
        existing = collection.get(ids=[c["id"] for c in chunks])
        existing_ids = set(existing["ids"])
        new_chunks = [c for c in chunks if c["id"] not in existing_ids]
        skipped = len(chunks) - len(new_chunks)
        if skipped:
            print(f"  {skipped} chunk(s) déjà présents — ignorés.")
    else:
        try:
            chroma.delete_collection(COLLECTION_NAME)
            print(f"  Collection '{COLLECTION_NAME}' existante supprimée.")
        except Exception:
            pass
        collection = chroma.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        new_chunks = chunks

    if not new_chunks:
        print("Aucun nouveau chunk à ajouter.")
        return 0

    # Embeddings
    print(f"Génération des embeddings ({len(new_chunks)} chunks · Voyage AI · {VOYAGE_MODEL}) :")
    embeddings = embed_all(new_chunks, api_key)
    print(f"\n  {len(embeddings)} embeddings générés ✓")

    # Indexation par lots
    ids       = [c["id"] for c in new_chunks]
    documents = [c["contenu"] for c in new_chunks]
    metadatas = [
        {
            "titre":       c["titre"],
            "date":        c["date"],
            "source_file": c["source_file"],
            "article_id":  c["article_id"],
            "chunk_index": c["chunk_index"],
            "n_chunks":    c["n_chunks"],
        }
        for c in new_chunks
    ]

    for batch_start in range(0, len(new_chunks), BATCH_SIZE):
        sl = slice(batch_start, batch_start + BATCH_SIZE)
        collection.add(
            ids=ids[sl],
            documents=documents[sl],
            embeddings=embeddings[sl],
            metadatas=metadatas[sl],
        )

    return len(new_chunks)


def ingest():
    """Full reindex depuis data/parsed/all_articles_segmented.json."""
    print(f"Chargement de {PARSED_FILE}...")
    articles = load_articles(PARSED_FILE)
    print(f"  {len(articles)} articles chargés\n")

    n = ingest_articles(articles, incremental=False)

    chroma = chromadb.PersistentClient(path=str(DB_DIR))
    collection = _get_or_create_collection(chroma)

    print(f"\n{'='*50}")
    print(f"  Indexation terminée !")
    print(f"  Collection : '{COLLECTION_NAME}'")
    print(f"  Chunks     : {collection.count()}")
    print(f"  Articles   : {len(articles)}")
    print(f"  Modèle     : {VOYAGE_MODEL}")
    print(f"  Distance   : cosinus")
    print(f"{'='*50}")


if __name__ == "__main__":
    ingest()
