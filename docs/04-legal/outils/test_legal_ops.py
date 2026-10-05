"""Tests des outils legal-ops : registre des champs, rendu des textes publics, vérificateur.

Chaque contrôle du vérificateur est testé sur les vrais fichiers (doit passer) puis sur une
copie altérée (doit échouer). Lancer : ``python -m pytest -q docs/04-legal/outils``.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import registre_champs as rc
import rendre_textes as rt
import verifier_legal_ops as v
import yaml

REPO = rc.REPO


# ----------------------------------------------------------------------------- fixtures
@pytest.fixture()
def ctx(tmp_path: Path) -> v.Context:
    """Copie du périmètre (et des fichiers lus ailleurs) dans un dossier temporaire."""
    for rel in ("docs/04-legal", "docs/07-ops"):
        shutil.copytree(REPO / rel, tmp_path / rel, ignore=shutil.ignore_patterns("__pycache__"))
    for rel in ("docs/05-da/packaging/NOTE_CHIFFRAGE.md", "config/pricing_rules.v1.yaml"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, tmp_path / rel)
    return v.Context(tmp_path)


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    """Remplace ``old`` par ``new`` dans un fichier ; échoue si ``old`` est absent."""
    text = path.read_text(encoding="utf-8")
    assert old in text, f"motif absent de {path.name} : {old!r}"
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def edit_registry(ctx: v.Context, mutate: Callable[[dict[str, Any]], None]) -> None:
    data = yaml.safe_load(ctx.registry_path.read_text(encoding="utf-8"))
    mutate(data)
    ctx.registry_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def assert_flags(errors: list[str], needle: str) -> None:
    assert errors, "le contrôle aurait dû échouer"
    assert any(needle in e for e in errors), errors


def registry(**fields: dict[str, Any]) -> dict[str, Any]:
    base = {"description": "d", "decideur": "x", "source": "s"}
    return {"champs": {name: {**base, **spec} for name, spec in fields.items()}}


# ----------------------------------------------------------------------- fichiers réels
@pytest.mark.parametrize("check", v.ALL_CHECKS, ids=lambda c: c.__name__)
def test_real_deliverables_pass(check: Callable[[v.Context], list[str]]) -> None:
    assert check(v.Context.default()) == []


def test_run_all_and_main(capsys: pytest.CaptureFixture[str]) -> None:
    assert v.run_all() == []
    assert v.main() == 0
    assert "OK : 20 contrôles passés" in capsys.readouterr().out


def test_copy_passes_all_checks(ctx: v.Context) -> None:
    assert v.run_all(ctx) == []


def test_expected_deliverables_listed() -> None:
    names = {p.name for p in v.Context.default().owned_docs()}
    assert {
        "CGV.md",
        "LIVRAISON_RETOURS.md",
        "PRECOMMANDES.md",
        "CONFIDENTIALITE.md",
        "MENTIONS_LEGALES.md",
        "COOKIES.md",
        "USAGE_MARQUES.md",
        "CHECKLIST_LCD_ECOMMERCE.md",
        "SOP_RECEPTION_STOCK.md",
        "SOP_PREPARATION_COLIS.md",
        "SOP_SAV_RETOURS.md",
        "SOP_INCIDENTS.md",
        "ROUTINES_PILOTAGE.md",
        "RECETTE_AVANT_OUVERTURE.md",
        "FAQ_CLIENTS.md",
    } <= names


def test_all_fields_still_to_validate_today() -> None:
    """Au 4.10.2026, aucun champ n'est validé : rien ne doit pouvoir être publié."""
    fields = rc.load_registry()
    assert all(f.status is not rc.Status.VALIDE for f in fields.values())


# ------------------------------------------------------------------ contrôles altérés
def test_missing_file_detected(ctx: v.Context) -> None:
    (ctx.legal / "COOKIES.md").unlink()
    assert_flags(v.check_expected_files(ctx), "COOKIES.md")


def test_missing_registry_detected(ctx: v.Context) -> None:
    ctx.registry_path.unlink()
    assert_flags(v.check_expected_files(ctx), "champs_a_remplir.yaml")
    assert_flags(v.check_registry_schema(ctx), "illisible")
    assert_flags(v.check_no_invented_amounts(ctx), "illisible")


