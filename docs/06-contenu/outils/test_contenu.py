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
    """BP §9 : 3 publications par semaine (1 guide, 1 nouveauté accessible, 1 preuve de service), Noël compris (COH-18)."""
    lignes = list(csv.DictReader(io.StringIO(gc.contenu_csv())))
    for numero in range(6, 14):
        piliers = sorted(lg["Pilier"] for lg in lignes if lg["Type"] == "Publication" and lg["Semaine"] == f"S{numero}")
        assert piliers == ["Guide", "Nouveauté accessible", "Preuve de service"], (numero, piliers)


def test_calendrier_detecte_une_semaine_a_deux_publications() -> None:
    def retirer(lignes: list[dict[str, str]]) -> None:
        lignes[:] = [lg for lg in lignes if not (lg["Semaine"] == "S12" and lg["Pilier"] == "Nouveauté accessible")]

    erreurs = vc.verifier_calendrier(_csv(retirer), controler_synchro=False)
    assert "S12 : 2 publications (3 attendues)" in erreurs


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
    assert len(ids) == 19 and ids == sorted(ids)  # 14 + 5 emails du pré-drop (15 à 19)
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
                assert "{{ $json.url_desinscription }}" in contenu
                # Préférences d'alertes seulement pour les inscrits aux alertes (CON-09).
                assert ("{{ $json.url_preferences }}" in contenu) == (e["motif_pied"] == "alertes"), e["id"]
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
    assert apercu.count('<section id="email-') == 19
    assert "Validation humaine requise" in apercu


def test_readme_contient_le_tableau_genere() -> None:
    readme = (ge.EMAILS / "README.md").read_text(encoding="utf-8")
    assert "| 01 | [Confirmation d'inscription (double opt-in)]" in readme and "| 14 |" in readme and "| 19 |" in readme


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


# ----------------------------------------------------------------------------- revue F5a (CON-02, 07, 08, 09)
def test_titre_texte_garde_les_expressions_n8n_intactes() -> None:
    """CON-08 : la mise en majuscules du titre texte ne touche pas aux variables (n8n est sensible à la casse)."""
    assert ge.majuscules_hors_expressions("Bonjour {{ $json.titre_semaine }} [[x]] {{CHAMP}}") == (
        "BONJOUR {{ $json.titre_semaine }} [[x]] {{CHAMP}}"
    )
    assert ge.majuscules_hors_expressions("{% if a %}oui{% endif %} ⟦à valider⟧") == "{% if a %}OUI{% endif %} ⟦à valider⟧"
    for chemin in (ge.EMAILS / "texte").glob("*.txt"):
        texte = chemin.read_text(encoding="utf-8")
        assert "$JSON" not in texte and "{{ $J" not in texte, chemin.name
    recap = (ge.EMAILS / "texte" / "05-recapitulatif-hebdo.txt").read_text(encoding="utf-8")
    assert recap.splitlines()[2] == "{{ $json.titre_semaine }}"


def test_verifier_detecte_une_expression_n8n_alteree() -> None:
    base = (ge.EMAILS / "texte" / "05-recapitulatif-hebdo.txt").read_text(encoding="utf-8")
    abime = base.replace("{{ $json.titre_semaine }}\n", "{{ $JSON.TITRE_SEMAINE }}\n", 1)
    assert any("expression n8n altérée" in e for e in vc.verifier_email("x.txt", abime, "n8n", "marketing", vc.champs_registre()))


def test_pied_conforme_au_segment() -> None:
    """CON-09 : 12 (clients) et 13 (consentement au checkout) ne se disent pas « inscrits à nos alertes »."""
    source = {e["id"]: e for e in ge.charger_source()["emails"]}
    assert source["12-reachat"]["motif_pied"] == "client" and source["13-panier-abandonne"]["motif_pied"] == "checkout"
    reachat = (ge.EMAILS / "texte" / "12-reachat.txt").read_text(encoding="utf-8")
    panier = (ge.EMAILS / "texte" / "13-panier-abandonne.txt").read_text(encoding="utf-8")
    for texte in (reachat, panier):
        assert "inscrite à nos alertes" not in texte and "Modifier mes préférences" not in texte
        assert "Me désinscrire en un clic : {{ $json.url_desinscription }}" in texte
    assert "avez commandé chez nous" in reachat
    assert "lors de votre passage en caisse le {{ $json.date_consentement }}" in panier
    alerte = (ge.EMAILS / "texte" / "04-alerte-stock-local.txt").read_text(encoding="utf-8")
    assert "inscrite à nos alertes" in alerte and "Modifier mes préférences" in alerte


