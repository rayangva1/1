"""Tests de docs/06-contenu : calendrier, sujets, scripts, emails, publicité, SEO.

Lancer : python -m pytest docs/06-contenu/outils -q
"""

from __future__ import annotations

import csv
import io
import re
import sys
from datetime import date
from pathlib import Path

import pytest

OUTILS = Path(__file__).resolve().parent
sys.path.insert(0, str(OUTILS))

import generer_calendrier as gc  # noqa: E402
import generer_emails as ge  # noqa: E402
import verifier_contenu as vc  # noqa: E402

RACINE = OUTILS.parent


# ----------------------------------------------------------------------------- ensemble
def test_tous_les_controles_passent() -> None:
    resultats = vc.tout_verifier()
    assert resultats == {k: [] for k in resultats}, resultats


# ----------------------------------------------------------------------------- calendrier
def _csv(modifier) -> str:  # type: ignore[no-untyped-def]
    lignes = list(csv.DictReader(io.StringIO(gc.contenu_csv())))
    modifier(lignes)
    tampon = io.StringIO()
    w = csv.DictWriter(tampon, fieldnames=gc.COLONNES, lineterminator="\n")
    w.writeheader()
    w.writerows(lignes)
    return tampon.getvalue()


def test_calendrier_trois_publications_par_semaine_apres_ouverture() -> None:
    lignes = list(csv.DictReader(io.StringIO(gc.contenu_csv())))
    for numero in range(6, 14):
        piliers = sorted(lg["Pilier"] for lg in lignes if lg["Type"] == "Publication" and lg["Semaine"] == f"S{numero}")
        if numero == 12:
            assert len(piliers) >= 2
        else:
            assert piliers == ["Guide", "Nouveauté accessible", "Preuve de service"], (numero, piliers)


def test_calendrier_aucun_contenu_stock_avant_reception() -> None:
    for lg in csv.DictReader(io.StringIO(gc.contenu_csv())):
        if lg["Pilier"] == "Nouveauté accessible":
            assert int(lg["J"][1:]) >= gc.J_OUVERTURE > gc.J_RECEPTION


def test_calendrier_detecte_nouveaute_avant_ouverture() -> None:
    def avancer(lignes: list[dict[str, str]]) -> None:
        cible = next(lg for lg in lignes if lg["Pilier"] == "Nouveauté accessible")
        cible["J"], cible["Date"], cible["Jour"] = "J20", "2026-10-24", "samedi"

    erreurs = vc.verifier_calendrier(_csv(avancer), controler_synchro=False)
    assert any("avant l'ouverture" in e for e in erreurs)


@pytest.mark.parametrize(
    ("champ", "valeur", "attendu"),
    [
        ("Accroche", "Display à CHF 189.90 seulement", "prix"),
        ("Accroche", "Dernières pièces, foncez", "fausse urgence"),
        ("Accroche", "Un vrai investissement", "promesse interdite"),
        ("Nom", "Notre fournisseur nous livre", "terme interne"),
    ],
)
def test_calendrier_detecte_les_textes_interdits(champ: str, valeur: str, attendu: str) -> None:
    def modifier(lignes: list[dict[str, str]]) -> None:
        lignes[5][champ] = valeur

    assert any(attendu in e for e in vc.verifier_calendrier(_csv(modifier), controler_synchro=False))


def test_calendrier_detecte_deux_recapitulatifs_la_meme_semaine() -> None:
    def doubler(lignes: list[dict[str, str]]) -> None:
        recap = next(lg for lg in lignes if lg["Format"].startswith("Email 05"))
        lignes.append(dict(recap))

    assert any("récapitulatifs" in e for e in vc.verifier_calendrier(_csv(doubler), controler_synchro=False))


def test_calendrier_detecte_pilier_manquant_et_desynchronisation() -> None:
    def retirer(lignes: list[dict[str, str]]) -> None:
        lignes[:] = [lg for lg in lignes if not (lg["Semaine"] == "S8" and lg["Pilier"] == "Guide" and lg["Type"] == "Publication")]

    erreurs = vc.verifier_calendrier(_csv(retirer))
    assert any("S8 : pilier « Guide » absent" in e for e in erreurs)
    assert any("désynchronisé" in e for e in erreurs)