def test_banner_required(ctx: v.Context) -> None:
    edit(ctx.legal / "CGV.md", v.BANNER, "Brouillon")
    assert_flags(v.check_banner(ctx), "CGV.md")


def test_banner_required_on_faq(ctx: v.Context) -> None:
    edit(ctx.ops / "FAQ_CLIENTS.md", v.BANNER, "Brouillon")
    assert_flags(v.check_banner(ctx), "FAQ_CLIENTS.md")


def test_final_section_must_be_last(ctx: v.Context) -> None:
    path = ctx.ops / "SOP_INCIDENTS.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n## Annexe\n\ntexte\n", encoding="utf-8")
    assert_flags(v.check_final_validation_section(ctx), "dernière section")


def test_final_section_needs_checkbox(ctx: v.Context) -> None:
    path = ctx.ops / "ROUTINES_PILOTAGE.md"
    text = path.read_text(encoding="utf-8")
    head = text.split(v.FINAL_SECTION)[0]
    path.write_text(head + v.FINAL_SECTION + "\n\nAucune.\n", encoding="utf-8")
    assert_flags(v.check_final_validation_section(ctx), "sans case")


def test_unbalanced_public_block(ctx: v.Context) -> None:
    edit(ctx.legal / "CGV.md", rc.PUBLIC_END, "")
    assert_flags(v.check_public_blocks(ctx), "sans balise de fin")


def test_unexpected_public_block(ctx: v.Context) -> None:
    edit(ctx.ops / "SOP_INCIDENTS.md", "## 1. Niveaux", f"{rc.PUBLIC_START}\nx\n{rc.PUBLIC_END}\n\n## 1. Niveaux")
    assert_flags(v.check_public_blocks(ctx), "bloc public inattendu")


def test_two_public_blocks(ctx: v.Context) -> None:
    path = ctx.legal / "COOKIES.md"
    edit(path, "## Partie interne", f"{rc.PUBLIC_START}\nbis\n{rc.PUBLIC_END}\n\n## Partie interne")
    assert_flags(v.check_public_blocks(ctx), "2 bloc(s)")


def test_undeclared_placeholder(ctx: v.Context) -> None:
    edit(ctx.ops / "FAQ_CLIENTS.md", "{{EMAIL_SUPPORT}}", "{{CHAMP_INCONNU}}")
    assert_flags(v.check_placeholders_declared(ctx), "CHAMP_INCONNU")


def test_orphan_field(ctx: v.Context) -> None:
    def add(data: dict[str, Any]) -> None:
        data["champs"]["CHAMP_ORPHELIN"] = {"description": "d", "statut": "a_remplir", "decideur": "x", "source": "s"}

    edit_registry(ctx, add)
    assert_flags(v.check_registry_fields_used(ctx), "CHAMP_ORPHELIN")


def test_invented_tariff_refused(ctx: v.Context) -> None:
    def propose(data: dict[str, Any]) -> None:
        data["champs"]["FRAIS_LIVRAISON"].update(statut="a_valider", valeur_proposee="7.00 CHF")

    edit_registry(ctx, propose)
    assert_flags(v.check_no_invented_amounts(ctx), "FRAIS_LIVRAISON")


def test_no_proposal_field_must_exist(ctx: v.Context) -> None:
    edit_registry(ctx, lambda d: d["champs"].pop("TAUX_HORAIRE_VALORISATION"))
    assert_flags(v.check_no_invented_amounts(ctx), "TAUX_HORAIRE_VALORISATION")


def test_registry_schema_error(ctx: v.Context) -> None:
    edit_registry(ctx, lambda d: d["champs"]["DELAI_EXPEDITION"].update(statut="peut-etre"))
    assert_flags(v.check_registry_schema(ctx), "DELAI_EXPEDITION")
    assert_flags(v.check_placeholders_declared(ctx), "registre invalide")
    assert_flags(v.check_registry_fields_used(ctx), "registre invalide")
    assert_flags(v.check_da_fields_declared(ctx), "registre invalide")
    assert_flags(v.check_previews_up_to_date(ctx), "rendu impossible")


def test_da_fields_must_be_declared(ctx: v.Context) -> None:
    edit(ctx.da_note, "{{EMAIL_SUPPORT}}", "{{NOUVEAU_CHAMP_DA}}")
    assert_flags(v.check_da_fields_declared(ctx), "NOUVEAU_CHAMP_DA")


