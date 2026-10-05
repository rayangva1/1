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


# ---------------------------------------------------------------- interventions, plan, gates, écarts (revue 5.10.2026)
def test_real_backlog_dates_aligned():
    """COH-19 et COH-04 : échéances alignées entre backlog, interventions et plan."""
    _, rows = v.read_csv(v.PILOTAGE / "BACKLOG.csv")
    due = {r["ID"]: r["Échéance"] for r in rows}
    assert due["BL-016"] == "J1"
    assert due["BL-132"] == "J45"
    assert due["BL-141"] == "J62"
    assert v.j_values(due["BL-136"]) == {60, 64}


def test_interventions_name_every_owner_act():
    """COH-06 : la checklist maîtresse couvre jetons, point zéro, signatures, renouvellement, hébergement."""
    text = (v.PILOTAGE / "INTERVENTIONS_HUMAINES.md").read_text(encoding="utf-8")
    for term in (
        "jeton",
        "point zéro",
        "Renouveler",
        "Héberger",
        "Search Console",
        "Recruter",
        "temps passé",
        "Signer",
    ):
        assert term in text, term
    days, links = v.interventions_tables(text)
    assert set(links) == set(days), "chaque fiche détaillée a une date dans la checklist, et inversement"


def _copy(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_interventions_backlog_detects_missing_owner_task(tmp_path):
    src = (v.PILOTAGE / "INTERVENTIONS_HUMAINES.md").read_text(encoding="utf-8")
    bad = _copy(tmp_path, "I.md", src.replace("| BL-171 |", "| — |"))
    assert any("BL-171 absente" in e for e in v.check_interventions_backlog(bad))


def test_interventions_without_backlog_column_fails(tmp_path):
    """L'ancienne checklist (sans colonne Backlog, sans jetons ni point zéro) échoue."""
    src = (v.PILOTAGE / "INTERVENTIONS_HUMAINES.md").read_text(encoding="utf-8")
    stripped = "\n".join(
        line.rsplit("|", 2)[0] + "|"
        if line.startswith(("| A", "| B", "| C")) and "BL-" in line.rsplit("|", 2)[1]
        else line
        for line in src.splitlines()
    )
    bad = _copy(tmp_path, "I.md", stripped)
    errors = v.check_interventions_backlog(bad)
    assert any("BL-176 absente" in e for e in errors)
    assert any("BL-148 absente" in e for e in errors)


def test_interventions_backlog_detects_misaligned_deadline(tmp_path):
    def mutate(rows):
        for r in rows:
            if r["ID"] == "BL-016":
                r["Échéance"] = "J2"
        return rows

    backlog = _rewrite_csv(v.PILOTAGE / "BACKLOG.csv", tmp_path / "BACKLOG.csv", mutate)
    errors = v.check_interventions_backlog(backlog=backlog)
    assert any("C01 à J[1] mais BL-016 échoit à J2" in e for e in errors)


def test_plan_owner_dates_detect_task_placed_late(tmp_path):
    src = (v.PILOTAGE / "PLAN_90_JOURS.md").read_text(encoding="utf-8")
    bad = src.replace(" · choisir l'entité exploitante avec la fiduciaire (BL-007)", "").replace(
        "· IDE (BL-011)", "· entité et IDE (BL-007, BL-011)"
    )
    assert bad != src
    errors = v.check_plan_owner_dates(_copy(tmp_path, "P.md", bad))
    assert any("BL-007 placé à J[10] mais échoit à J7" in e for e in errors)


def test_gate_dates_detect_g5_at_j60_only(tmp_path):
    """COH-04 : G5 daté J60 seul alors que l'option A (recommandée) le place à J64."""
    src = (v.PILOTAGE / "GATES_GO_NO_GO.md").read_text(encoding="utf-8")
    bad = src.replace("| G5 | J60 (3.12) option B ; J64 (7.12) option A, recommandée |", "| G5 | J60 (3.12) |")
    assert bad != src
    errors = v.check_gate_dates(gates=_copy(tmp_path, "G.md", bad))
    assert any("dates de G5 divergentes" in e for e in errors)
    assert v.check_gate_dates() == []


def test_ecarts_detect_incomplete_rows(tmp_path):
    lines = [
        "| EC-F-99 | §10 | Constat | Mineur |",
        "| EC-X-01 | §1 | Constat | Mineur | Traitement | Décision |",
        "| EC-01 | §2 | Doublon | Mineur | Traitement | Décision |",
        "| EC-M-77 | §5 | Constat | Grave | Traitement | — |",
    ]
    src = (v.PILOTAGE / "ECARTS_BP.md").read_text(encoding="utf-8")
    bad = _copy(
        tmp_path,
        "E.md",
        src.replace("## 15. Journal des décisions", "\n".join(lines) + "\n\n## 15. Journal des décisions"),
    )
    errors = " | ".join(v.check_ecarts(bad))
    assert "EC-F-99 : 4 colonnes" in errors
    assert "'EC-X-01' hors convention" in errors
    assert "en double EC-01" in errors
    assert "EC-M-77 : gravité 'Grave'" in errors
    assert "EC-M-77 : décision attendue vide" in errors


def test_ecarts_cover_every_build_domain():
    text = (v.PILOTAGE / "ECARTS_BP.md").read_text(encoding="utf-8")
    for prefix in ("EC-F-", "EC-M-", "EC-D-", "EC-G-", "EC-L-", "EC-DA-", "EC-S-", "EC-I-", "EC-O-", "EC-A-"):
        assert f"| {prefix}01 |" in text, prefix
    assert "| EC-23 |" in text and "externalisé" in text  # CON-11


def test_no_stale_expected_detected(tmp_path):
    good = _copy(tmp_path, "ok.md", "| A02 | x | (attendu : `docs/inexistant/`) |\n")
    assert v.check_no_stale_expected(good) == []
    bad = _copy(
        tmp_path,
        "bad.md",
        "| A02 | SOP colis (attendu : `docs/07-ops/`, agent ops) |\n| A05 | SOP réception (attendu) |\n",
    )
    errors = " | ".join(v.check_no_stale_expected(bad))
    assert "`docs/07-ops/` est livré" in errors
    assert "sans chemin exact" in errors


# ---------------------------------------------------------------- revue round 2 (NEW-01, NEW-06, NEW-07, COH-04)
def test_dependency_dates_detect_task_due_before_dependency(tmp_path):
    """NEW-06 : BL-182 (J85) dépendait de BL-147 (J90) ; BL-002 (J1) exigeait le coffre créé à J2."""

    def mutate(rows):
        for r in rows:
            if r["ID"] == "BL-182":
                r["Dépendances"] = "BL-147"
            if r["ID"] == "BL-005":
                r["Échéance"] = "J2"
        return rows

    bad = _rewrite_csv(v.PILOTAGE / "BACKLOG.csv", tmp_path / "BACKLOG.csv", mutate)
    errors = " | ".join(v.check_dependency_dates(bad))
    assert "BL-182 (J85) échoit avant sa dépendance BL-147 (J90)" in errors
    assert "BL-002 (J1) échoit avant sa dépendance BL-005 (J2)" in errors
    assert v.check_dependency_dates() == []


def test_counts_detect_wrong_category_count(tmp_path):
    """NEW-01 : les compteurs du tableau suivent le nombre de fiches."""
    src = (v.PILOTAGE / "INTERVENTIONS_HUMAINES.md").read_text(encoding="utf-8")
    bad = src.replace("| B. Légal et identité, une fois | 27 |", "| B. Légal et identité, une fois | 24 |")
    assert bad != src
    errors = v.check_counts(interventions=_copy(tmp_path, "I.md", bad))
    assert errors == ["INTERVENTIONS : catégorie B annoncée à 24 items, 27 fiches"]
    readme = _copy(tmp_path, "README.md", "| `BACKLOG.csv` | 159 tâches sur tout le BP |")
    assert any("159 tâches annoncées" in e for e in v.check_counts(readme=readme))


def test_gate_dates_detect_calendar_with_g5_at_j60_only(tmp_path):
    """COH-04 : le calendrier de contenu doit porter G5 à J60 (option B) et à J64 (option A)."""

    def mutate(rows):
        return [r for r in rows if not (r["Nom"].startswith("Gate G5") and r["J"] == "J64")]

    cal = _rewrite_csv(v.CALENDRIER, tmp_path / "CAL.csv", mutate)
    errors = v.check_gate_dates(calendrier=cal)
    assert any("dates de G5 divergentes" in e and "CAL.csv J[60]" in e for e in errors)


def test_interventions_cover_every_owner_route_and_sequence():
    """NEW-01 / NEW-07 : chaque acte réservé de l'API a sa fiche ; le point zéro est décidé à J3, posé après la photo."""
    text = (v.PILOTAGE / "INTERVENTIONS_HUMAINES.md").read_text(encoding="utf-8")
    for route in ("POST /capital/movements", "POST /pricing/approvals", "cap_exceptions", "POST /fx/rates",
                  "POST /stoploss/baseline", "POST /stoploss/rearm", "POST /stoploss/capital-memory/reset",
                  "POST /autonomy", "POST /incidents/{id}/resume", "POST /incidents/{id}/test"):  # fmt: skip
        assert route in text, route
    for act in ("lecture seule", "Basic Auth", "age", "R-I04", "R-E03", "checklist LCD", "canal d'alerte",
                "petits produits", "agent-12-qa", "n8n-07-stoploss", "/etc/pokeshop/api.env"):  # fmt: skip
        assert act in text, act
    days, _ = v.interventions_tables(text)
    assert days["C19"] == {3, 27} and days["B03"] == {1} and days["B01"] == {1} and days["B27"] == {8}
    _, rows = v.read_csv(v.PILOTAGE / "BACKLOG.csv")
    by = {r["ID"]: r for r in rows}
    assert {"BL-188", "BL-189", "BL-190"} <= set(v.split_ids(by["BL-191"]["Dépendances"]))
    assert {"BL-186", "BL-187"} <= set(v.split_ids(by["BL-032"]["Dépendances"]))
    assert "BL-005" in v.split_ids(by["BL-002"]["Dépendances"])
