"""
segment_articles.py
-------------------
Détecte les sections thématiques de chaque article via Claude Haiku,
insère le marqueur ###SECTION### dans le champ `contenu`, et sauvegarde
le résultat dans data/parsed/all_articles_segmented.json.

Pipeline par article :
1. Haiku reçoit le contenu et renvoie un JSON avec les 6 premiers mots
   de chaque section (copiés mot pour mot depuis le texte).
2. Python localise chaque début de section dans le texte par string matching.
3. Si un match échoue → retry progressif (5, 4, 3 mots) puis nouvelle
   tentative API (max 3 au total).
4. En cas d'échec définitif → l'article est conservé en 1 seul chunk (log warning).
5. Les marqueurs ###SECTION### sont insérés en tête de chaque section
   (sauf la première, qui est le début naturel de l'article).

Lancement :
    python segment_articles.py
"""

import json
import os
import re
import time
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
INPUT_FILE  = Path("data/parsed/all_articles_clean.json")
OUTPUT_FILE = Path("data/parsed/all_articles_segmented.json")
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_API_RETRIES = 3


# ── Nombre de sections cible selon la longueur de l'article ────────────────

def target_sections(contenu: str) -> tuple[int, int]:
    """Retourne (min_sections, max_sections) selon le nombre de mots."""
    words = len(contenu.split())
    if words < 500:
        return 2, 3
    elif words < 1000:
        return 3, 4
    elif words < 2000:
        return 4, 6
    else:
        return 5, 8


# ── Appel Haiku ────────────────────────────────────────────────────────────

def ask_haiku_for_sections(contenu: str, min_s: int, max_s: int, client: Anthropic) -> list[str]:
    """
    Demande à Haiku de retourner les 6 premiers mots de chaque section.
    Retourne une liste de chaînes.
    """
    prompt = f"""Tu analyses un article de blog et tu dois identifier ses sections thématiques principales.

Identifie entre {min_s} et {max_s} sections thématiques principales.
Pour chaque section, reproduis EXACTEMENT les 6 premiers mots tels qu'ils apparaissent dans le texte.
La première section est toujours le tout début de l'article (ses 6 premiers mots).

Réponds UNIQUEMENT en JSON, sans aucun autre texte :
{{"sections": ["6 premiers mots section 1", "6 premiers mots section 2", ...]}}

CRITIQUE : copie les mots mot pour mot, même casse, même ponctuation, mêmes caractères spéciaux.

Article :
{contenu}"""

    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=512,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Extraire le JSON (au cas où Haiku ajoute du texte parasite)
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not json_match:
        raise ValueError(f"Pas de JSON dans la réponse Haiku : {raw[:200]}")

    data = json.loads(json_match.group())
    sections = data.get("sections", [])

    if not isinstance(sections, list) or len(sections) == 0:
        raise ValueError(f"Liste de sections vide ou invalide : {data}")

    return sections