def test_da_note_absent_is_not_an_error(ctx: v.Context) -> None:
    ctx.da_note.unlink()
    assert v.check_da_fields_declared(ctx) == []


@pytest.mark.parametrize(
    ("injected", "label"),
    [
        ("Notre marge est faible.", "marge"),
        ("La contribution est suivie.", "contribution"),
        ("Le stop-loss coupe la vente.", "stop-loss"),
        ("Un agent vous répond.", "agent"),
        ("Le coût rendu est de 10 CHF.", "coût interne"),
        ("Le prix d'achat est connu.", "prix interne"),
        ("Acheté chez Asmodee.", "fournisseur"),
        ("Produit FICTIF_X.", "fictive"),
        ("TODO compléter.", "marqueur"),
        ("Dépêchez-vous !", "fausse urgence"),
        ("Revendeur officiel.", "statut officiel"),
        ("Écrivez à contact@exemple.ch.", "adresse email"),
        ("Appelez le +41 22 000 00 00.", "téléphone"),
        ("Commande [NUMERO_COMMANDE].", "variable de cas"),
        ("Valeur ⟦à valider⟧.", "marque d'aperçu"),
    ],
)
def test_public_hygiene_flags(ctx: v.Context, injected: str, label: str) -> None:
    edit(ctx.legal / "CGV.md", "### 16. Contact", f"{injected}\n\n### 16. Contact")
    assert_flags(v.check_public_hygiene(ctx), label)


def test_internal_notes_are_not_public(ctx: v.Context) -> None:
    edit(
        ctx.legal / "CGV.md",
        "## Notes pour le juriste (ne pas publier)",
        "## Notes pour le juriste (ne pas publier)\n\nmarge interne, agent, Asmodee.",
    )
    assert v.check_public_hygiene(ctx) == []


@pytest.mark.parametrize(
    ("doc", "needle"),
    [
        ("CGV.md", "CVIM"),
        ("CGV.md", "art. 197 ss du Code des obligations"),
        ("CGV.md", "{{MENTION_TVA}}"),
        ("CONFIDENTIALITE.md", "art. 25 LPD"),
        ("MENTIONS_LEGALES.md", "{{NUMERO_IDE}}"),
        ("COOKIES.md", "Paramètres des cookies"),
        ("PRECOMMANDES.md", "dans l'ordre de leur paiement"),
    ],
)
def test_required_clause_missing(ctx: v.Context, doc: str, needle: str) -> None:
    path = next(p for p in ctx.public_docs() if p.name == doc)
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(needle, "supprimé"), encoding="utf-8")
    assert_flags(v.check_required_public_clauses(ctx), needle)


def test_lcd_checklist_obligation_missing(ctx: v.Context) -> None:
    edit(ctx.legal / "CHECKLIST_LCD_ECOMMERCE.md", "LCD art. 3 al. 1 let. s ch. 2", "LCD")
    assert_flags(v.check_lcd_checklist(ctx), "ch. 2")


def test_lcd_checklist_source_and_date(ctx: v.Context) -> None:
    path = ctx.legal / "CHECKLIST_LCD_ECOMMERCE.md"
    text = path.read_text(encoding="utf-8").replace(v.S11_URL, "https://exemple.invalid").replace("4.10.2026", "x")
    path.write_text(text, encoding="utf-8")
    errors = v.check_lcd_checklist(ctx)
    assert_flags(errors, "S11")
    assert_flags(errors, "date")


def test_lcd_checklist_ids_and_blocking(ctx: v.Context) -> None:
    path = ctx.legal / "CHECKLIST_LCD_ECOMMERCE.md"
    edit(path, "| L-03 |", "| L-02 |")
    edit(path, "| R-A04, R-A07 | O |", "| R-A04, R-A07 | X |")
    errors = v.check_lcd_checklist(ctx)
    assert_flags(errors, "non consécutifs")
    assert_flags(errors, "O ou N")


def test_recette_prefilled_result(ctx: v.Context) -> None:
    path = ctx.ops / "RECETTE_AVANT_OUVERTURE.md"
    text = path.read_text(encoding="utf-8")
    line = next(li for li in text.splitlines() if li.startswith("| R-A01 |"))
    path.write_text(text.replace(line, line[: -len("| | | |")] + "| OK | OK | capture |"), encoding="utf-8")
    assert_flags(v.check_recette(ctx), "pré-rempli")