def test_calendrier_couvre_les_15_sujets_et_colonnes_notion() -> None:
    texte = gc.contenu_csv()
    lignes = list(csv.DictReader(io.StringIO(texte)))
    assert tuple(lignes[0]) == gc.COLONNES and gc.COLONNES[0] == "Nom"
    sujets = {s.strip() for lg in lignes if lg["Type"] == "Publication" for s in lg["Sujet"].split(",")}
    assert {f"S{n:02d}" for n in range(1, 16)} <= sujets
    assert lignes[0]["Date"] >= "2026-10-05" and lignes[-1]["Date"] <= "2027-01-02"


def test_calendrier_decalage_de_j1() -> None:
    decale = list(csv.DictReader(io.StringIO(gc.contenu_csv(date(2026, 10, 12)))))
    origine = list(csv.DictReader(io.StringIO(gc.contenu_csv())))
    assert all((date.fromisoformat(a["Date"]) - date.fromisoformat(b["Date"])).days == 7 for a, b in zip(decale, origine))
    assert gc.main(["--j1", "2026-10-06"]) == 1  # un mardi est refusé


# ----------------------------------------------------------------------------- sujets et scripts
def test_sujets_detecte_fiche_incomplete() -> None:
    texte = (RACINE / "15_SUJETS.md").read_text(encoding="utf-8")
    abime = texte.replace("### S07 —", "### X07 —").replace("- **Hook** : « Offrir", "- Hook : « Offrir")
    erreurs = vc.verifier_sujets(abime)
    assert any("S07 absente" in e for e in erreurs) and any("S04 sans Hook" in e for e in erreurs)


def test_scripts_durees_et_contiguite() -> None:
    texte = (RACINE / "SCRIPTS_VIDEO.md").read_text(encoding="utf-8")
    scripts = re.findall(r"^### (V\d) — .*?\((\d+) s\)", texte, re.MULTILINE)
    assert len(scripts) == 8 and all(20 <= int(d) <= 45 for _, d in scripts)
    abime = texte.replace("| 2 | 3-10 s | Main qui tourne le display", "| 2 | 4-10 s | Main qui tourne le display")
    assert any("V1 : plans non contigus" in e for e in vc.verifier_scripts(abime))
    trop_long = texte.replace("### V7 — Lire une fiche : les 3 statuts (20 s)", "### V7 — Lire une fiche : les 3 statuts (50 s)")
    assert any("V7" in e and "durée" in e for e in vc.verifier_scripts(trop_long))


# ----------------------------------------------------------------------------- emails
def test_variables_selon_le_canal() -> None:
    n8n = ge.Rendu("n8n", {}, {})
    shop = ge.Rendu("shopify", {}, {})
    assert ge.en_html("Bonjour [[prenom]]", n8n) == "Bonjour {{ $json.prenom }}"
    assert ge.en_html("Total [[total_price | money]]", shop) == "Total {{ total_price | money }}"
    assert ge.variable("salutation", shop).startswith("Bonjour{% if customer.first_name %}")
    with pytest.raises(ge.EmailError):
        ge.variable("prix | money", n8n)
    lien = ge.en_html("[Guide]([[url_guide]]) et **gras** <b>", n8n)
    assert '<a href="{{ $json.url_guide }}"' in lien and "<strong>gras</strong>" in lien and "&lt;b&gt;" in lien


def test_source_refuse_variable_non_declaree(tmp_path: Path) -> None:
    texte = ge.SOURCE.read_text(encoding="utf-8").replace("[[duree_validite_lien]].", "[[variable_inconnue]].")
    source = tmp_path / "emails.yaml"
    source.write_text(texte, encoding="utf-8")
    with pytest.raises(ge.EmailError, match="variable_inconnue"):
        ge.charger_source(source)


