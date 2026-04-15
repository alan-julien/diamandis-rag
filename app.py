"""
app.py
------
Interface Streamlit : exploration vectorielle + Prompts système — Fenêtre RAG.
Question → embedding Voyage AI → ChromaDB (top N résultats).
"""

import html as html_lib
import json
import os
from datetime import date
from pathlib import Path

import chromadb
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
DB_DIR            = Path("db")
COLLECTION_NAME   = "diamandis_articles"
VOYAGE_MODEL      = "voyage-4"
VOYAGE_URL        = "https://api.voyageai.com/v1/embeddings"
TOP_K_DEFAULT     = 35
PROMPTS_FILE      = Path("data/system_prompts.json")


# ── Ressources ────────────────────────────────────────────────────────────────

@st.cache_resource
def load_chroma():
    return chromadb.PersistentClient(path=str(DB_DIR))


def get_collection(chroma):
    return chroma.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_query(text: str) -> list[float]:
    api_key = os.getenv("VOYAGE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY manquant dans .env")

    resp = requests.post(
        VOYAGE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model":      VOYAGE_MODEL,
            "input":      [text],
            "input_type": "query",
        },
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Voyage AI HTTP {resp.status_code} — {resp.text[:200]}")

    return resp.json()["data"][0]["embedding"]


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve(question: str, collection, k: int) -> list[dict]:
    embedding = embed_query(question)
    results   = collection.query(query_embeddings=[embedding], n_results=k)

    sources = []
    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        sources.append({
            "contenu": doc,
            "titre":   meta.get("titre") or "Sans titre",
            "date":    meta.get("date")  or "Date inconnue",
            "score":   round(1 - distance, 3),
        })
    return sources


# ── Persistance des prompts ───────────────────────────────────────────────────

def load_prompts() -> list[dict]:
    """Charge les prompts depuis le fichier JSON."""
    if not PROMPTS_FILE.exists():
        return []
    try:
        with open(PROMPTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_prompts(prompts: list[dict]) -> None:
    """Sauvegarde les prompts dans le fichier JSON."""
    PROMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)


# ── Modal de lecture ──────────────────────────────────────────────────────────

@st.dialog("📖 Lecture complète", width="large")
def show_content_dialog(row):
    st.markdown(
        f"<h2 style='color:#1e3a5f; margin-bottom:6px'>{row['titre']}</h2>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"📅 {row['date']}  ·  🎯 Score : **{row['score']:.3f}**  ·  📝 {row['taille']} caractères"
    )
    st.divider()
    st.markdown(
        f"<div style='font-size:1.05rem; line-height:1.8; color:#1a202c'>{row['contenu']}</div>",
        unsafe_allow_html=True,
    )


@st.dialog("📋 Contenu du prompt", width="large")
def show_prompt_dialog(prompt: dict):
    st.markdown(
        f"<h2 style='color:#1e3a5f; margin-bottom:4px'>{html_lib.escape(prompt['description'])}</h2>",
        unsafe_allow_html=True,
    )
    st.caption(f"👤 {prompt['utilisateur']}  ·  📅 {prompt['date']}")
    st.divider()
    st.code(prompt["contenu"], language="text")


# ── UI ────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Fenêtre RAG",
    page_icon="🪟",
    layout="wide",
)