def test_recette_summary_mismatch(ctx: v.Context) -> None:
    edit(ctx.ops / "RECETTE_AVANT_OUVERTURE.md", "| C. Prix | 8 |", "| C. Prix | 7 |")
    assert_flags(v.check_recette(ctx), "section C")


def test_recette_total_mismatch(ctx: v.Context) -> None:
    edit(ctx.ops / "RECETTE_AVANT_OUVERTURE.md", "| **Total** | **69** |", "| **Total** | **70** |")
    assert_flags(v.check_recette(ctx), "total")


def test_recette_duplicate_and_gap(ctx: v.Context) -> None:
    edit(ctx.ops / "RECETTE_AVANT_OUVERTURE.md", "| R-B07 |", "| R-B06 |")
    errors = v.check_recette(ctx)
    assert_flags(errors, "dupliqués")
    assert_flags(errors, "section B")


def test_recette_blocking_value(ctx: v.Context) -> None:
    edit(ctx.ops / "RECETTE_AVANT_OUVERTURE.md", "| R-B07 | N |", "| R-B07 | peut-être |")
    assert_flags(v.check_recette(ctx), "O ou N")


def test_recette_column_count(ctx: v.Context) -> None:
    edit(ctx.ops / "RECETTE_AVANT_OUVERTURE.md", "| R-K04 | O |", "| R-K04 | O | extra |")
    assert_flags(v.check_recette(ctx), "colonnes")


def test_recette_topic_not_covered(ctx: v.Context) -> None:
    edit(ctx.ops / "RECETTE_AVANT_OUVERTURE.md", "en même temps", "successivement")
    assert_flags(v.check_recette(ctx), "stock simultané")


def test_recette_sections_and_headers(ctx: v.Context) -> None:
    path = ctx.ops / "RECETTE_AVANT_OUVERTURE.md"
    edit(path, "### K. Incidents", "### Z. Incidents")
    edit(path, "| Résultat obtenu |", "| Résultat |")
    errors = v.check_recette(ctx)
    assert_flags(errors, "sections A à K")
    assert_flags(errors, "en-tête")


def test_sav_model_missing(ctx: v.Context) -> None:
    edit(ctx.ops / "SOP_SAV_RETOURS.md", "**SAV-M14 — ", "**Modèle — ")
    assert_flags(v.check_sav_matrix(ctx), "SAV-M14 cité mais non rédigé")


def test_sav_model_unused(ctx: v.Context) -> None:
    path = ctx.ops / "SOP_SAV_RETOURS.md"
    anchor = "## 5. Contrôle physique d'un retour"
    edit(path, anchor, f"**SAV-M15 — Inutilisé**\n> texte\n\n{anchor}")
    assert_flags(v.check_sav_matrix(ctx), "SAV-M15 jamais utilisé")


def test_sav_cases_gap_and_topic(ctx: v.Context) -> None:
    path = ctx.ops / "SOP_SAV_RETOURS.md"
    edit(path, "| SAV-26 |", "| SAV-27 |")
    edit(path, "Rétrofacturation", "Contestation")
    errors = v.check_sav_matrix(ctx)
    assert_flags(errors, "non consécutifs")
    assert_flags(errors, "Rétrofacturation")


def test_sav_models_gap(ctx: v.Context) -> None:
    edit(ctx.ops / "SOP_SAV_RETOURS.md", "**SAV-M02 — ", "**SAV-M99 — ")
    assert_flags(v.check_sav_matrix(ctx), "modèles non consécutifs")


def test_incident_type_and_steps(ctx: v.Context) -> None:
    path = ctx.ops / "SOP_INCIDENTS.md"
    edit(path, "**Survente**", "**Autre**")
    edit(path, "| 5. Test |", "| 5. Essai |")
    errors = v.check_incidents(ctx)
    assert_flags(errors, "Survente")
    assert_flags(errors, "étapes")


def test_incident_codes_gap(ctx: v.Context) -> None:
    edit(ctx.ops / "SOP_INCIDENTS.md", "| INC-16 |", "| INC-17 |")
    assert_flags(v.check_incidents(ctx), "non consécutifs")