def test_quatorze_emails_et_generation_deterministe() -> None:
    source = ge.charger_source()
    ids = [e["id"] for e in source["emails"]]
    assert len(ids) == 14 and ids == sorted(ids)
    for attendu in ("bienvenue", "alerte-stock-local", "confirmation-commande", "expedition-suivi", "demande-avis",
                    "reachat", "desinscription", "precommande-confirmee", "precommande-report"):
        assert any(attendu in i for i in ids), attendu
    assert ge.fichiers_generes() == ge.fichiers_generes()


def test_emails_marketing_ont_desinscription_et_preferences() -> None:
    for e in ge.charger_source()["emails"]:
        html = (ge.EMAILS / "html" / f"{e['id']}.html").read_text(encoding="utf-8")
        texte = (ge.EMAILS / "texte" / f"{e['id']}.txt").read_text(encoding="utf-8")
        if e["categorie"] == "marketing":
            for contenu in (html, texte):
                assert "{{ $json.url_desinscription }}" in contenu and "{{ $json.url_preferences }}" in contenu
        if e["categorie"] == "transactionnel":
            assert "aucune publicité" in html or e["canal"] == "n8n"


def test_verifier_email_detecte_les_defauts() -> None:
    connus = vc.champs_registre()
    base = (ge.EMAILS / "html" / "04-alerte-stock-local.html").read_text(encoding="utf-8")
    assert vc.verifier_email("x.html", base, "n8n", "marketing", connus) == []
    cas = {
        "prix en dur": base.replace("CHF {{ $json.produit_prix }}", "CHF 209.90"),
        "désinscription": base.replace("url_desinscription", "url_autre"),
        "champs hors registre": base.replace("{{EMAIL_SUPPORT}}", "{{EMAIL_INVENTE}}"),
        "balise Liquid": base.replace("</body>", "{% if x %}{% endif %}</body>"),
        "terme interne": base.replace("Voir la fiche", "Voir notre marge"),
        "fausse urgence": base.replace("Voir la fiche", "Dernières pièces"),
        "script": base.replace("</body>", "<script>x()</script></body>"),
        "mention d'indépendance": base.replace(vc.MENTION_COURTE, ""),
    }
    for attendu, contenu in cas.items():
        assert any(attendu in e for e in vc.verifier_email("x.html", contenu, "n8n", "marketing", connus)), attendu


def test_integration_refuse_puis_remplit(tmp_path: Path) -> None:
    assert ge.integrer(tmp_path / "a", "https://cdn.exemple.invalid/logo.png")  # registre non validé : refus
    assert not (tmp_path / "a").exists()
    assert ge.integrer(tmp_path / "b", "http://non-securise/logo.png")
    valeurs = {nom: f"FICTIF-{nom.lower()}" for nom in vc.champs_registre()}
    assert ge.integrer(tmp_path / "c", "https://cdn.exemple.invalid/logo.png", valeurs) == []
    commande = (tmp_path / "c" / "html" / "06-confirmation-commande.html").read_text(encoding="utf-8")
    assert not ge.CHAMP_RE.search(commande)
    assert "{{ line.final_line_price | money }}" in commande and "FICTIF-delai_expedition" in commande
    alerte = (tmp_path / "c" / "html" / "04-alerte-stock-local.html").read_text(encoding="utf-8")
    assert "{{ $json.produit_titre }}" in alerte and 'src="https://cdn.exemple.invalid/logo.png"' in alerte


def test_apercu_rempli_avec_donnees_fictives() -> None:
    apercu = (ge.EMAILS / "apercu.html").read_text(encoding="utf-8")
    assert "FICTIF" in apercu and "{{ $json" not in apercu and "{%" not in apercu
    assert apercu.count('<section id="email-') == 14
    assert "Validation humaine requise" in apercu


def test_readme_contient_le_tableau_genere() -> None:
    readme = (ge.EMAILS / "README.md").read_text(encoding="utf-8")
    assert "| 01 | [Confirmation d'inscription (double opt-in)]" in readme and "| 14 |" in readme


