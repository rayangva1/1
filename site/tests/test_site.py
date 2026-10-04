"""Tests du périmètre site/ : landing, outils de publication, contrôles, snippets Liquid (statique)."""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import da_sync
import markdown_mini
import publication
import registre_champs as rc
import verifier_site as vs
from typo import NBSP, NNBSP, fautes, typographier

REPO = Path(__file__).resolve().parents[2]
LANDING = REPO / "site" / "landing"
WEBHOOK_FICTIF = "https://n8n.exemple.invalid/webhook/alertes-inscription"
URL_FICTIVE = "https://landing.exemple.invalid/"


# ----------------------------------------------------------------------------- dépôt
def test_tous_les_controles_du_depot_passent() -> None:
    resultats = vs.tout_verifier()
    assert resultats == {k: [] for k in resultats}, resultats


def test_landing_sans_prix_ni_stock_ni_precommande() -> None:
    texte = vs._texte_visible((LANDING / "index.html").read_text(encoding="utf-8"))
    assert not vs.PRIX_RE.search(texte)
    assert "en stock" not in texte.replace("« en stock »", "")
    analyse = vs.analyser((LANDING / "index.html").read_text(encoding="utf-8"))
    assert not [lib for _, lib in analyse.actions if vs.ACHAT_RE.search(lib)]


def test_mention_independance_reprend_le_texte_legal() -> None:
    reference = vs.mention_reference()
    assert "The Pokémon Company" in reference and reference.endswith("revendons.")
    for page in LANDING.glob("*.html"):
        assert reference in vs._normaliser(page.read_text(encoding="utf-8")), page.name


def test_formulaire_conforme_au_schema() -> None:
    a = vs.analyser((LANDING / "index.html").read_text(encoding="utf-8"))
    schema = json.loads(vs.SCHEMA.read_text(encoding="utf-8"))
    noms = {c["name"] for c in a.champs if c.get("name")}
    assert set(schema["required"]) <= noms <= set(schema["properties"])
    consentement = next(c for c in a.champs if c.get("name") == "consentement")
    assert "checked" not in consentement and "required" in consentement


# ----------------------------------------------------------------------------- contrôles sur pages défectueuses
def _page(tmp_path: Path, html: str) -> list[str]:
    dossier = tmp_path / "lp"
    shutil.copytree(LANDING, dossier)
    (dossier / "index.html").write_text(html, encoding="utf-8")
    return vs.verifier_page(dossier / "index.html", dossier)


def _source() -> str:
    return (LANDING / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("modification", "attendu"),
    [
        (lambda t: t.replace("Aucun prix n'est encore fixé.", "Display dès CHF 189.90."), "prix"),
        (lambda t: t.replace("Aucun prix n'est encore fixé.", "Prix d'achat négocié."), "terme interne"),
        (lambda t: t.replace("Aucun prix n'est encore fixé.", "Notre fournisseur livre vite."), "terme interne"),
        (lambda t: t.replace("Aucun prix n'est encore fixé.", "Plus que 3 boîtes !"), "fausse urgence"),
        (lambda t: t.replace("Aucun prix n'est encore fixé.", "Un excellent investissement."), "promesse interdite"),
        (lambda t: t.replace("Aucun prix n'est encore fixé.", "EAN 4006381333931."), "13 chiffres"),
        (lambda t: t.replace('<input id="lp-consentement" name="consentement" type="checkbox"', '<input id="lp-consentement" name="consentement" type="checkbox" checked'), "pré-cochée"),
        (lambda t: t.replace('value="oui" required aria-describedby', 'value="oui" aria-describedby'), "non obligatoire"),
        (lambda t: t.replace('<label for="lp-prenom">', '<label for="autre">'), "sans libellé"),
        (lambda t: t.replace('href="confidentialite.html">déclaration', 'href="confidentialite-absente.html">déclaration'), "lien relatif cassé"),
        (lambda t: t.replace('href="#alertes"', 'href="#inexistant"'), "ancre introuvable"),
        (lambda t: t.replace('<script src="js/theme.js"></script>', '<script src="https://cdn.exemple.invalid/x.js"></script>'), "ressource externe"),
        (lambda t: t.replace("ni sponsorisée, ", ""), "mention d'indépendance"),
        (lambda t: t.replace("Pour qui achetez-vous ?", "Pour qui achetez-vous ?"), "espace insécable"),
        (lambda t: t.replace('<p class="lp-surtitre">', '<p class="lp-surtitre"><span>'), "balises"),
        (lambda t: t.replace('<meta property="og:image"', '<meta property="og:imagex"'), "og:image"),
        (lambda t: t.replace("Recevoir l'alerte d'ouverture</a>", "Précommander</a>"), "action d'achat"),
        (lambda t: t.replace('id="titre-promesse"', 'id="titre-principal"'), "identifiant en double"),
        (lambda t: t.replace('name="prenom"', 'name="telephone"'), "inscription.schema.json"),
        (lambda t: t.replace('<div class="lp-piege" aria-hidden="true">', '<div aria-hidden="true">'), "champ piège"),
    ],
)
def test_controles_detectent_les_defauts(tmp_path: Path, modification, attendu: str) -> None:  # type: ignore[no-untyped-def]
    erreurs = _page(tmp_path, modification(_source()))
    assert any(attendu in e for e in erreurs), erreurs