# ── Matching progressif ────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """
    Normalise les caractères Unicode susceptibles de différer entre le texte
    source (Word → docx → apostrophes courbes) et la réponse Haiku (ASCII).
    Toutes les substitutions sont 1→1 caractère pour préserver les positions.
    """
    replacements = {
        "\u2018": "'", "\u2019": "'",   # ' '  apostrophes/guillemets simples courbes
        "\u201c": '"', "\u201d": '"',   # " "  guillemets doubles courbes
        "\u2014": "-", "\u2013": "-",   # — –  tirets longs
        "\u00a0": " ",                  # espace insécable
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _word_to_pattern(word: str) -> str:
    """
    Convertit un mot (déjà normalisé) en fragment de pattern regex.
    Gère l'équivalence ellipse : "..." (ASCII) ↔ "…" (U+2026, Word).
    Les deux directions sont couvertes : Haiku peut renvoyer l'un ou l'autre.
    """
    escaped = re.escape(word)
    # re.escape("...") → r"\.\.\."  — on le remplace par un groupe alternatif
    escaped = escaped.replace(r"\.\.\.", r"(?:\.\.\.|\u2026)")
    # Si le mot contient directement \u2026 (Haiku a renvoyé le caractère Unicode)
    escaped = escaped.replace("\u2026", r"(?:\.\.\.|\u2026)")
    return escaped


def find_position(contenu: str, phrase: str) -> int | None:
    """
    Recherche la séquence de mots de `phrase` dans `contenu`.
    Gère trois types de divergences :
      1. Caractères Unicode (apostrophes courbes, etc.) → normalize()
      2. Espaces/sauts de ligne entre mots (titre collé au paragraphe) → \\s+
      3. Ellipses : "..." ASCII vs "…" U+2026 (Word) → pattern alternatif
    L'index retourné correspond à la position dans le `contenu` original
    (normalize() étant strictement 1→1, les positions sont conservées).
    Réduit progressivement à 5, 4, 3 mots si le match complet échoue.
    """
    contenu_norm = normalize(contenu)
    words = normalize(phrase).split()

    for n_words in range(len(words), 1, -1):
        pattern = r"\s+".join(_word_to_pattern(w) for w in words[:n_words])
        m = re.search(pattern, contenu_norm)
        if m:
            return m.start()
    return None


# ── Segmentation d'un article ──────────────────────────────────────────────

def segment_article(article: dict, client: Anthropic) -> tuple[str, int]:
    """
    Retourne (contenu_avec_marqueurs, nb_sections).
    En cas d'échec définitif, retourne (contenu_original, 1).
    """
    contenu = article["contenu"]
    min_s, max_s = target_sections(contenu)

    section_starts: list[str] = []

    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            candidates = ask_haiku_for_sections(contenu, min_s, max_s, client)
        except Exception as exc:
            print(f"      [tentative {attempt}/{MAX_API_RETRIES}] Erreur API : {exc}")
            if attempt < MAX_API_RETRIES:
                time.sleep(1)
            continue

        # Valider que chaque début de section se trouve bien dans le texte
        positions: dict[str, int] = {}
        failed: list[str] = []

        for phrase in candidates:
            pos = find_position(contenu, phrase)
            if pos is not None:
                positions[phrase] = pos
            else:
                failed.append(phrase)

        if not failed:
            section_starts = candidates
            break
        else:
            print(f"      [tentative {attempt}/{MAX_API_RETRIES}] "
                  f"{len(failed)} sections non trouvées : {failed[:2]}")
            if attempt < MAX_API_RETRIES:
                time.sleep(1)

    if not section_starts:
        return contenu, 1   # fallback : 1 chunk

    # ── Calculer toutes les positions et trier ─────────────────────────────
    # Construire la liste (position, phrase) en ignorant les doublons de position
    pos_map: dict[int, str] = {}
    for phrase in section_starts:
        pos = find_position(contenu, phrase)
        if pos is not None:
            pos_map[pos] = phrase

    # Trier par position croissante
    sorted_positions = sorted(pos_map.keys())

    # La position 0 (ou très proche) = début de l'article → pas de marqueur devant
    # Identifier la position du début réel (première section = début)
    first_section_phrase = section_starts[0]
    first_pos = find_position(contenu, first_section_phrase)

    # Insérer les marqueurs en partant de la fin pour ne pas décaler les indices
    result = contenu
    for pos in reversed(sorted_positions):
        # Ne pas insérer de marqueur tout au début de l'article
        # (tolérance : si la section commence dans les 30 premiers caractères)
        if pos <= 30:
            continue
        result = result[:pos] + "###SECTION###\n" + result[pos:]

    nb_sections = sum(1 for p in sorted_positions if p > 30) + 1

    return result, nb_sections


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY introuvable dans .env")

    client = Anthropic(api_key=api_key)

    print(f"Chargement de {INPUT_FILE}...")
    with open(INPUT_FILE, encoding="utf-8") as f:
        articles = json.load(f)
    print(f"  {len(articles)} articles chargés\n")

    results = []
    total_sections = 0
    fallback_count = 0

    for i, article in enumerate(articles, 1):
        titre = (article.get("titre") or "sans titre")[:55]
        words = len(article["contenu"].split())
        min_s, max_s = target_sections(article["contenu"])
        print(f"[{i:>3}/{len(articles)}] {titre}")
        print(f"         {words} mots → cible {min_s}–{max_s} sections")

        contenu_seg, nb = segment_article(article, client)

        if nb == 1 and "###SECTION###" not in contenu_seg:
            fallback_count += 1
            print(f"         ⚠ fallback (1 chunk)")
        else:
            print(f"         ✓ {nb} section(s)")

        total_sections += nb

        segmented = dict(article)
        segmented["contenu"] = contenu_seg
        results.append(segmented)

    # ── Sauvegarde ──────────────────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f"  Segmentation terminée !")
    print(f"  Articles traités  : {len(articles)}")
    print(f"  Sections totales  : {total_sections}")
    print(f"  Moy. sections/art : {total_sections/len(articles):.1f}")
    print(f"  Fallbacks (1 chunk): {fallback_count}")
    print(f"  Fichier sauvegardé : {OUTPUT_FILE}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