def test_source_refuse_un_motif_absent_ou_incoherent(tmp_path: Path) -> None:
    texte = ge.SOURCE.read_text(encoding="utf-8")
    sans_motif = tmp_path / "a.yaml"
    sans_motif.write_text(texte.replace("    motif_pied: checkout\n", "", 1), encoding="utf-8")
    with pytest.raises(ge.EmailError, match="13-panier-abandonne : motif_pied obligatoire"):
        ge.charger_source(sans_motif)
    incoherent = tmp_path / "b.yaml"
    incoherent.write_text(texte.replace("    motif_pied: checkout\n", "    motif_pied: alertes\n", 1), encoding="utf-8")
    with pytest.raises(ge.EmailError, match="incohérent avec le segment"):
        ge.charger_source(incoherent)
    base = (ge.EMAILS / "texte" / "04-alerte-stock-local.txt").read_text(encoding="utf-8")
    assert any("faux pour ce segment" in e for e in vc.verifier_email("x.txt", base, "n8n", "marketing", vc.champs_registre(), "checkout"))


def test_emails_sans_affirmation_inexacte() -> None:
    """CON-02 et CON-07 : aucune promesse de réponse humaine systématique ni de limite « par commande »."""
    for dossier in ("html", "texte"):
        for chemin in (ge.EMAILS / dossier).glob("*"):
            contenu = chemin.read_text(encoding="utf-8")
            for motif, libelle in vc.AFFIRMATIONS_INEXACTES:
                assert not motif.search(contenu), (chemin.name, libelle)
    avis = (ge.EMAILS / "texte" / "11-demande-avis.txt").read_text(encoding="utf-8")
    assert "une personne reprend votre demande si vous le souhaitez" in avis
    ouverture = (ge.EMAILS / "texte" / "03-ouverture-boutique.txt").read_text(encoding="utf-8")
    assert "Une limite par foyer, toutes commandes confondues" in ouverture
    base = (ge.EMAILS / "texte" / "11-demande-avis.txt").read_text(encoding="utf-8")
    abime = base.replace("Nous vous répondons", "Une personne vous répond")
    assert any("service client" in e for e in vc.verifier_email("x.txt", abime, "n8n", "avis", vc.champs_registre()))


def test_textes_reutilisables_sans_champ_hors_registre(tmp_path: Path) -> None:
    """CON-07 : {{LIMITE_PAR_COMMANDE}} n'existait dans aucun registre (une valeur, un endroit)."""
    assert vc.verifier_textes_reutilisables() == []
    copie = tmp_path / "contenu"
    copie.mkdir()
    ton = (RACINE / "TON_EDITORIAL.md").read_text(encoding="utf-8")
    (copie / "TON_EDITORIAL.md").write_text(
        ton.replace("« Limite : {{LIMITE_PAR_CLIENT}}, toutes commandes confondues", "« Limite : {{LIMITE_PAR_COMMANDE}} par commande"),
        encoding="utf-8",
    )
    erreurs = " ".join(vc.verifier_textes_reutilisables(copie))
    assert "{{LIMITE_PAR_COMMANDE}} absent du registre" in erreurs and "par commande" in erreurs