def test_negations_de_lencadre_ne_sont_pas_de_la_fausse_urgence(tmp_path: Path) -> None:
    assert "dernières pièces" in _source()
    assert not [e for e in _page(tmp_path, _source()) if "urgence" in e]


def test_bouton_actif_dans_la_source_refuse() -> None:
    t = _source().replace('id="lp-envoyer" disabled>', 'id="lp-envoyer">')
    assert vs.verifier_bouton_source(t)
    assert vs.verifier_bouton_source(_source()) == []


def test_css_couleur_en_dur_et_js_url_detectees(tmp_path: Path) -> None:
    dossier = tmp_path / "lp"
    shutil.copytree(LANDING, dossier)
    css = dossier / "css" / "landing.css"
    css.write_text(css.read_text(encoding="utf-8") + "\n.x { color: #ff0000; }\n", encoding="utf-8")
    js = dossier / "js" / "landing.js"
    js.write_text(js.read_text(encoding="utf-8") + '\nfetch("https://pixel.exemple.invalid");\n', encoding="utf-8")
    cfg = dossier / "js" / "config.js"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace('webhookUrl: ""', f'webhookUrl: "{WEBHOOK_FICTIF}"'), encoding="utf-8")
    erreurs = vs.verifier_css_js(dossier)
    assert any("couleur en dur" in e for e in erreurs)
    assert any("URL en dur" in e for e in erreurs)
    assert any("ne doit pas contenir d'URL de webhook" in e for e in erreurs)


def test_page_de_service_sans_noindex(tmp_path: Path) -> None:
    dossier = tmp_path / "lp"
    shutil.copytree(LANDING, dossier)
    merci = dossier / "merci.html"
    merci.write_text(merci.read_text(encoding="utf-8").replace('<meta name="robots" content="noindex, nofollow">', ""), encoding="utf-8")
    assert any("noindex" in e for e in vs.verifier_page(merci, dossier))


# ----------------------------------------------------------------------------- typographie et Markdown
def test_typographie_espaces_insecables_et_idempotence() -> None:
    html = '<p>Quoi ? Oui ! a ; b : « c » &amp; d; https://x.ch/?q=1</p><script>a ? b : c;</script>'
    sortie = typographier(html)
    assert f"Quoi{NNBSP}?" in sortie and f"Oui{NNBSP}!" in sortie and f"b{NBSP}:" in sortie
    assert f"«{NBSP}c{NBSP}»" in sortie and "&amp; d" in sortie and "https://x.ch/?q=1" in sortie
    assert "<script>a ? b : c;</script>" in sortie
    assert typographier(sortie) == sortie
    assert fautes(html) and not fautes(sortie)


