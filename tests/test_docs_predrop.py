"""Pré-drop, étape 3 (légal, contenus, pilotage) : les documents tenus contre le moteur, la matrice et n8n.

* Conditions client (brouillon) : phrases de garantie du moteur mot pour mot dans la page Précommandes, les CGV, la FAQ,
  les emails 15 à 17 et le plan du jour de drop ; plafond du supplément du code ; champs du registre alignés sur les
  paramètres signés (vérificateurs ``verifier_legal_ops.py`` et ``verifier_contenu.py``, exécutés ici) ; notes au juriste.
* Pilotage : actes de la propriétaire C32 à C34 (signature, allocations et référence marché, remboursements), tâches
  BL-208 à BL-214, dette dérivée (``STOP_LOSS.md``), reconnaissance à l'expédition (``ETOILE_POLAIRE.md``), risques
  RS-17 à RS-19 (``REVUE_SECURITE.md``).
* Agents : chaque écriture ``/predrop/*`` de la matrice est attribuée dans ``docs/08-agents/PRE_DROP.md`` ; les briefs et
  agents concernés y renvoient.
* n8n : chaque email du pré-drop envoyé par un workflow existe dans le générateur (ids numérotés 15 à 19).
Aucun réseau ; lecture seule du dépôt.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
from pokeshop import authz
from pokeshop.predrop import (
    GUARANTEE_TEXT_FR,
    MAX_PREMIUM_PCT,
    NO_DIFFERENCE_REFUND_FR,
    NOT_SERVED_REASONS_FR,
    PREDROP_DEBT_LABEL,
    CANCELLATION_REASONS_FR,
)

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _load(rel: str, name: str) -> ModuleType:
    """Charge un outil des dossiers docs/ (ses voisins importés par chemin)."""
    path = ROOT / rel
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(path.parent))


def _public(rel: str) -> str:
    text = _text(rel)
    return text.split("<!-- TEXTE_PUBLIC:DEBUT -->", 1)[1].split("<!-- TEXTE_PUBLIC:FIN -->", 1)[0]


# ================================================================================================ légal et contenus


def test_legal_and_content_verifiers_are_green_with_the_predrop_checks() -> None:
    legal = _load("docs/04-legal/outils/verifier_legal_ops.py", "_verif_legal_predrop")
    assert legal.check_predrop_alignment in legal.ALL_CHECKS
    assert legal.run_all() == []
    contenu = _load("docs/06-contenu/outils/verifier_contenu.py", "_verif_contenu_predrop")
    resultats = contenu.tout_verifier()
    assert "pré-drop" in resultats and all(not e for e in resultats.values()), resultats


@pytest.mark.parametrize(
    "rel",
    ["docs/04-legal/PRECOMMANDES.md", "docs/04-legal/CGV.md", "docs/07-ops/FAQ_CLIENTS.md"],
)
def test_public_texts_state_the_guarantee_and_no_difference_refund_word_for_word(rel: str) -> None:
    public = _public(rel)
    assert GUARANTEE_TEXT_FR in public and NO_DIFFERENCE_REFUND_FR in public
    cap = f"{int(MAX_PREMIUM_PCT * 100)} %"
    assert cap in public
    for urgency in ("compte à rebours", "plus que ", "dernière chance", "dépêchez"):
        assert urgency not in public.lower(), urgency
    assert "supplément compris" in public  # remboursements toujours intégraux


def test_precommandes_covers_every_point_of_the_owner_decision() -> None:
    public = _public("docs/04-legal/PRECOMMANDES.md")
    section = public.split("## Pré-drop : la réservation garantie", 1)[1]
    for needle in ("Deux prix", "Ce que garantit le supplément", "« Réservations ouvertes »", "« Réservations fermées »",
                   "Accès prioritaire", "{{LIMITE_RESERVATION_PREDROP}}", "Si nous recevons moins que prévu",
                   "servies **en premier**", "dernières réservations payées", "Si la date du drop change",
                   "{{SEUIL_REPORT_PRECOMMANDE}}", "Annuler votre réservation garantie", "{{DELAI_ANNULATION_PRECOMMANDE}}"):  # fmt: skip
        assert needle in section, needle
    text = _text("docs/04-legal/PRECOMMANDES.md")
    assert "À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION" in text.splitlines()[2]
    notes = text.split("## Notes pour le juriste — pré-drop", 1)[1].split("## Validation humaine requise", 1)[0]
    assert [f"P{n}" for n in range(1, 11)] == re.findall(r"^\| (P\d+) \|", notes, re.M)
    assert "### 2.5 Pré-drop" in text and "C32" in text and "C34" in text
    cgv = _public("docs/04-legal/CGV.md")
    for ch in ("7.7", "7.8", "7.9", "7.10", "7.11", "7.12"):
        assert f"\n{ch} **" in cgv, ch
    assert "| J14 |" in _text("docs/04-legal/CGV.md")


def test_refund_reason_phrases_follow_the_email_rules() -> None:
    """Les motifs en français (variable de l'email 18) n'emploient aucun terme interne ni chiffre."""
    sys.path.insert(0, str(ROOT / "site" / "outils"))
    try:
        from verifier_site import PROMESSES_RE, TERMES_INTERNES, URGENCE_RE
    finally:
        sys.path.remove(str(ROOT / "site" / "outils"))
    for code, phrase in {**NOT_SERVED_REASONS_FR, **CANCELLATION_REASONS_FR}.items():
        for motif in (TERMES_INTERNES, URGENCE_RE, PROMESSES_RE):
            assert not motif.search(phrase), (code, phrase)


# ================================================================================================ pilotage


def _backlog() -> dict[str, dict[str, str]]:
    return {r["ID"]: r for r in csv.DictReader(io.StringIO(_text("docs/00-pilotage/BACKLOG.csv")))}


def test_owner_acts_and_backlog_tasks_of_the_predrop() -> None:
    text = _text("docs/00-pilotage/INTERVENTIONS_HUMAINES.md")
    details = {ln.split("|")[1].strip(): ln for ln in text.splitlines() if re.match(r"^\| C3[2-4] \|", ln)}
    assert set(details) == {"C32", "C33", "C34"}
    assert "POKESHOP_PREDROP_FINGERPRINT" in details["C32"] and "BL-210" in details["C32"] and "BL-209" in details["C32"]
    assert "POST /predrop/{predrop_id}/approve" in details["C33"] and "market_ref_chf" in details["C33"]
    assert "POST /predrop/refunds/{refund_id}/approve" in details["C34"] and "BL-213" in details["C34"]
    rows = _backlog()
    for bl in ("BL-208", "BL-209", "BL-210", "BL-211", "BL-212", "BL-213", "BL-214"):
        assert bl in rows, bl
    for bl in ("BL-209", "BL-210", "BL-211", "BL-213", "BL-214"):
        assert rows[bl]["Agent/rôle"].startswith("Propriétaire") and rows[bl]["Validation humaine (O/N)"] == "O", bl
    assert "BL-209" in rows["BL-210"]["Dépendances"]
    assert {"BL-210", "BL-212"} <= {d.strip() for d in rows["BL-214"]["Dépendances"].split(",")}
    readme = _text("docs/00-pilotage/README.md")
    assert f"`BACKLOG.csv` | {len(rows)} tâches" in readme


def test_stoploss_and_north_star_docs_describe_the_derived_debt_and_recognition_at_shipment() -> None:
    stop = _text("docs/00-pilotage/STOP_LOSS.md")
    assert "dette dérivée" in stop and PREDROP_DEBT_LABEL in stop and "predrop_derivees_chf" in stop
    assert "réservations pré-drop dérivées du registre comprises" in stop
    star = _text("docs/00-pilotage/ETOILE_POLAIRE.md")
    assert "reconnu à l'expédition" in star and "`recognized_at`" in star
    assert "predrop_collected_not_recognized_chf" in star and "jamais à l'encaissement" in star


def test_security_review_tracks_the_new_feature() -> None:
    text = _text("docs/00-pilotage/REVUE_SECURITE.md")
    for rid in ("RS-17", "RS-18", "RS-19"):
        assert re.search(rf"^\| {rid} \|", text, re.M), rid
    assert "BL-214" in text and "BL-212" in text and "**pré-drop** (BL-214" in text
    level2 = next(ln for ln in text.splitlines() if ln.startswith("| 2 (C14, BL-200) |"))
    assert "RS-17" in level2 and "RS-18" in level2


# ================================================================================================ agents


def _route_key(method: str, path: str) -> str:
    return f"{method} {re.sub(r'{[^}]*}', '{}', path)}"


def test_every_predrop_write_route_is_assigned_in_the_who_does_what_doc() -> None:
    doc = _text("docs/08-agents/PRE_DROP.md")
    cited = {_route_key("POST", p) for p in re.findall(r"`POST (/predrop/[^`\s]+)`", doc)}
    writes = {_route_key(m, p) for (m, p), r in authz.ROUTE_MATRIX.items()
              if p.startswith("/predrop") and r.kind is authz.Kind.WRITE}  # fmt: skip
    assert writes <= cited, sorted(writes - cited)
    assert "2026-10-06.predrop-annulation" in doc and authz.AUTHZ_VERSION in doc
    for rel in ("docs/08-agents/05_finance-pricing.md", "docs/08-agents/11_operations-sav.md",
                "docs/08-agents/12_qa-conformite.md", ".claude/agents/finance-pricing.md",
                ".claude/agents/operations-sav.md", ".claude/agents/communication.md", "README.md"):  # fmt: skip
        assert "docs/08-agents/PRE_DROP.md" in _text(rel), rel


def test_cancellation_route_is_documented_for_the_service_agent() -> None:
    rule = authz.rule_for("POST", "/predrop/reservations/{order_id}/cancel")
    assert rule.roles == {"operations-sav"} and rule.owner
    for rel in ("docs/SPEC.md", "docs/08-agents/BRIEF_COMMUN.md", "docs/07-ops/SOP_SAV_RETOURS.md",
                "docs/04-legal/PRECOMMANDES.md"):  # fmt: skip
        assert "/predrop/reservations/{order_id}/cancel" in _text(rel), rel


# ================================================================================================ n8n et README


def test_root_readme_has_a_short_predrop_section() -> None:
    readme = _text("README.md")
    section = readme.split("## Pré-drop (réservation garantie)", 1)[1].split("## Démarrage rapide", 1)[0]
    assert "pas le produit" in section and "aucun remboursement de la différence" in section
    assert "C32" in section and "C33" in section and "C34" in section and len(section.splitlines()) < 15


def test_no_stale_predrop_email_reference_survives() -> None:
    for rel in ("orchestration/build_workflows.py", "orchestration/README.md", "site/shopify/STRUCTURE_BOUTIQUE.md"):
        text = _text(rel)
        assert not re.search(r"'pre-drop-[a-z-]+'", text), rel
        assert "à rédiger dans `docs/06-contenu/EMAILS/`" not in text, rel
        assert "email au client = brouillon du moteur" not in text, rel