st.markdown("""
<style>
/* ── En-têtes ── */
h1 { color: #0a1628 !important; font-weight: 800 !important; letter-spacing: -0.5px; }
h2, h3 { color: #1e3a5f !important; }

/* ── Focus : suppression de l'orange, remplacement par navy ── */
*:focus-visible {
    outline-color: #1e3a5f !important;
    outline-offset: 2px;
}
[data-baseweb="base-input"]:focus-within {
    border-color: #1e3a5f !important;
    box-shadow: 0 0 0 3px rgba(30,58,95,.18) !important;
}
input[type="checkbox"] { accent-color: #1e3a5f !important; }

/* ── Inputs ── */
input[type="text"], input[type="number"] {
    border-radius: 7px !important;
}

/* ── Caption ── */
.stCaption { color: #4a5568 !important; }

/* ── Séparateur ── */
hr { border-color: #bee3f8 !important; }

/* ── Survol des lignes de résultats ── */
[data-testid="stHorizontalBlock"] {
    border-radius: 7px;
    padding: 2px 6px;
    transition: background-color 0.12s ease;
}
[data-testid="stHorizontalBlock"]:hover {
    background-color: #ebf4ff;
}

/* ── En-tête colonnes résultats ── */
.col-header {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #718096;
    padding: 4px 6px 2px;
    border-bottom: 2px solid #bee3f8;
    margin-bottom: 4px;
}

/* ── Score badge ── */
.score-pill {
    display: inline-block;
    background: #dbeafe;
    color: #1e3a5f;
    font-weight: 700;
    font-size: 0.82rem;
    padding: 2px 9px;
    border-radius: 999px;
}

/* ── Titre dans la liste ── */
.row-titre {
    font-size: 0.9rem;
    color: #1a202c;
    line-height: 1.35;
}

/* ── Modal ── */
[data-testid="stModal"] > div {
    border-top: 4px solid #1e3a5f !important;
    border-radius: 12px !important;
}

/* ── Code block ── */
[data-testid="stCode"] {
    border: 1.5px solid #bee3f8 !important;
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)

st.title("🪟 Fenêtre RAG")
st.caption("Exploration vectorielle et gestion des prompts système.")

chroma_client = load_chroma()

# ── Session state ─────────────────────────────────────────────────────────────
if "explore_results" not in st.session_state:
    st.session_state.explore_results = None
if "explore_query" not in st.session_state:
    st.session_state.explore_query = ""
if "prompts" not in st.session_state:
    st.session_state.prompts = load_prompts()

# ── Onglets ───────────────────────────────────────────────────────────────────
tab_explore, tab_prompts = st.tabs(["🔍 Explorer", "📋 Prompts système"])


# ══════════════════════════════════════════════════════════════════════════════
# ONGLET EXPLORER
# ══════════════════════════════════════════════════════════════════════════════

with tab_explore:

    # ── Barre de recherche ────────────────────────────────────────────────────
    col_input, col_k = st.columns([4, 1])
    with col_input:
        explore_query = st.text_input(
            "Requête",
            value=st.session_state.explore_query,
            placeholder="Ex : moonshots, abundance, longevity…",
        )
    with col_k:
        k_explore = st.number_input(
            "Top N", min_value=1, max_value=100, value=TOP_K_DEFAULT, step=5
        )

    if st.button("🔍 Rechercher", type="primary"):
        if not explore_query.strip():
            st.warning("Entrez une requête avant de lancer la recherche.")
        else:
            st.session_state.explore_query = explore_query
            for key in list(st.session_state.keys()):
                if isinstance(key, str) and key.startswith("cb_"):
                    del st.session_state[key]
            with st.spinner("Recherche en cours…"):
                try:
                    raw = retrieve(explore_query.strip(), get_collection(chroma_client), k=k_explore)
                    rows = []
                    for s in raw:
                        rows.append({
                            "score":   s["score"],
                            "contenu": s["contenu"],
                            "taille":  len(s["contenu"]),
                            "titre":   s["titre"],
                            "date":    s["date"],
                        })
                    df = pd.DataFrame(rows)
                    df.sort_values("score", ascending=False, inplace=True)
                    df.reset_index(drop=True, inplace=True)
                    st.session_state.explore_results = df
                except Exception as e:
                    st.error(f"Erreur lors de la recherche : {e}")
                    st.session_state.explore_results = None

    # ── Résultats ─────────────────────────────────────────────────────────────
    if st.session_state.explore_results is not None:
        df = st.session_state.explore_results

        # ── Tout cocher / décocher ───────────────────────────────────────────
        col_check, col_uncheck, _ = st.columns([1, 1, 8])
        with col_check:
            if st.button("✅ Tout cocher"):
                for i in range(len(df)):
                    st.session_state[f"cb_{i}"] = True
                st.rerun()
        with col_uncheck:
            if st.button("☐ Tout décocher"):
                for i in range(len(df)):
                    st.session_state[f"cb_{i}"] = False
                st.rerun()

        # ── En-tête colonnes ─────────────────────────────────────────────────
        h0, h1, h2, h3, h4, h5 = st.columns([0.4, 0.7, 3.5, 0.9, 0.65, 0.45])
        with h0: st.markdown('<div class="col-header">✓</div>',       unsafe_allow_html=True)
        with h1: st.markdown('<div class="col-header">Score</div>',   unsafe_allow_html=True)
        with h2: st.markdown('<div class="col-header">Titre</div>',   unsafe_allow_html=True)
        with h3: st.markdown('<div class="col-header">Date</div>',    unsafe_allow_html=True)
        with h4: st.markdown('<div class="col-header">Taille</div>',  unsafe_allow_html=True)
        with h5: st.markdown('<div class="col-header">Lire</div>',    unsafe_allow_html=True)

        # ── Lignes de résultats ──────────────────────────────────────────────
        for i, row in df.iterrows():
            c0, c1, c2, c3, c4, c5 = st.columns([0.4, 0.7, 3.5, 0.9, 0.65, 0.45])

            with c0:
                st.checkbox("", key=f"cb_{i}", value=True, label_visibility="collapsed")
            with c1:
                st.markdown(
                    f'<div style="padding-top:6px"><span class="score-pill">{row["score"]:.3f}</span></div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f'<div class="row-titre" style="padding-top:5px">{row["titre"]}</div>',
                    unsafe_allow_html=True,
                )
            with c3:
                st.caption(row["date"])
            with c4:
                st.caption(f'{row["taille"]:,}')
            with c5:
                if st.button("📖", key=f"btn_{i}", help="Lire l'extrait complet"):
                    show_content_dialog(row)

        # ── Actions sur la sélection ──────────────────────────────────────────
        checked_indices = [i for i in range(len(df)) if st.session_state.get(f"cb_{i}", True)]
        checked_rows    = df.iloc[checked_indices] if checked_indices else pd.DataFrame(columns=df.columns)
        n_checked       = len(checked_indices)
        total_chars     = int(checked_rows["taille"].sum()) if n_checked > 0 else 0

        st.divider()
        col_copy, col_info = st.columns([2, 8])
        with col_copy:
            copy_clicked = st.button("📋 Copier les sources", type="primary")
        with col_info:
            st.caption(f"{n_checked} source(s) cochée(s) · {total_chars:,} caractères")

        if copy_clicked:
            lines = []
            for num, (_, row) in enumerate(checked_rows.iterrows(), start=1):
                lines.append(f"--- [{num}] {row['titre']} | {row['date']} | score {row['score']:.3f} ---")
                lines.append(row["contenu"])
                lines.append("")
            text_to_copy = "\n".join(lines)
            st.markdown(
                "<p style='margin:8px 0 4px; font-size:0.83rem; color:#2c5282; font-weight:600'>"
                "Cliquez sur l'icône ⎘ en haut à droite du bloc pour copier :</p>",
                unsafe_allow_html=True,
            )
            st.code(text_to_copy, language="text")


# ══════════════════════════════════════════════════════════════════════════════
# ONGLET PROMPTS SYSTÈME
# ══════════════════════════════════════════════════════════════════════════════

with tab_prompts:

    # ── Formulaire de création ────────────────────────────────────────────────
    with st.expander("➕ Ajouter un prompt", expanded=(len(st.session_state.prompts) == 0)):
        with st.form("form_nouveau_prompt", clear_on_submit=True):
            col_user, col_date = st.columns([3, 2])
            with col_user:
                nouveau_utilisateur = st.text_input("Utilisateur", placeholder="Ex : julien.alan")
            with col_date:
                nouveau_date = st.date_input("Date", value=date.today())

            nouveau_description = st.text_input(
                "Description courte",
                placeholder="Ex : Assistant expert Diamandis — réponses en français",
            )
            nouveau_contenu = st.text_area(
                "Contenu du prompt système",
                placeholder="Tu es un assistant expert sur les articles de Peter Diamandis…",
                height=200,
            )

            submitted = st.form_submit_button("Enregistrer", type="primary")
            if submitted:
                if not nouveau_utilisateur.strip():
                    st.error("Le nom d'utilisateur est obligatoire.")
                elif not nouveau_description.strip():
                    st.error("La description est obligatoire.")
                elif not nouveau_contenu.strip():
                    st.error("Le contenu du prompt est obligatoire.")
                else:
                    new_prompt = {
                        "date":        str(nouveau_date),
                        "utilisateur": nouveau_utilisateur.strip(),
                        "description": nouveau_description.strip(),
                        "contenu":     nouveau_contenu.strip(),
                    }
                    st.session_state.prompts.append(new_prompt)
                    save_prompts(st.session_state.prompts)
                    st.success("Prompt enregistré.")
                    st.rerun()

    # ── Tableau des prompts ───────────────────────────────────────────────────
    prompts = st.session_state.prompts

    if not prompts:
        st.info("Aucun prompt enregistré. Créez-en un ci-dessus.")
    else:
        st.caption(f"{len(prompts)} prompt(s) enregistré(s)")

        # En-têtes
        h_date, h_user, h_desc, h_voir, h_del = st.columns([1.2, 1.5, 5, 0.6, 0.6])
        with h_date: st.markdown('<div class="col-header">Date</div>',        unsafe_allow_html=True)
        with h_user: st.markdown('<div class="col-header">Utilisateur</div>', unsafe_allow_html=True)
        with h_desc: st.markdown('<div class="col-header">Description</div>', unsafe_allow_html=True)
        with h_voir: st.markdown('<div class="col-header">Voir</div>',        unsafe_allow_html=True)
        with h_del:  st.markdown('<div class="col-header">Sup.</div>',        unsafe_allow_html=True)

        to_delete = None
        for idx, prompt in enumerate(prompts):
            c_date, c_user, c_desc, c_voir, c_del = st.columns([1.2, 1.5, 5, 0.6, 0.6])
            with c_date:
                st.caption(prompt["date"])
            with c_user:
                st.caption(prompt["utilisateur"])
            with c_desc:
                st.markdown(
                    f'<div class="row-titre" style="padding-top:5px">{html_lib.escape(prompt["description"])}</div>',
                    unsafe_allow_html=True,
                )
            with c_voir:
                if st.button("📋", key=f"voir_{idx}", help="Voir le contenu du prompt"):
                    show_prompt_dialog(prompt)
            with c_del:
                if st.button("🗑️", key=f"del_{idx}", help="Supprimer ce prompt"):
                    to_delete = idx

        if to_delete is not None:
            st.session_state.prompts.pop(to_delete)
            save_prompts(st.session_state.prompts)
            st.rerun()