def test_markdown_tableaux_listes_et_echappement() -> None:
    md = (
        "## Titre\n\nTexte **gras** et *italique* <script>x</script>.\n\n- un\n- deux\n\n1. a\n2. b\n\n"
        "| A | B |\n|---|---|\n| 1 | [lien](https://ex.ch) |\n\n[mal](javascript:alert(1)) ⟦À REMPLIR : X⟧"
    )
    html = markdown_mini.convertir(md, decalage_titres=1)
    assert "<h1>Titre</h1>" in html
    assert "<strong>gras</strong>" in html and "<em>italique</em>" in html
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert "<ul><li>un</li><li>deux</li></ul>" in html and "<ol><li>a</li><li>b</li></ol>" in html
    assert '<th scope="col">A</th>' in html and '<a href="https://ex.ch">lien</a>' in html
    assert 'href="javascript' not in html
    assert '<mark class="lp-a-remplir">' in html


# ----------------------------------------------------------------------------- copies DA
def test_copies_da_synchronisees_et_falsification_detectee(tmp_path: Path) -> None:
    assert da_sync.verifier() == []
    cible = tmp_path / "da"
    shutil.copytree(LANDING / "assets" / "da", cible)
    (cible / "tokens.css").write_text("/* modifié */", encoding="utf-8")
    erreurs = da_sync.verifier(cible=cible)
    assert any("tokens.css" in e for e in erreurs)


def test_plan_de_copie_direction_b_et_direction_inconnue() -> None:
    plan = da_sync.plan_copie("b")
    assert plan["logo-horizontal.svg"].name == "logo-b-principal.svg"
    assert all(p.exists() for p in plan.values())
    with pytest.raises(ValueError):
        da_sync.plan_copie("c")


# ----------------------------------------------------------------------------- publication
def _champs_fictifs(nom: str = publication.NOM_DE_TRAVAIL) -> dict[str, rc.Field]:
    """Tous les champs validés avec des valeurs FICTIVES (jamais publiées)."""
    champs = publication.charger_champs()
    valeurs = {
        "NOM_BOUTIQUE": nom,
        "WEBHOOK_INSCRIPTION": WEBHOOK_FICTIF,
        "URL_LANDING": URL_FICTIVE,
        "EMAIL_SUPPORT": "contact@exemple.invalid",
        "EMAIL_DONNEES": "donnees@exemple.invalid",
        "MOIS_OUVERTURE": "novembre 2026",
        "URL_COOKIES": URL_FICTIVE + "cookies",
    }
    sortie = {}
    for cle, f in champs.items():
        if f.alias_of:
            sortie[cle] = f
            continue
        sortie[cle] = dataclasses.replace(f, status=rc.Status.VALIDE, value=valeurs.get(cle, f"FICTIF {cle.lower()}"), validated_by="test")
    return sortie


def test_webhook_valide() -> None:
    assert publication.webhook_valide(WEBHOOK_FICTIF)
    for mauvais in ("", None, "http://n8n.ex.ch/webhook/x", "https://n8n.ex.ch", "https://{{X}}/w", "https://a b.ch/w", "javascript:alert(1)"):
        assert not publication.webhook_valide(mauvais), mauvais


def test_publication_refusee_tant_que_rien_nest_valide(tmp_path: Path) -> None:
    with pytest.raises(publication.PublicationError) as exc:
        publication.construire("publication", tmp_path / "pub")
    erreurs = " ".join(exc.value.erreurs)
    assert "NOM_BOUTIQUE non validé" in erreurs and "WEBHOOK_INSCRIPTION" in erreurs and "URL_LANDING" in erreurs
    assert not (tmp_path / "pub").exists()


def test_apercu_construit_et_garde_bandeau(tmp_path: Path) -> None:
    rapport = publication.construire("apercu", tmp_path / "ap")
    index = (tmp_path / "ap" / "index.html").read_text(encoding="utf-8")
    assert "APERCU:DEBUT" in index and "noindex" in index and "⟦À REMPLIR" in index
    assert 'webhookUrl: ""' in (tmp_path / "ap" / "js" / "config.js").read_text(encoding="utf-8")
    assert "README.md" not in rapport.fichiers and "inscription.schema.json" not in rapport.fichiers
    assert vs.verifier_landing(tmp_path / "ap") == []


