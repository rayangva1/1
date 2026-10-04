"""Tests des livrables pilotage, marché et sourcing (docs/00 à 02).

Chaque contrôle est testé sur les vrais fichiers (doit passer) puis sur une copie altérée (doit échouer).
Lancer : ``python -m pytest -q docs/00-pilotage/outils``.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest
import verifier_livrables as v


def _rewrite_csv(src: Path, dst: Path, mutate) -> Path:
    with src.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    rows = mutate(rows)
    with dst.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return dst


# ---------------------------------------------------------------- fichiers réels
@pytest.mark.parametrize("check", v.ALL_CHECKS, ids=lambda c: c.__name__)
def test_real_deliverables_pass(check):
    assert check() == []


def test_run_all_and_main(capsys):
    assert v.run_all() == []
    assert v.main() == 0
    assert "OK" in capsys.readouterr().out


def test_expected_files_exist():
    expected = {
        v.PILOTAGE: [
            "PLAN_90_JOURS.md",
            "BACKLOG.csv",
            "GATES_GO_NO_GO.md",
            "INTERVENTIONS_HUMAINES.md",
            "REGISTRE_RISQUES.md",
            "ECARTS_BP.md",
        ],
        v.MARCHE: [
            "GRILLE_CONCURRENCE.csv",
            "PROTOCOLE_CONCURRENCE.md",
            "GUIDE_ENTRETIENS.md",
            "QUESTIONNAIRE.md",
            "PROTOCOLE_LANDING_TEST.md",
            "ASSORTIMENT_PILOTE.md",
        ],
        v.SOURCING: [
            "DOSSIER_B2B.md",
            "EMAILS_FOURNISSEURS.md",
            "PANIER_PILOTE.csv",
            "COMPARATEUR_OFFRES.xlsx",
            "TRACKER_CONTACTS.csv",
            "CHECKLIST_DUE_DILIGENCE_FOURNISSEUR.md",
        ],
    }
    for folder, names in expected.items():
        for name in names:
            assert (folder / name).exists(), name


def test_governance_docs_not_owned():
    names = {p.name for p in v.owned_markdown()}
    assert not names & v.FOREIGN_DOCS
    # tous les documents attendus du périmètre sont contrôlés
    assert {"PLAN_90_JOURS.md", "GATES_GO_NO_GO.md", "EMAILS_FOURNISSEURS.md", "ASSORTIMENT_PILOTE.md"} <= names


def test_foreign_file_in_folder_is_ignored(tmp_path, monkeypatch):
    fake = tmp_path / "00-pilotage"
    fake.mkdir()
    (fake / "STOP_LOSS.md").write_text("# Sans section finale\n", encoding="utf-8")
    (fake / "AUTRE_AGENT.md").write_text("# Sans section finale\n", encoding="utf-8")
    monkeypatch.setattr(v, "PILOTAGE", fake)
    monkeypatch.setattr(v, "OWNED_MD", {"PILOTAGE": ("PLAN_90_JOURS.md",), "MARCHE": (), "SOURCING": ()})
    assert v.owned_markdown() == []
    assert v.check_validation_sections() == []


def test_backlog_covers_whole_bp():
    _, rows = v.read_csv(v.PILOTAGE / "BACKLOG.csv")
    assert len(rows) >= 100
    sections = " ".join(r["Section BP"] for r in rows)
    for s in ("§1", "§2", "§3", "§4", "§5", "§6", "§7", "§8", "§9", "§10", "§11", "§12", "§13"):
        assert s in sections, s
    phases = {r["Phase"].split()[0] for r in rows}
    assert {"P0", "P1", "P2", "P3", "P4", "P5", "P6", "Transverse"} <= phases
    # les six conditions de lancement et la décision finale ont une tâche de gate
    titles = " ".join(r["Titre"] for r in rows)
    for gate in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"):
        assert f"Gate {gate}" in titles, gate


def test_tracker_never_marks_contact_established():
    _, rows = v.read_csv(v.SOURCING / "TRACKER_CONTACTS.csv")
    assert {r["statut"] for r in rows} == {"non contacté"}


def test_grid_has_no_price_yet():
    _, rows = v.read_csv(v.MARCHE / "GRILLE_CONCURRENCE.csv")
    assert all(not r[f] for r in rows for f in v.GRILLE_PRICE_FIELDS)
    assert {r["source_lecture"] for r in rows} == {"non relevé"}


def test_find_cycle():
    assert v.find_cycle({"a": ["b"], "b": ["c"], "c": []}) is None
    cyc = v.find_cycle({"a": ["b"], "b": ["c"], "c": ["a"]})
    assert cyc is not None and cyc[0] == cyc[-1]


def test_gtin_valid():
    assert v.gtin_valid("4006381333931")
    assert not v.gtin_valid("4006381333932")
    assert not v.gtin_valid("ABC")


def test_to_decimal():
    assert str(v.to_decimal("**3 000**")) == "3000"
    assert v.to_decimal("n/a") is None


# ---------------------------------------------------------------- copies altérées
def test_backlog_detects_unknown_dependency_and_cycle(tmp_path):
    def mutate(rows):
        rows[0]["Dépendances"] = "BL-999"
        rows[1]["Dépendances"] = rows[2]["ID"]
        rows[2]["Dépendances"] = rows[1]["ID"]
        rows[3]["Statut"] = "Fait"
        rows[4]["ID"] = rows[5]["ID"]
        return rows

    bad = _rewrite_csv(v.PILOTAGE / "BACKLOG.csv", tmp_path / "BACKLOG.csv", mutate)
    errors = " | ".join(v.check_backlog(bad))
    assert "dépendance inconnue BL-999" in errors
    assert "cycle" in errors
    assert "statut 'Fait'" in errors
    assert "double" in errors


def test_backlog_owner_task_requires_validation(tmp_path):
    def mutate(rows):
        for r in rows:
            if r["Agent/rôle"].startswith("Propriétaire"):
                r["Validation humaine (O/N)"] = "N"
                break
        return rows

    bad = _rewrite_csv(v.PILOTAGE / "BACKLOG.csv", tmp_path / "BACKLOG.csv", mutate)
    assert any("sans validation humaine" in e for e in v.check_backlog(bad))


def test_backlog_bad_header(tmp_path):
    p = tmp_path / "BACKLOG.csv"
    p.write_text("ID,Titre\nBL-001,x\n", encoding="utf-8")
    assert v.check_backlog(p) and "en-tête" in v.check_backlog(p)[0]


def test_tracker_detects_established_contact(tmp_path):
    def mutate(rows):
        rows[0]["statut"] = "contacté"
        rows[1]["date_premier_contact"] = "2026-10-07"
        return [r for r in rows if "CardCosmos" not in r["organisation"]]

    bad = _rewrite_csv(v.SOURCING / "TRACKER_CONTACTS.csv", tmp_path / "T.csv", mutate)
    errors = " | ".join(v.check_tracker(bad))
    assert "statut 'contacté'" in errors
    assert "date_premier_contact" in errors
    assert "CardCosmos" in errors


def test_grid_detects_price_without_dated_reading(tmp_path):
    def mutate(rows):
        rows[0]["prix_produit_chf"] = "99.90"
        return rows[:-1]

    bad = _rewrite_csv(v.MARCHE / "GRILLE_CONCURRENCE.csv", tmp_path / "G.csv", mutate)
    errors = " | ".join(v.check_grille(bad))
    assert "prix sans lecture" in errors
    assert "incomplète" in errors


def test_grid_accepts_dated_reading(tmp_path):
    def mutate(rows):
        rows[0].update(
            prix_produit_chf="99.90",
            source_lecture="page lue",
            date_releve="2026-10-06",
            url_produit="https://exemple.invalid/p",
        )
        return rows

    ok = _rewrite_csv(v.MARCHE / "GRILLE_CONCURRENCE.csv", tmp_path / "G.csv", mutate)
    assert v.check_grille(ok) == []


def test_basket_detects_bad_counts_and_ean(tmp_path):
    def mutate(rows):
        for r in rows:
            r["statut_vise"] = "STOCK"
        rows[0]["ean"] = "1234567890123"
        rows[1]["fictif"] = "true"
        return rows[:14]

    bad = _rewrite_csv(v.SOURCING / "PANIER_PILOTE.csv", tmp_path / "P.csv", mutate)
    errors = " | ".join(v.check_panier(bad))
    assert "14 références" in errors
    assert "en stock" in errors
    assert "EAN invalide" in errors
    assert "FICTIF" in errors


def test_assortment_detects_extension_over_cap(tmp_path):
    src = (v.MARCHE / "ASSORTIMENT_PILOTE.md").read_text(encoding="utf-8")
    bad = src.replace("| Displays (25 %) | — | 375 | 375 |", "| Displays (25 %) | 375 | 375 | — |")
    assert bad != src
    p = tmp_path / "A.md"
    p.write_text(bad, encoding="utf-8")
    assert any("plafond 750" in e for e in v.check_assortiment_envelopes(p))


def test_assortment_detects_wrong_category_total(tmp_path):
    src = (v.MARCHE / "ASSORTIMENT_PILOTE.md").read_text(encoding="utf-8")
    bad = src.replace(
        "| Accessoires (10 %) | — | — | — | — | 300 | **300** |",
        "| Accessoires (10 %) | — | — | — | — | 400 | **400** |",
    )
    assert bad != src
    p = tmp_path / "A.md"
    p.write_text(bad, encoding="utf-8")
    errors = " | ".join(v.check_assortiment_envelopes(p))
    assert "Accessoires" in errors and "3 000" in errors


def test_emails_detect_missing_bp_field_and_relance(tmp_path):
    src = (v.SOURCING / "EMAILS_FOURNISSEURS.md").read_text(encoding="utf-8")
    bad = src.replace("Incoterm", "conditions").replace(
        "**Relance J+12 — Objet :** Re : Accès B2B", "**Relance — Objet :** Re : Accès B2B"
    )
    p = tmp_path / "E.md"
    p.write_text(bad, encoding="utf-8")
    errors = " | ".join(v.check_emails(p))
    assert "Incoterm" in errors
    assert "CardCosmos" in errors and "Relance J+12" in errors


def test_gates_plan_interventions_detect_gaps(tmp_path):
    g = tmp_path / "G.md"
    g.write_text(
        (v.PILOTAGE / "GATES_GO_NO_GO.md").read_text(encoding="utf-8").replace("### G5 ", "### X5 "), encoding="utf-8"
    )
    assert "GATES : G5 absent" in v.check_gates(g)
    pl = tmp_path / "P.md"
    pl.write_text(
        (v.PILOTAGE / "PLAN_90_JOURS.md").read_text(encoding="utf-8").replace("| S9 |", "| SX |"), encoding="utf-8"
    )
    assert "PLAN : S9 absente" in v.check_plan(pl)
    it = tmp_path / "I.md"
    src = (v.PILOTAGE / "INTERVENTIONS_HUMAINES.md").read_text(encoding="utf-8")
    head, detail = src.split("## 2.", 1)
    it.write_text(head + "## 2." + detail.replace("| B14 | Ouvrir", "| Z14 | Ouvrir"), encoding="utf-8")
    assert "INTERVENTIONS : B14 sans fiche détaillée" in v.check_interventions(it)


def test_validation_section_must_be_last(tmp_path):
    good = tmp_path / "ok.md"
    good.write_text("# T\n\n## A\n\ntexte\n\n## Validation humaine requise\n\n- [ ] décider\n", encoding="utf-8")
    bad1 = tmp_path / "bad1.md"
    bad1.write_text("# T\n\n## Validation humaine requise\n\n- [ ] x\n\n## Annexe\n", encoding="utf-8")
    bad2 = tmp_path / "bad2.md"
    bad2.write_text("# T\n\n## Validation humaine requise\n\nRien.\n", encoding="utf-8")
    assert v.check_validation_sections([good]) == []
    assert "dernière section" in v.check_validation_sections([bad1])[0]
    assert "case à cocher" in v.check_validation_sections([bad2])[0]


def test_cross_refs_detect_unknown_backlog_id(tmp_path, monkeypatch):
    fake = tmp_path / "docs" / "00-pilotage"
    fake.mkdir(parents=True)
    shutil.copy(v.PILOTAGE / "BACKLOG.csv", fake / "BACKLOG.csv")
    (fake / "NOTE.md").write_text("Voir BL-998.\n\n## Validation humaine requise\n\n- [ ] x\n", encoding="utf-8")
    monkeypatch.setattr(v, "PILOTAGE", fake)
    monkeypatch.setattr(v, "OWNED_MD", {"PILOTAGE": ("NOTE.md",), "MARCHE": (), "SOURCING": ()})
    errors = v.check_cross_refs()
    assert any("BL-998" in e for e in errors)