@pytest.mark.parametrize("ref", ["SAV-99", "SAV-M40", "INC-42", "R-K09", "L-77"])
def test_dangling_reference(ctx: v.Context, ref: str) -> None:
    edit(ctx.ops / "README.md", "## Répartition des rôles", f"Voir {ref}.\n\n## Répartition des rôles")
    assert_flags(v.check_cross_references(ctx), ref)


def test_internal_path_missing(ctx: v.Context) -> None:
    edit(
        ctx.ops / "README.md",
        "## Répartition des rôles",
        "Voir `docs/07-ops/INEXISTANT.md`.\n\n## Répartition des rôles",
    )
    assert_flags(v.check_internal_paths(ctx), "INEXISTANT.md")


def test_stoploss_value_changed_in_sop(ctx: v.Context) -> None:
    edit(ctx.ops / "SOP_INCIDENTS.md", "réserve de 1 600 CHF", "réserve de 1 500 CHF")
    assert_flags(v.check_stoploss_alignment(ctx), "1 600 CHF")


def test_stoploss_follows_engine_config(ctx: v.Context) -> None:
    edit(ctx.pricing_config, 'hard_floor_margin: "0.12"', 'hard_floor_margin: "0.15"')
    assert_flags(v.check_stoploss_alignment(ctx), "15 %")


def test_stoploss_mandate_value(ctx: v.Context) -> None:
    edit(ctx.ops / "SOP_INCIDENTS.md", "45 jours sans vente", "50 jours sans vente")
    assert_flags(v.check_stoploss_alignment(ctx), "45 jours")


def test_stoploss_unreadable_config(ctx: v.Context) -> None:
    ctx.pricing_config.unlink()
    assert_flags(v.check_stoploss_alignment(ctx), "illisible")


def test_stoploss_expectations_values() -> None:
    assert v.stoploss_expectations(v.Context.default()) == ["12 %", "8 CHF", "25 %", "1 600 CHF"]


def test_readme_counts(ctx: v.Context) -> None:
    edit(ctx.ops / "README.md", "76 cas de test", "75 cas de test")
    edit(ctx.ops / "README.md", "14 modèles de réponse", "13 modèles de réponse")
    edit(ctx.legal / "README.md", "25 obligations", "24 obligations")
    errors = v.check_readme_counts(ctx)
    assert_flags(errors, "recette")
    assert_flags(errors, "modèles")
    assert_flags(errors, "obligations")


def test_readme_counts_sav_and_incidents(ctx: v.Context) -> None:
    edit(ctx.ops / "README.md", "Matrice de 26 cas", "Matrice de 25 cas")
    edit(ctx.ops / "README.md", "INC-01 à INC-16", "INC-01 à INC-15")
    errors = v.check_readme_counts(ctx)
    assert_flags(errors, "cas SAV")
    assert_flags(errors, "INC-01 à INC-16")


def test_preview_stale_after_source_change(ctx: v.Context) -> None:
    edit(ctx.legal / "CGV.md", "### 16. Contact", "### 16. Nous contacter")
    assert_flags(v.check_previews_up_to_date(ctx), "périmé : CGV.md")


def test_preview_stale_after_registry_change(ctx: v.Context) -> None:
    edit_registry(ctx, lambda d: d["champs"]["DELAI_EXPEDITION"].update(valeur_proposee="2 jours ouvrés"))
    errors = v.check_previews_up_to_date(ctx)
    assert any("périmé" in e for e in errors)


def test_preview_orphan_and_missing(ctx: v.Context) -> None:
    (ctx.apercu / "ANCIEN.md").write_text("x", encoding="utf-8")
    (ctx.apercu / "COOKIES.md").unlink()
    errors = v.check_previews_up_to_date(ctx)
    assert_flags(errors, "orphelin : ANCIEN.md")
    assert_flags(errors, "manquant : COOKIES.md")


def test_previews_skipped_if_public_doc_missing(ctx: v.Context) -> None:
    (ctx.legal / "COOKIES.md").unlink()
    assert v.check_previews_up_to_date(ctx) == []