def test_publication_complete_avec_champs_fictifs(tmp_path: Path) -> None:
    sortie = tmp_path / "pub"
    rapport = publication.construire("publication", sortie, champs=_champs_fictifs())
    assert {"_headers", "robots.txt", "sitemap.xml", "index.html", "confidentialite.html"} <= set(rapport.fichiers)
    index = (sortie / "index.html").read_text(encoding="utf-8")
    assert "{{" not in index and "⟦" not in index and "APERCU" not in index and "noindex" not in index
    assert f'action="{WEBHOOK_FICTIF}"' in index
    assert 'id="lp-envoyer">' in index
    assert f'<link rel="canonical" href="{URL_FICTIVE}">' in index
    config = (sortie / "js" / "config.js").read_text(encoding="utf-8")
    assert f'webhookUrl: "{WEBHOOK_FICTIF}"' in config and 'mode: "publication"' in config
    entetes = (sortie / "_headers").read_text(encoding="utf-8")
    assert "connect-src https://n8n.exemple.invalid;" in entetes and "fonts.googleapis.com" in entetes
    assert (sortie / "merci.html").read_text(encoding="utf-8").count("noindex") == 1
    assert vs.verifier_landing(sortie, publication_mode=True) == []


def test_publication_sans_google_fonts(tmp_path: Path) -> None:
    sortie = tmp_path / "pub"
    publication.construire("publication", sortie, champs=_champs_fictifs(), sans_google_fonts=True)
    for page in sortie.glob("*.html"):
        assert "fonts.googleapis.com" not in page.read_text(encoding="utf-8")
    assert "fonts.g" not in (sortie / "_headers").read_text(encoding="utf-8")


def test_publication_refuse_un_nom_valide_sans_nouveau_logo(tmp_path: Path) -> None:
    with pytest.raises(publication.PublicationError) as exc:
        publication.construire("publication", tmp_path / "pub", champs=_champs_fictifs(nom="Franc Jeu"))
    assert any("logo" in e for e in exc.value.erreurs)


def test_publication_refuse_un_champ_a_valider(tmp_path: Path) -> None:
    champs = _champs_fictifs()
    champs["MOIS_OUVERTURE"] = dataclasses.replace(champs["MOIS_OUVERTURE"], status=rc.Status.A_VALIDER)
    with pytest.raises(publication.PublicationError) as exc:
        publication.construire("publication", tmp_path / "pub", champs=champs)
    assert any("MOIS_OUVERTURE" in e for e in exc.value.erreurs)


def test_pages_secondaires_reprennent_le_texte_legal() -> None:
    pages = publication.pages_secondaires()
    assert set(pages) == {"merci.html", "inscription-confirmee.html", "desinscription.html", "confidentialite.html"}
    conf = pages["confidentialite.html"]
    assert "Déclaration de confidentialité</h1>" in conf and "<table>" in conf and "Partie interne" not in conf
    assert "Notes pour le juriste" not in conf


def test_champ_defini_deux_fois_refuse(tmp_path: Path) -> None:
    doublon = tmp_path / "site.yaml"
    doublon.write_text(
        "champs:\n  EMAIL_SUPPORT:\n    description: x\n    statut: a_remplir\n    decideur: x\n    source: x\n",
        encoding="utf-8",
    )
    with pytest.raises(publication.PublicationError):
        publication.charger_champs(chemin_site=doublon)


def test_etat_liste_les_champs_requis() -> None:
    lignes = dict((n, s) for n, s, _ in publication.etat())
    assert {"NOM_BOUTIQUE", "WEBHOOK_INSCRIPTION", "URL_LANDING", "RAISON_SOCIALE", "MOIS_OUVERTURE"} <= set(lignes)
    assert "INCONNU" not in lignes.values()


# ----------------------------------------------------------------------------- Liquid (statique)
def test_snippets_liquid_controles_statiques() -> None:
    assert vs.verifier_liquid() == []


