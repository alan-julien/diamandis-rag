"""
query_rag.py
------------
Script CLI pour interroger la BDD ChromaDB depuis un autre dossier.
Usage : python query_rag.py "<requête>" [--k 15]
Sortie : JSON sur stdout, un objet par chunk retrouvé.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import chromadb
import requests
from dotenv import load_dotenv

load_dotenv()

DB_DIR          = Path(__file__).parent / "db"
COLLECTION_NAME = "diamandis_articles"
VOYAGE_MODEL    = "voyage-4"
VOYAGE_URL      = "https://api.voyageai.com/v1/embeddings"


def embed(text: str) -> list[float]:
    api_key = os.getenv("VOYAGE_API_KEY", "").strip()
    if not api_key:
        sys.exit("Erreur : VOYAGE_API_KEY absent de l'environnement.")

    resp = requests.post(
        VOYAGE_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": VOYAGE_MODEL, "input": [text], "input_type": "query"},
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"Voyage AI erreur {resp.status_code} : {resp.text[:200]}")

    return resp.json()["data"][0]["embedding"]


def query(question: str, k: int = 15) -> list[dict]:
    client     = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    embedding = embed(question)
    results   = collection.query(query_embeddings=[embedding], n_results=k)

    chunks = []
    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "contenu": doc,
            "titre":   meta.get("titre", "Sans titre"),
            "date":    meta.get("date",  "Date inconnue"),
            "score":   round(1 - distance, 3),
        })
    return chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interroge la BDD Diamandis RAG")
    parser.add_argument("query",      help="Requête en langage naturel")
    parser.add_argument("--k", type=int, default=15, help="Nombre de chunks retournés (défaut : 15)")
    args = parser.parse_args()

    results = query(args.query, k=args.k)
    print(json.dumps(results, ensure_ascii=False, indent=2))