# ----------------------------------------------------------------- registre des champs
def test_parse_registry_statuses() -> None:
    fields = rc.parse_registry(
        registry(
            A={"statut": "a_remplir"},
            B={"statut": "a_valider", "valeur_proposee": "14 jours"},
            C={"statut": "valide", "valeur": "CHF", "valide_par": "Propriétaire, 1.11.2026"},
            D={"alias_de": "C"},
        )
    )
    assert fields["A"].value is None and fields["A"].status is rc.Status.A_REMPLIR
    assert fields["B"].value == "14 jours" and fields["B"].status is rc.Status.A_VALIDER
    assert fields["C"].value == "CHF" and fields["C"].validated_by
    assert fields["D"].status is rc.Status.VALIDE and fields["D"].value == "CHF" and fields["D"].alias_of == "C"


@pytest.mark.parametrize(
    ("spec", "needle"),
    [
        ({"x": {"statut": "a_remplir"}}, "nom invalide"),
        ({"A": "texte"}, "dictionnaire"),
        ({"A": {"statut": "a_remplir", "couleur": "bleu"}}, "clés inconnues"),
        ({"A": {"statut": "inconnu"}}, "statut « inconnu »"),
        ({"A": {}}, "« statut » manquant"),
        ({"A": {"statut": "a_remplir", "valeur_proposee": "x"}}, "a_remplir sans valeur"),
        ({"A": {"statut": "a_valider"}}, "sans valeur_proposee"),
        ({"A": {"statut": "a_valider", "valeur_proposee": "x", "valeur": "y"}}, "réservée au statut valide"),
        ({"A": {"statut": "valide", "valide_par": "P"}}, "sans « valeur »"),
        ({"A": {"statut": "valide", "valeur": "x"}}, "valide_par"),
        ({"A": {"statut": "a_valider", "valeur_proposee": "  "}}, "texte non vide"),
        ({"A": {"alias_de": "Z"}}, "alias vers un champ inconnu"),
        ({"A": {"alias_de": "B", "statut": "a_remplir"}, "B": {"statut": "a_remplir"}}, "ne porte pas de « statut »"),
        ({"A": {"alias_de": "B"}, "B": {"alias_de": "C"}, "C": {"statut": "a_remplir"}}, "alias d'un alias"),
        ({"A": {"alias_de": ""}}, "nom de champ"),
    ],
)
def test_parse_registry_errors(spec: dict[str, Any], needle: str) -> None:
    data = registry(**{k: val for k, val in spec.items() if isinstance(val, dict)})
    for k, val in spec.items():
        if not isinstance(val, dict):
            data["champs"][k] = val
    with pytest.raises(rc.RegistryError) as exc:
        rc.parse_registry(data)
    assert any(needle in e for e in exc.value.errors), exc.value.errors


def test_parse_registry_missing_description() -> None:
    data = {"champs": {"A": {"statut": "a_remplir", "decideur": "x", "source": "s"}}}
    with pytest.raises(rc.RegistryError, match="description"):
        rc.parse_registry(data)


@pytest.mark.parametrize("data", [None, {}, {"champs": {}}, {"champs": []}])
def test_parse_registry_empty(data: Any) -> None:
    with pytest.raises(rc.RegistryError, match="section"):
        rc.parse_registry(data)


def test_placeholders_ignore_prose_ellipsis() -> None:
    assert rc.placeholders("a {{A}} b {{…}} c {{ B }} {{A}}") == ["A", "B", "A"]


def test_public_blocks_parsing() -> None:
    s, e = rc.PUBLIC_START, rc.PUBLIC_END
    assert rc.public_blocks("rien") == []
    assert rc.public_blocks(f"x\n{s}\nun\n{e}\ny\n{s}\ndeux\n{e}") == ["un", "deux"]
    for bad, msg in [
        (f"{s} sans fin", "sans balise de fin"),
        (f"{e} {s} x {e}", "fin sans balise de début"),
        (f"{s} {s} x {e} {e}", "imbriqués"),
    ]:
        with pytest.raises(rc.BlockError, match=msg):
            rc.public_blocks(bad)


@pytest.fixture()
def fields() -> dict[str, rc.Field]:
    return rc.parse_registry(
        registry(
            VIDE={"statut": "a_remplir"},
            PROPOSE={"statut": "a_valider", "valeur_proposee": "14 jours"},
            OK={"statut": "valide", "valeur": "Genève", "valide_par": "P"},
            ALIAS={"alias_de": "OK"},
            IMBRIQUE={"statut": "valide", "valeur": "à {{OK}}", "valide_par": "P"},
            BOUCLE={"statut": "valide", "valeur": "{{BOUCLE}}", "valide_par": "P"},
        )
    )