def test_notifications_shopify_rendues_en_liquid() -> None:
    liquid = pytest.importorskip("liquid")
    env = liquid.Environment()
    env.filters["money"] = lambda v: f"CHF {float(v):.2f}"
    commande = env.from_string((ge.EMAILS / "texte" / "06-confirmation-commande.txt").read_text(encoding="utf-8"))
    sortie = commande.render(
        order_name="#1001", customer={"first_name": "Léa"}, subtotal_price=269.80, shipping_price=9, total_price=278.80,
        discounts_amount=0, shipping_address={"name": "Léa Exemple", "address1": "Rue Fictive 1", "zip": "1200", "city": "Genève"},
        subtotal_line_items=[
            {"title": "Display — Extension Exemple — FR (FICTIF)", "quantity": 1, "final_line_price": 209.9},
            {"title": "Coffret — Extension Exemple 2 — FR — Précommande (FICTIF)", "quantity": 1, "final_line_price": 59.9},
        ],
    )
    assert "Bonjour Léa," in sortie and "CHF 209.90" in sortie and "(précommande, expédiée à part)" in sortie
    assert "Total payé : CHF 278.80" in sortie and "Réductions" not in sortie
    html = env.from_string((ge.EMAILS / "html" / "06-confirmation-commande.html").read_text(encoding="utf-8"))
    rendu = html.render(
        order_name="#1001", customer={}, subtotal_price=19.8, shipping_price=9, total_price=28.8, discounts_amount=0,
        shipping_address={"name": "L", "address1": "R", "zip": "1200", "city": "Genève"}, order_status_url="https://x.invalid",
        subtotal_line_items=[{"title": "Protège-cartes (FICTIF)", "quantity": 2, "final_price": 9.9, "final_line_price": 19.8}],
    )
    assert "Bonjour," in rendu and "Commande mixte" not in rendu and "STOCK LOCAL" in rendu
    suivi = env.from_string((ge.EMAILS / "texte" / "07-expedition-suivi.txt").read_text(encoding="utf-8")).render(
        order_name="#1001", customer={"first_name": "Léa"}, order_status_url="https://x.invalid",
        fulfillment={"fulfillment_line_items": [{"line_item": {"title": "Display (FICTIF)"}, "quantity": 1}],
                     "tracking_numbers": ["99.00.FICTIF"], "tracking_urls": ["https://suivi.invalid/1"], "tracking_company": "Transporteur FICTIF"},
    )
    assert "Display (FICTIF) × 1" in suivi and "n° 99.00.FICTIF" in suivi and "https://suivi.invalid/1" in suivi


# ----------------------------------------------------------------------------- publicité et SEO
def test_publicite_coherente_avec_le_mandat_et_le_stop_loss() -> None:
    pub = (RACINE / "PUBLICITE_TEST.md").read_text(encoding="utf-8")
    mandat = (RACINE.parents[1] / "config" / "mandate.v1.yaml").read_text(encoding="utf-8")
    stoploss = (RACINE.parents[1] / "config" / "stoploss.v1.yaml").read_text(encoding="utf-8")
    assert 'proposé : "33"' in mandat and "33 CHF" in pub
    assert 'min_spend_to_judge_chf: "20.00"' in stoploss and "dépense ≥ 20 CHF sur 7 jours" in pub
    assert 'reserve_chf: "1600"' in stoploss and "1 600 CHF" in pub
    # Exemples FICTIFS recalculés
    assert round(70 / 8, 2) == 8.75 and round(100 / 7, 2) == 14.29 and 120 / 4 == 30.0
    assert "| B | 100.00 | 8 | 1 | 7 | 14.29 | ORANGE |" in pub


def test_seo_sans_volume_chiffre() -> None:
    seo = (RACINE / "SEO.md").read_text(encoding="utf-8")
    assert not vc.VOLUME_RE.search(seo)
    assert vc.VOLUME_RE.search("display pokémon : 1 200 recherches par mois")