def test_controle_liquid_detecte_les_defauts(tmp_path: Path) -> None:
    dossier = tmp_path / "snippets"
    shutil.copytree(vs.SNIPPETS, dossier)
    p = dossier / "da-badges.liquid"
    p.write_text(p.read_text(encoding="utf-8").replace("{%- endcase -%}", "", 1) + "\n<p>Coût : CHF 12.00</p>{% render 'absent' %}", encoding="utf-8")
    s = dossier / "da-statut-stock.liquid"
    s.write_text(s.read_text(encoding="utf-8").replace("Rupture – alerte", "Épuisé"), encoding="utf-8")
    erreurs = " ".join(vs.verifier_liquid(dossier))
    for attendu in ("blocs non fermés", "terme interne", "prix en dur", "snippet absent", "libellé « Rupture – alerte »"):
        assert attendu in erreurs, attendu


# ----------------------------------------------------------------------------- JavaScript (Node, si disponible)
def _node(script: str) -> dict:  # type: ignore[type-arg]
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js absent : tests JavaScript ignorés")
    code = f"require({json.dumps(str(LANDING / 'js' / 'landing.js'))});\nconst C = globalThis.LandingCore;\n{script}"
    sortie = subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(sortie.stdout)


def test_js_validation_webhook_et_utm() -> None:
    r = _node(
        "console.log(JSON.stringify({"
        f"ok: C.webhookValide({json.dumps(WEBHOOK_FICTIF)}), vide: C.webhookValide(''), http: C.webhookValide('http://a.ch/x'),"
        "champ: C.webhookValide('https://{{WEBHOOK}}/x'), sansChemin: C.webhookValide('https://a.ch'),"
        "utm: C.lireUtm('?utm_source=Instagram&utm_medium=bio%20x&utm_campaign=lancement-1'),"
        "email: [C.emailValide('a@b.ch'), C.emailValide('a@b'), C.emailValide(' '), C.emailValide('a b@c.ch')]}));"
    )
    assert r["ok"] is True and not any((r["vide"], r["http"], r["champ"], r["sansChemin"]))
    assert r["utm"] == {"utm_source": "instagram", "utm_medium": "", "utm_campaign": "lancement-1"}
    assert r["email"] == [True, False, False, False]


def test_js_construction_du_payload() -> None:
    r = _node(
        "const d = new Date('2026-10-14T08:00:00Z');"
        "const ok = C.construirePayload({email: ' lea@exemple.ch ', prenom: ' Léa<b> ', formats: ['etb','x','etb','displays'],"
        " budget: '30-60', pour_qui: 'pirate', canton: 'GE', consentement: true, consentement_texte: ' J\\'accepte   tout ',"
        " utm: {utm_source: 'reseau'}}, d, {consentVersion: 'alertes-v1-2026-10-04', page: 'https://x.ch/'});"
        "const ko = C.construirePayload({email: 'pas-un-email', consentement: false}, d, {});"
        "const vide = C.construirePayload({email: '', consentement: 'oui'}, d, {});"
        "console.log(JSON.stringify({ok, ko, vide}));"
    )
    champs = r["ok"]["champs"]
    assert r["ok"]["ok"] is True
    assert champs["email"] == "lea@exemple.ch" and champs["prenom"] == "Léab"
    assert champs["formats"] == "etb,displays" and champs["budget"] == "30-60" and champs["pour_qui"] == ""
    assert champs["consentement"] == "oui" and champs["consentement_texte"] == "J'accepte tout"
    assert champs["horodatage_client"] == "2026-10-14T08:00:00.000Z" and champs["utm_source"] == "reseau"
    schema = json.loads(vs.SCHEMA.read_text(encoding="utf-8"))
    assert set(champs) <= set(schema["properties"])
    assert re.match(schema["properties"]["formats"]["pattern"], champs["formats"])
    assert r["ko"]["ok"] is False and set(r["ko"]["erreurs"]) == {"email", "consentement"} and r["ko"]["champs"] is None
    assert set(r["vide"]["erreurs"]) == {"email", "consentement"}


# ----------------------------------------------------------------------------- documents
def test_documents_finissent_par_validation_humaine() -> None:
    assert vs.verifier_docs() == []