# ----------------------------------------------------------------------------- pré-drop (étape 3, 6.10.2026)
def test_emails_du_pre_drop_reprennent_la_garantie_du_moteur_mot_pour_mot() -> None:
    garantie, difference = vc.textes_garantie()
    assert "pas le produit" in garantie and "Aucun remboursement de la différence" in difference
    source = {e["id"]: e for e in ge.charger_source()["emails"]}
    for ident in vc.EMAILS_GARANTIE:
        texte = (ge.EMAILS / "texte" / f"{ident}.txt").read_text(encoding="utf-8")
        assert garantie in texte and difference in texte, ident
    # Annonces (16, 17) : emails marketing aux inscrits des alertes ; 15, 18, 19 : transactionnels.
    assert {source[i]["categorie"] for i in ("16-pre-drop-acces-prioritaire", "17-pre-drop-ouverture")} == {"marketing"}
    assert {source[i]["motif_pied"] for i in ("16-pre-drop-acces-prioritaire", "17-pre-drop-ouverture")} == {"alertes"}
    for ident in ("15-pre-drop-reservation-confirmee", "18-pre-drop-remboursement", "19-pre-drop-expedition-prioritaire"):
        assert source[ident]["categorie"] == "transactionnel", ident
    # 18 : montant et motif du moteur, jamais un prix en dur ; supplément compris.
    rembourse = (ge.EMAILS / "html" / "18-pre-drop-remboursement.html").read_text(encoding="utf-8")
    assert "{{ $json.montant_rembourse }}" in rembourse and "{{ $json.motif_remboursement }}" in rembourse
    assert "supplément compris" in rembourse
    # Aucune variable de prix, de quantité ni d'heure de fermeture dans les annonces.
    for ident in ("16-pre-drop-acces-prioritaire", "17-pre-drop-ouverture"):
        noms = {v[0] for v in source[ident]["variables"]}
        assert not {n for n in noms if any(m in n for m in ("prix", "quantite", "restant", "heure", "quota"))}, ident


def test_verifier_predrop_detecte_garantie_absente_et_urgence(tmp_path: Path) -> None:
    import shutil

    assert vc.verifier_predrop() == []
    racine = tmp_path / "06-contenu"
    racine.mkdir()
    plan = (vc.RACINE / vc.PLAN_DROP).read_text(encoding="utf-8")
    garantie, _ = vc.textes_garantie()
    (racine / vc.PLAN_DROP).write_text(plan.replace(garantie, "Le supplément paie le produit."), encoding="utf-8")
    assert any("phrase de garantie" in e for e in vc.verifier_predrop(racine))
    for injecte, attendu in (("> Plus que 3 réservations, dépêchez-vous !", "fausse urgence"),
                             ("> Il reste 12 unités au prix du drop.", "chiffre de stock"),
                             ("> Réservation garantie à CHF 229.90.", "prix en dur"),
                             ("> Prix fixé selon notre marge.", "terme interne")):
        (racine / vc.PLAN_DROP).write_text(plan.replace("## 4. Live", f"{injecte}\n\n## 4. Live"), encoding="utf-8")
        assert any(attendu in e for e in vc.verifier_predrop(racine)), attendu
    (racine / vc.PLAN_DROP).unlink()
    assert any("absent" in e for e in vc.verifier_predrop(racine))
    shutil.rmtree(racine)


def test_confirmation_shopify_signale_une_ligne_de_reservation_garantie() -> None:
    liquid = pytest.importorskip("liquid")
    env = liquid.Environment()
    env.filters["money"] = lambda v: f"CHF {float(v):.2f}"
    gabarit = env.from_string((ge.EMAILS / "html" / "06-confirmation-commande.html").read_text(encoding="utf-8"))
    rendu = gabarit.render(
        order_name="#1001", customer={}, subtotal_price=229.9, shipping_price=9, total_price=238.9, discounts_amount=0,
        shipping_address={"name": "L", "address1": "R", "zip": "1200", "city": "Genève"}, order_status_url="https://x.invalid",
        subtotal_line_items=[{"title": "Réservation garantie — Display (FICTIF)", "sku": "DSP-FICTIF-FR-RESA-20261020",
                              "quantity": 1, "final_price": 229.9, "final_line_price": 229.9}],
    )
    assert "RÉSERVATION GARANTIE" in rendu and "Servie en premier" in rendu and "STOCK LOCAL" not in rendu
    assert "Commande mixte" in rendu  # envoi séparé, dès réception
    texte = env.from_string((ge.EMAILS / "texte" / "06-confirmation-commande.txt").read_text(encoding="utf-8")).render(
        order_name="#1001", customer={"first_name": "Léa"}, subtotal_price=229.9, shipping_price=9, total_price=238.9,
        discounts_amount=0, shipping_address={"name": "L", "address1": "R", "zip": "1200", "city": "Genève"},
        subtotal_line_items=[{"title": "Réservation garantie — Display (FICTIF)", "sku": "DSP-FICTIF-FR-RESA-20261020",
                              "quantity": 1, "final_line_price": 229.9}],
    )
    assert "(réservation garantie : servie en premier, expédiée à part dès réception)" in texte
