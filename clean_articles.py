import json
import re

INPUT  = "data/parsed/all_articles.json"
OUTPUT = "data/parsed/all_articles_clean.json"

# ── Patterns de date ──────────────────────────────────────────────────────────
# Anglais : "Jul 8, 2025" / "July 8, 2025"
_EN_MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DATE_EN = re.compile(rf"^{_EN_MONTHS}\s+\d{{1,2}},\s+\d{{4}}\s*$", re.IGNORECASE)

# Français — formats couverts :
#   "lun. 14 juil. 2025"          → jour + date + mois + année
#   "lun. 23 févr. 17:05"         → jour + date + mois + heure
#   "jeu. 25 sept. 2025 19:35"    → jour + date + mois + année + heure
#   "18 sept. 2025 23:41"         → date + mois + année + heure (sans nom de jour)
_FR_DAYS   = r"(?:lun|mar|mer|jeu|ven|sam|dim)\.?"
_FR_MONTHS = (
    r"(?:janv?|févr?|mars|avr|mai|juin|juil?|août|sept?|oct|nov|déc)\.?"
)
_DATE_FR = re.compile(
    rf"^(?:{_FR_DAYS}\s+)?\d{{1,2}}\s+{_FR_MONTHS}"
    rf"(?:\s+\d{{4}}(?:\s+\d{{1,2}}:\d{{2}})?|\s+\d{{1,2}}:\d{{2}})?\s*$",
    re.IGNORECASE,
)

# ── Blocs qui tronquent l'article dès leur apparition ────────────────────────
TRUNCATE_TRIGGERS = [
    "Other Key Tech Developments This Week:",
    "A Statement From Peter:",
    "Pre-Order Our Book",
    "Disclaimer:",
]

# ── Lignes à supprimer entièrement (match exact strip) ───────────────────────
EXACT_DROP = {"Tweet", "Share", "Tweet Share"}

# ── Préfixes qui éliminent la ligne ─────────────────────────────────────────
PREFIX_DROP = (
    "Topics:",
    "By ",
    "Sources:",
    "Metatrend #",
    "Métatendance",
    "In partnership with",
    "Presented by",          # ex : "Presented by:\xa0Viome"
)


def is_date_line(line: str) -> bool:
    s = line.strip()
    return bool(_DATE_EN.match(s) or _DATE_FR.match(s))


def clean_content(contenu: str, titre: str) -> str:
    lines = contenu.splitlines()

    # ── 1. Supprimer la 1re ligne non-vide si identique au titre ─────────────
    for i, line in enumerate(lines):
        if line.strip():
            if line.strip() == titre.strip():
                lines[i] = ""
            break

    # ── 2-8-9-10-11. Parcours ligne par ligne, truncate sur trigger ──────────
    cleaned = []
    for line in lines:
        stripped = line.strip()

        # Truncate triggers
        if any(stripped.startswith(t) for t in TRUNCATE_TRIGGERS):
            break

        # Exact drop
        if stripped in EXACT_DROP:
            continue

        # Prefix drop
        if any(stripped.startswith(p) for p in PREFIX_DROP):
            continue

        # Date line drop (règle 13)
        if is_date_line(stripped):
            continue

        cleaned.append(line)

    # ── 12. Max 1 ligne vide consécutive ─────────────────────────────────────
    deduped = []
    prev_blank = False
    for line in cleaned:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        deduped.append(line)
        prev_blank = is_blank

    # Supprimer les lignes vides en début et fin
    result = "\n".join(deduped).strip()
    return result


def main():
    with open(INPUT, encoding="utf-8") as f:
        articles = json.load(f)

    for art in articles:
        before = len(art["contenu"])
        art["contenu"] = clean_content(art["contenu"], art["titre"])
        after = len(art["contenu"])
        print(f"{art['titre'][:70]:<70}  {before:>5} -> {after:>5} chars")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\nOK {len(articles)} articles nettoyes -> {OUTPUT}")


if __name__ == "__main__":
    main()