def test_render_preview(fields: dict[str, rc.Field]) -> None:
    out = rc.render("{{OK}} / {{ALIAS}} / {{PROPOSE}} / {{VIDE}} / {{IMBRIQUE}} / {{…}}", fields)
    assert out == "Genève / Genève / 14 jours ⟦à valider⟧ / ⟦À REMPLIR : VIDE⟧ / à Genève / {{…}}"


def test_render_unknown_and_cycle(fields: dict[str, rc.Field]) -> None:
    with pytest.raises(rc.RenderError) as exc:
        rc.render("{{INCONNU}} {{BOUCLE}}", fields)
    assert any("champ inconnu : INCONNU" in e for e in exc.value.errors)
    assert any("cyclique" in e for e in exc.value.errors)


def test_render_publication(fields: dict[str, rc.Field]) -> None:
    assert rc.render("{{OK}} {{IMBRIQUE}}", fields, rc.Mode.PUBLICATION) == "Genève à Genève"
    with pytest.raises(rc.RenderError) as exc:
        rc.render("{{PROPOSE}} {{VIDE}}", fields, rc.Mode.PUBLICATION)
    assert exc.value.errors == ["champ non validé : PROPOSE", "champ non validé : VIDE"]


def test_render_public_requires_block(fields: dict[str, rc.Field]) -> None:
    with pytest.raises(rc.BlockError):
        rc.render_public("pas de bloc", fields)
    text = f"interne {{{{INCONNU}}}}\n{rc.PUBLIC_START}\nà {{{{OK}}}}\n{rc.PUBLIC_END}\n"
    assert rc.render_public(text, fields) == "à Genève\n"


# --------------------------------------------------------------------------- rendu CLI
def test_previews_on_disk_are_current() -> None:
    assert rt.stale_previews(rt.build_previews()) == []


def test_registry_version() -> None:
    assert rt.registry_version() == "2026-10-04"


def test_write_and_check_previews(tmp_path: Path) -> None:
    previews = {"A.md": "a\n", "B.md": "b\n"}
    (tmp_path / "VIEUX.md").write_text("x", encoding="utf-8")
    written = rt.write_previews(previews, tmp_path)
    assert sorted(p.name for p in written) == ["A.md", "B.md"]
    assert not (tmp_path / "VIEUX.md").exists()
    assert rt.stale_previews(previews, tmp_path) == []
    (tmp_path / "A.md").write_text("modifié", encoding="utf-8")
    (tmp_path / "B.md").unlink()
    assert rt.stale_previews(previews, tmp_path) == [
        "aperçu périmé : A.md (relancer rendre_textes.py)",
        "aperçu manquant : B.md",
    ]


def test_publish_refused_today(tmp_path: Path) -> None:
    with pytest.raises(rc.RenderError) as exc:
        rt.publish(tmp_path / "sortie")
    assert any("CGV.md : champ non validé : RAISON_SOCIALE" in e for e in exc.value.errors)
    assert not (tmp_path / "sortie").exists()


def test_publish_when_everything_is_validated(tmp_path: Path) -> None:
    validated = {}
    for name, field in rc.load_registry().items():
        validated[name] = replace(field, status=rc.Status.VALIDE, value=field.value or f"valeur de {name}")
    paths = rt.publish(tmp_path, fields=validated)
    assert {p.name for p in paths} == {p.name for p in rt.PUBLIC_DOCS}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "{{" not in text.replace("{{…}}", "") and "⟦" not in text
        assert "Validation humaine requise" not in text and "Notes pour le juriste" not in text


def test_main_writes_and_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rt, "APERCU_DIR", tmp_path / "apercu")
    assert rt.main([]) == 0
    assert len(list((tmp_path / "apercu").glob("*.md"))) == len(rt.PUBLIC_DOCS)
    assert rt.main(["--verifier"]) == 0
    (tmp_path / "apercu" / "CGV.md").write_text("modifié", encoding="utf-8")
    assert rt.main(["--verifier"]) == 1
    assert "périmé : CGV.md" in capsys.readouterr().out


def test_main_publication_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert rt.main(["--publication", "--sortie", str(tmp_path / "out")]) == 1
    assert "REFUS" in capsys.readouterr().out


