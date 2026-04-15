"""
fetch_emails.py
---------------
Pipeline email complet : récupère les emails Diamandis non traités depuis
Gmail (IMAP), les nettoie, les segmente via Claude Haiku, les ingère
dans ChromaDB en mode incrémental, et met à jour le registre des emails traités.

Prérequis :
  - Variables dans .env :
      ANTHROPIC_API_KEY        clé Claude
      VOYAGE_API_KEY           clé Voyage AI
      DIAMANDIS_SENDER_EMAIL   adresse expéditeur à filtrer (ex: metatrends@substack.com)
      GMAIL_ADDRESS            adresse Gmail cible
      GMAIL_APP_PASSWORD       mot de passe d'application Gmail (pas le mot de passe principal)

Usage :
    python fetch_emails.py
"""

import email as email_lib
import imaplib
import json
import os
import re
import unicodedata
from pathlib import Path

import html2text
from anthropic import Anthropic
from dotenv import load_dotenv

from clean_articles import clean_content
from ingest import ingest_articles
from segment_articles import segment_article

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
PROCESSED_IDS_FILE = Path("data/processed_email_ids.json")
SENDER_EMAIL       = os.getenv("DIAMANDIS_SENDER_EMAIL", "").strip().lower()
GMAIL_ADDRESS      = os.getenv("GMAIL_ADDRESS", "").strip()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()
GMAIL_FOLDER       = os.getenv("GMAIL_FOLDER", "INBOX").strip()


# ── Registre des emails traités ───────────────────────────────────────────────

def load_processed_ids() -> set:
    if PROCESSED_IDS_FILE.exists():
        data = json.loads(PROCESSED_IDS_FILE.read_text(encoding="utf-8"))
        return set(data.get("processed", []))
    return set()


def save_processed_ids(ids: set):
    PROCESSED_IDS_FILE.write_text(
        json.dumps({"processed": sorted(ids)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Conversion HTML → texte ───────────────────────────────────────────────────

def html_to_text(html: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links   = True
    h.ignore_images  = True
    h.body_width     = 0
    return h.handle(html)


# ── Utilitaires ───────────────────────────────────────────────────────────────

def slugify(text: str, n: int = 8) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s]", "", text).strip().lower()
    text = re.sub(r"\s+", "_", text)
    return text[:n]


# ── Fetch Gmail (IMAP) ────────────────────────────────────────────────────────

def fetch_new_emails(processed_ids: set) -> tuple[list[dict], list[str]]:
    """
    Se connecte à Gmail via IMAP, retourne :
    - la liste des emails bruts non encore traités
    - la liste de leurs Message-IDs
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_ADDRESS et GMAIL_APP_PASSWORD doivent être définis dans .env")

    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    imap.select(GMAIL_FOLDER)

    search_criteria = "ALL"
    if SENDER_EMAIL:
        search_criteria = f'FROM "{SENDER_EMAIL}"'

    _, data = imap.search(None, search_criteria)
    msg_nums = data[0].split()
    print(f"  {len(msg_nums)} email(s) trouvé(s) dans {GMAIL_FOLDER}")

    new_emails = []
    new_ids    = []

    for num in msg_nums:
        _, msg_data = imap.fetch(num, "(RFC822)")
        raw = msg_data[0][1]
        msg = email_lib.message_from_bytes(raw)

        message_id = (msg.get("Message-ID") or "").strip()
        if not message_id:
            message_id = f"num_{num.decode()}"

        if message_id in processed_ids:
            continue

        subject  = email_lib.header.decode_header(msg.get("Subject", "Sans titre"))
        subject  = "".join(
            part.decode(enc or "utf-8") if isinstance(part, bytes) else part
            for part, enc in subject
        ).strip()

        date_str = msg.get("Date", "")
        try:
            from email.utils import parsedate_to_datetime
            date_str = parsedate_to_datetime(date_str).strftime("%Y-%m-%d")
        except Exception:
            date_str = "0000-00-00"

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/html":
                    body = html_to_text(part.get_payload(decode=True).decode("utf-8", errors="replace"))
                    break
                elif ct == "text/plain" and not body:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                ct = msg.get_content_type()
                text = payload.decode("utf-8", errors="replace")
                body = html_to_text(text) if ct == "text/html" else text

        new_emails.append({"entry_id": message_id, "subject": subject, "date": date_str, "body": body})
        new_ids.append(message_id)

    imap.logout()
    return new_emails, new_ids


# ── Construction de l'article ─────────────────────────────────────────────────

def build_article(email: dict) -> dict:
    slug = slugify(email["subject"])
    return {
        "id":          f"email_{email['date']}_{slug}",
        "source_file": "gmail",
        "titre":       email["subject"],
        "date":        email["date"],
        "contenu":     email["body"],
    }


# ── Pipeline principal ────────────────────────────────────────────────────────

def main():
    if not SENDER_EMAIL:
        print("⚠  DIAMANDIS_SENDER_EMAIL non défini — tous les emails du dossier seront traités.")

    processed_ids = load_processed_ids()
    print(f"Emails déjà traités : {len(processed_ids)}")

    print(f"Connexion à Gmail (dossier : {GMAIL_FOLDER})...")
    raw_emails, new_entry_ids = fetch_new_emails(processed_ids)

    if not raw_emails:
        print("Aucun nouvel email à traiter.")
        return

    print(f"{len(raw_emails)} nouvel(s) email(s) trouvé(s)\n")

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not anthropic_key:
        raise RuntimeError("ANTHROPIC_API_KEY introuvable dans .env")
    client = Anthropic(api_key=anthropic_key)

    articles_to_ingest = []
    skipped_empty      = []

    for i, email in enumerate(raw_emails, 1):
        print(f"[{i}/{len(raw_emails)}] {email['subject'][:60]}")

        article = build_article(email)
        article["contenu"] = clean_content(article["contenu"], article["titre"])

        if not article["contenu"].strip():
            print("  ⚠ Contenu vide après nettoyage — ignoré")
            skipped_empty.append(email["entry_id"])
            continue

        print("  Segmentation (Haiku)...")
        contenu_seg, nb = segment_article(article, client)
        article["contenu"] = contenu_seg
        print(f"  ✓ {nb} section(s)")

        articles_to_ingest.append(article)

    if not articles_to_ingest:
        print("\nAucun article à ingérer (tous vides après nettoyage).")
    else:
        print(f"\nIngestion de {len(articles_to_ingest)} article(s) dans ChromaDB...")
        n_chunks = ingest_articles(articles_to_ingest, incremental=True)

    # Mise à jour du registre
    processed_ids.update(new_entry_ids)
    save_processed_ids(processed_ids)

    print(f"\n{'='*50}")
    print(f"  Pipeline terminé !")
    print(f"  Emails traités   : {len(raw_emails)}")
    if articles_to_ingest:
        print(f"  Articles ingérés : {len(articles_to_ingest)}")
        print(f"  Chunks ajoutés   : {n_chunks}")
    if skipped_empty:
        print(f"  Emails ignorés   : {len(skipped_empty)} (contenu vide)")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