def test_main_publication_requires_output() -> None:
    with pytest.raises(SystemExit) as exc:
        rt.main(["--publication"])
    assert exc.value.code == 2


def test_preview_header_marks_draft() -> None:
    previews = rt.build_previews()
    for content in previews.values():
        assert content.startswith("<!-- FICHIER GÉNÉRÉ")
        assert "NE PAS PUBLIER" in content and v.BANNER in content


# ------------------------------------------------------------------ revue F5a (CON-02, 03, 06, 16, 17, 21)
#: Champs connus seulement après la boutique (B15), le paiement (B16), le transporteur (B17) ou la relecture J28 (C11).
CHAMPS_APRES_J10 = {
    "ST_PAIEMENT", "ST_PAIEMENT_PAYS", "PSP_NOM", "ST_TRANSPORT", "ST_TRANSPORT_PAYS", "ST_BOUTIQUE", "ST_BOUTIQUE_PAYS",
    "URL_COOKIES", "DATE_VERSION", "ST_AUDIENCE", "ST_AUDIENCE_PAYS",
}


def test_landing_notice_is_published_and_publishable_at_j10() -> None:
    """CON-06 : la landing a sa propre notice, sans champ connu seulement après J10."""
    notice = rc.LEGAL_DIR / "CONFIDENTIALITE_LANDING.md"
    assert notice in rt.PUBLIC_DOCS and notice.name in v.LEGAL_FILES
    used = set(rc.placeholders("\n".join(rc.public_blocks(notice.read_text(encoding="utf-8")))))
    assert used and not used & CHAMPS_APRES_J10, used & CHAMPS_APRES_J10
    assert "DATE_VERSION_LANDING" in used


def test_privacy_declarations_cover_optional_answers_and_abandoned_cart() -> None:
    """CON-03 et CON-21 : toutes les données collectées et finalités sont déclarées."""
    full = "\n".join(rc.public_blocks((rc.LEGAL_DIR / "CONFIDENTIALITE.md").read_text(encoding="utf-8")))
    for needle in ("Réponses facultatives", "budget", "canton", "utm", "agrégée", "Panier non finalisé",
                   "{{DUREE_CONSERVATION_PANIER}}", "passage en caisse"):
        assert needle in full, needle
    landing = "\n".join(rc.public_blocks((rc.LEGAL_DIR / "CONFIDENTIALITE_LANDING.md").read_text(encoding="utf-8")))
    for needle in ("Prénom", "budget", "pour qui", "canton", "utm", "agrégée", "Adresse IP", "aucun cookie"):
        assert needle in landing, needle


def test_missing_cart_row_detected(ctx: v.Context) -> None:
    edit(ctx.legal / "CONFIDENTIALITE.md", "| Panier non finalisé |", "| Panier |")
    assert_flags(v.check_required_public_clauses(ctx), "Panier non finalisé")


def test_customer_cancellation_in_cgv_and_faq() -> None:
    """CON-17 : la FAQ ne promet rien que les CGV (qui font foi) ne prévoient."""
    cgv = "\n".join(rc.public_blocks((rc.LEGAL_DIR / "CGV.md").read_text(encoding="utf-8")))
    assert "4.7 **Annulation de votre part avant préparation.**" in cgv
    faq = (rc.OPS_DIR / "FAQ_CLIENTS.md").read_text(encoding="utf-8")
    assert "(CGV ch. 4.7)" in faq


def test_human_reply_claim_flagged(ctx: v.Context) -> None:
    """CON-02 : « une personne vous répond » est faux (réponses courantes automatisées)."""
    edit(ctx.ops / "FAQ_CLIENTS.md", "Une personne traite les cas particuliers", "Une personne vous répond toujours")
    assert_flags(v.check_public_hygiene(ctx), "service client")


def test_unusual_clause_not_attributed_to_art_8_lcd() -> None:
    """CON-16 : la règle de l'insolite est jurisprudentielle ; l'art. 8 LCD vise les clauses abusives."""
    cgv = (rc.LEGAL_DIR / "CGV.md").read_text(encoding="utf-8")
    assert "insolite (art. 8 LCD)" not in cgv
    assert cgv.count("règle jurisprudentielle de l'insolite") >= 2 and "ATF 135 III 1" in cgv
