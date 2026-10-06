"""Tests des livrables DA (docs/05-da) : contrastes, lettrage, SVG, HTML, synchronisation.

Lancer : cd /home/user/1 && python -m pytest docs/05-da/tests -q
"""

from __future__ import annotations

import copy
import json
import re
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import pytest

DA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DA / "tools"))

import contraste  # noqa: E402
import generer_da  # noqa: E402
import glyphes  # noqa: E402
import verifier_da  # noqa: E402

SVG_NS = "{http://www.w3.org/2000/svg}"


def _aire(d: str) -> float:
    """Aire signée d'un chemin polygonal « M x y L x y … Z »."""
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    pts = list(zip(nums[0::2], nums[1::2]))
    return glyphes._aire_signee(pts)


# ---------------------------------------------------------------------------
# Contraste WCAG
# ---------------------------------------------------------------------------
class TestContraste:
    def test_extremes(self) -> None:
        assert contraste.ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
        assert contraste.ratio("#123456", "#123456") == pytest.approx(1.0)

    def test_symetrique(self) -> None:
        assert contraste.ratio("#FF5B14", "#111111") == pytest.approx(contraste.ratio("#111111", "#FF5B14"))

    def test_valeur_reference_gris(self) -> None:
        # #777777 sur blanc : 4.478… (cas connu « juste sous AA »)
        assert contraste.ratio("#777777", "#FFFFFF") == pytest.approx(4.4781, abs=1e-3)
        assert contraste.ratio_affiche("#777777", "#FFFFFF") == "4.47"

    def test_affichage_tronque_jamais_arrondi(self) -> None:
        r = contraste.ratio("#FFFFFF", "#FF5B14")
        assert 3.10 < r < 3.11
        assert contraste.ratio_affiche("#FFFFFF", "#FF5B14") == "3.10"

    def test_hex_invalide(self) -> None:
        with pytest.raises(ValueError):
            contraste.luminance("#FFF")
        assert not contraste.est_hex("red")
        assert contraste.est_hex("#a1B2c3")

    @pytest.mark.parametrize(
        ("r", "attendu"),
        [(7.0, "AAA"), (4.5, "AA"), (3.0, "AA grand texte / UI"), (2.99, "insuffisant")],
    )
    def test_niveaux(self, r: float, attendu: str) -> None:
        assert contraste.niveau(r) == attendu


# ---------------------------------------------------------------------------
# Lettrage (glyphes)
# ---------------------------------------------------------------------------
class TestGlyphes:
    def test_num_formatage(self) -> None:
        assert glyphes.num(1.0) == "1"
        assert glyphes.num(1.234) == "1.23"
        assert glyphes.num(-0.001) == "0"

    def test_rect_et_poly_sens_horaire(self) -> None:
        p = glyphes.Pen()
        p.rect(0, 0, 10, 5)
        p.poly([(0, 0), (0, 10), (10, 10)])  # donné en sens anti-horaire
        assert all(_aire(d) > 0 for d in p.main)

    def test_bbox_anneau(self) -> None:
        p = glyphes.Pen(ox=10, oy=20, s=2)
        p.ring(50, 50, 50, 32)
        assert p.bbox == pytest.approx([10, 20, 210, 220], abs=0.01)

    def test_couronne_ouverture_invalide(self) -> None:
        with pytest.raises(ValueError):
            glyphes.Pen().band(0, 0, 10, 10, 5, 5, 0, 360)
        with pytest.raises(ValueError):
            glyphes.Pen().band(0, 0, 10, 10, 5, 5, 90, 90)

    def test_carte_inverse_balayage(self) -> None:
        p = glyphes.Pen()
        p.card(0, 0, 10, 14, 2, 0)
        p.card(0, 0, 8, 12, 1, 0, reverse=True)
        assert " 0 0 1 " in p.main[0] and " 0 0 0 " in p.main[1]

    def test_glyphe_absent(self) -> None:
        with pytest.raises(KeyError):
            glyphes.chasse("XYZ", glyphes.GLYPHES_A, glyphes.KERN_A, 10, 30)

    @pytest.mark.parametrize("texte", ["QUAI DES CARTES"])
    def test_nom_couvert_par_les_deux_lettrages(self, texte: str) -> None:
        wa = glyphes.chasse(texte, glyphes.GLYPHES_A, glyphes.KERN_A, glyphes.INTERLETTRE_A, glyphes.ESPACE_A)
        wb = glyphes.chasse(texte.lower(), glyphes.GLYPHES_B, glyphes.KERN_B, glyphes.INTERLETTRE_B, glyphes.ESPACE_B)
        assert wa > 900 and wb > 900

    def test_chasse_deterministe(self) -> None:
        args = (glyphes.GLYPHES_A, glyphes.KERN_A, glyphes.INTERLETTRE_A, glyphes.ESPACE_A)
        assert glyphes.chasse("QUAI", *args) == glyphes.chasse("QUAI", *args)

    def test_point_du_i_sur_calque_accent(self) -> None:
        p = glyphes.Pen()
        glyphes.b_i(p)
        assert len(p.accent) == 1 and len(p.main) >= 1


# ---------------------------------------------------------------------------
# Tokens et contrastes déclarés
# ---------------------------------------------------------------------------
class TestTokens:
    def test_structure(self) -> None:
        assert verifier_da.verifier_tokens(verifier_da.charger_tokens()) == []

    def test_toutes_les_paires_passent(self) -> None:
        tokens = verifier_da.charger_tokens()
        assert verifier_da.verifier_contrastes(tokens) == []
        assert len(verifier_da.lignes_contraste(tokens)) == 2 * 2 * len(tokens["contrastPairs"]) == 96

    def test_paire_insuffisante_detectee(self) -> None:
        tokens = copy.deepcopy(verifier_da.charger_tokens())
        tokens["directions"]["a"]["color"]["light"]["ink-muted"]["$value"] = "#B0B0B0"
        erreurs = verifier_da.verifier_contrastes(tokens)
        assert any("ink-muted" in e for e in erreurs)

    def test_couleur_invalide_detectee(self) -> None:
        tokens = copy.deepcopy(verifier_da.charger_tokens())
        tokens["directions"]["b"]["color"]["dark"]["bg"]["$value"] = "noir"
        assert verifier_da.verifier_tokens(tokens)

    def test_css_contient_chaque_couleur_dans_les_6_blocs(self) -> None:
        css = (DA / "tokens" / "tokens.css").read_text(encoding="utf-8")
        cles = verifier_da.charger_tokens()["directions"]["a"]["color"]["light"].keys()
        for k in cles:
            assert css.count(f"--da-color-{k}:") == 6, k

    def test_regles_de_lisibilite_documentees(self) -> None:
        a = generer_da.couleurs("a")
        b = generer_da.couleurs("b")
        assert contraste.ratio("#FFFFFF", a["accent"]) < 4.5 <= contraste.ratio(a["on-accent"], a["accent"])
        assert contraste.ratio(b["ink"], b["accent"]) < 4.5 <= contraste.ratio(b["on-accent"], b["accent"])


# ---------------------------------------------------------------------------
# Fichiers générés
# ---------------------------------------------------------------------------
LOGOS_ATTENDUS = [
    "logo/a/logo-a-principal.svg", "logo/a/logo-a-horizontal.svg", "logo/a/logo-a-monogramme.svg",
    "logo/a/logo-a-mono-noir.svg", "logo/a/logo-a-mono-blanc.svg", "logo/a/favicon.svg",
    "logo/b/logo-b-principal.svg", "logo/b/logo-b-empile.svg", "logo/b/logo-b-monogramme.svg",
    "logo/b/logo-b-mono-noir.svg", "logo/b/logo-b-mono-blanc.svg", "logo/b/favicon.svg",
]


class TestFichiers:
    def test_generation_deterministe(self) -> None:
        assert generer_da.tous_les_fichiers() == generer_da.tous_les_fichiers()

    def test_synchronises(self) -> None:
        assert verifier_da.verifier_synchro() == []

    @pytest.mark.parametrize("rel", LOGOS_ATTENDUS)
    def test_logos_presents_et_vectoriels(self, rel: str) -> None:
        racine = ET.parse(DA / rel).getroot()
        assert racine.tag == f"{SVG_NS}svg"
        assert not list(racine.iter(f"{SVG_NS}text"))
        assert list(racine.iter(f"{SVG_NS}path"))

    def test_favicons_32(self) -> None:
        for da in ("a", "b"):
            assert ET.parse(DA / f"logo/{da}/favicon.svg").getroot().get("viewBox") == "0 0 32 32"

    def test_tous_les_svg_valides(self) -> None:
        assert verifier_da.verifier_svgs() == []
        assert len(verifier_da.fichiers_svg()) >= 48

    @pytest.mark.parametrize("da", ["a", "b"])
    def test_gabarits_sociaux_complets(self, da: str) -> None:
        attendus = {
            "couverture-1x1.svg", "couverture-4x5.svg", "couverture-9x16.svg", "story-9x16-nouveau-stock.svg",
            *(f"carrousel-{f}-{n}.svg" for f in ("4x5", "1x1") for n in (1, 2, 3)),
        }
        assert attendus <= {p.name for p in (DA / "social" / da).glob("*.svg")}

    def test_prix_social_jamais_code_en_dur(self) -> None:
        for p in (DA / "social").rglob("*.svg"):
            texte = p.read_text(encoding="utf-8")
            assert not re.search(r"CHF\s*\d", texte), p.name
            if "couverture" in p.name or "story" in p.name:
                assert "{{PRIX_VALIDE}}" in texte

    @pytest.mark.parametrize("da", ["a", "b"])
    def test_packaging_mm(self, da: str) -> None:
        tailles = {
            "sticker-rond-50mm.svg": ("54mm", "54mm"),
            "carte-merci-a6-recto.svg": ("111mm", "154mm"),
            "carte-merci-a6-verso.svg": ("111mm", "154mm"),
            "repere-commande-70x37mm.svg": ("70mm", "37mm"),
        }
        for nom, (w, h) in tailles.items():
            svg = ET.parse(DA / "packaging" / da / nom).getroot()
            assert (svg.get("width"), svg.get("height")) == (w, h)

    def test_email_coherent(self) -> None:
        total = sum(Decimal(t) for *_, t in generer_da.LIGNES_EMAIL)
        assert total == Decimal(generer_da.SOUS_TOTAL_EMAIL)
        for da in ("a", "b"):
            html = (DA / f"components/email-transactionnel-{da}.html").read_text(encoding="utf-8")
            assert "FICTIF" in html and 'role="presentation"' in html
            assert "var(--" not in html and "<script" not in html and "<style" not in html
            assert f"CHF {generer_da.SOUS_TOTAL_EMAIL}" in html


# ---------------------------------------------------------------------------
# HTML, documents, termes publics
# ---------------------------------------------------------------------------
class TestPagesEtDocs:
    def test_html_ressources(self) -> None:
        assert verifier_da.verifier_html() == []

    def test_html_responsive_fr(self) -> None:
        for p in verifier_da.fichiers_html():
            texte = p.read_text(encoding="utf-8")
            assert 'lang="fr-CH"' in texte, p.name
            assert 'name="viewport"' in texte, p.name

    def test_charte_8_a_12_sections_et_tokens_relatifs(self) -> None:
        charte = (DA / "CHARTE.html").read_text(encoding="utf-8")
        assert 8 <= charte.count('class="ch-section"') <= 12
        assert 'href="tokens/tokens.css"' in charte
        assert 'src="logo/a/' in charte and 'src="logo/b/' in charte

    def test_termes_publics(self) -> None:
        assert verifier_da.verifier_termes_publics() == []

    def test_docs_validation_humaine(self) -> None:
        assert verifier_da.verifier_docs() == []

    def test_champs_declares_et_limite_par_foyer(self) -> None:
        """Revue CON-07 : aucun champ hors registre (ex. LIMITE_PAR_COMMANDE) ni limite « par commande »."""
        assert verifier_da.verifier_champs() == []
        for da in ("a", "b"):
            story = (DA / "social" / da / "story-9x16-nouveau-stock.svg").read_text(encoding="utf-8")
            assert "{{LIMITE_PAR_CLIENT}}" in story and "par commande" not in story

    def test_contrastes_publies_exacts(self) -> None:
        assert verifier_da.verifier_docs_contrastes(DA, verifier_da.charger_tokens()) == []

    def test_naming_complet(self) -> None:
        texte = (DA / "NAMING.md").read_text(encoding="utf-8")
        assert len(re.findall(r"^### Piste \d", texte, re.MULTILINE)) == 3
        section = texte.split("## 3. Cinq alternatives")[1].split("## 4.")[0]
        assert len(re.findall(r"^\| \*\*", section, re.MULTILINE)) == 5
        for registre in ("Swissreg", "EUIPO", "Zefix", "Domaine .ch"):
            assert registre in texte


# ---------------------------------------------------------------------------
# Le vérificateur détecte bien les fautes (tests négatifs sur un dossier temporaire)
# ---------------------------------------------------------------------------
class TestVerificateurNegatif:
    def test_svg_mal_forme_et_logo_avec_texte(self, tmp_path: Path) -> None:
        (tmp_path / "logo").mkdir()
        (tmp_path / "logo" / "casse.svg").write_text("<svg><path></svg>", encoding="utf-8")
        (tmp_path / "logo" / "texte.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" width="10" height="10">'
            '<title>t</title><text>Poké</text><path d="M0 0H1V1Z"/></svg>',
            encoding="utf-8",
        )
        erreurs = verifier_da.verifier_svgs(tmp_path)
        assert any("mal formé" in e for e in erreurs)
        assert any("<text>" in e for e in erreurs)
        assert any("Poké" in e for e in erreurs)

    def test_terme_interne_detecte(self, tmp_path: Path) -> None:
        (tmp_path / "components").mkdir()
        (tmp_path / "components" / "x.html").write_text(
            '<p style="margin:0">Marge : 30 %, prix CHF 10</p>', encoding="utf-8"
        )
        erreurs = verifier_da.verifier_termes_publics(tmp_path)
        assert any("Marge" in e for e in erreurs)
        assert any("FICTIF" in e for e in erreurs)

    def test_css_margin_non_signale(self, tmp_path: Path) -> None:
        (tmp_path / "components").mkdir()
        (tmp_path / "components" / "x.html").write_text('<p style="margin:0;margin-top:4px">ok</p>', encoding="utf-8")
        assert verifier_da.verifier_termes_publics(tmp_path) == []

    def test_ressource_externe_refusee(self, tmp_path: Path) -> None:
        (tmp_path / "p.html").write_text(
            '<link rel="stylesheet" href="https://cdn.example.com/x.css"><img src="absent.svg">',
            encoding="utf-8",
        )
        erreurs = verifier_da.verifier_html(tmp_path)
        assert any("non autorisée" in e for e in erreurs)
        assert any("introuvable" in e for e in erreurs)

    def test_champ_hors_registre_et_limite_par_commande_detectes(self, tmp_path: Path) -> None:
        (tmp_path / "social" / "a").mkdir(parents=True)
        (tmp_path / "social" / "a" / "x.svg").write_text(
            "<svg><text>Limite : {{LIMITE_PAR_COMMANDE}} par commande · {{MENTION_TVA}} · {{EXTENSION}}</text></svg>",
            encoding="utf-8",
        )
        erreurs = verifier_da.verifier_champs(tmp_path)
        assert any("{{LIMITE_PAR_COMMANDE}}" in e for e in erreurs)
        assert any("par commande" in e and "foyer" in e for e in erreurs)
        assert not any("MENTION_TVA" in e or "EXTENSION" in e for e in erreurs)

    def test_doc_sans_validation(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text("# Titre\n\n## Validation humaine requise\n\n## Annexe\n", encoding="utf-8")
        assert verifier_da.verifier_docs(tmp_path)

    def test_citation_fausse_detectee(self, tmp_path: Path) -> None:
        (tmp_path / "x.md").write_text("Contraste 9.99:1 entre `#FFFFFF` et `#FF5B14`.\n", encoding="utf-8")
        assert verifier_da.verifier_citations(tmp_path)

    def test_tokens_json_valide(self) -> None:
        json.loads((DA / "tokens" / "tokens.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Ambiance « Nuit sur le Léman » (bâtie sur B, toujours sombre)
# ---------------------------------------------------------------------------
class TestAmbianceNuit:
    def test_structure_et_contrastes(self) -> None:
        tokens = verifier_da.charger_tokens()
        assert verifier_da.verifier_ambiances(tokens) == []
        lignes = verifier_da.lignes_contraste_ambiances(tokens)
        assert len(lignes) == len(tokens["contrastPairs"]) + len(tokens["ambianceContrastPairs"])
        assert all(lc["ratio"] >= lc["min"] for lc in lignes)

    def test_couleur_insuffisante_detectee(self) -> None:
        tokens = copy.deepcopy(verifier_da.charger_tokens())
        tokens["ambiances"]["nuit"]["color"]["dark"]["or"]["$value"] = "#5A4A20"
        assert any(e.startswith("nuit/dark or sur") for e in verifier_da.verifier_contrastes(tokens))

    def test_ambiance_jamais_claire_et_complete(self) -> None:
        tokens = copy.deepcopy(verifier_da.charger_tokens())
        amb = tokens["ambiances"]["nuit"]
        amb["color"]["light"] = amb["color"]["dark"]
        assert any("toujours sombre" in e for e in verifier_da.verifier_ambiances(tokens))
        tokens = copy.deepcopy(verifier_da.charger_tokens())
        del tokens["ambiances"]["nuit"]["color"]["dark"]["focus"]
        assert any("focus" in e for e in verifier_da.verifier_ambiances(tokens))
        tokens = copy.deepcopy(verifier_da.charger_tokens())
        tokens["ambiances"]["nuit"]["googleFonts"] = tokens["directions"]["b"]["googleFonts"]
        assert any("Fraunces" in e for e in verifier_da.verifier_ambiances(tokens))

    def test_regle_texte_fonce_sur_rose(self) -> None:
        n = generer_da.couleurs_ambiance("nuit")
        assert contraste.ratio(n["ink"], n["accent"]) < 4.5 <= contraste.ratio(n["on-accent"], n["accent"])

    def test_css_ambiance_genere_et_prioritaire(self) -> None:
        css = (DA / "tokens" / "tokens-nuit.css").read_text(encoding="utf-8")
        assert css == generer_da.generer_css_ambiance("nuit")
        assert ':root[data-ambiance="nuit"][data-da] {' in css and "color-scheme: dark;" in css
        for k in generer_da.couleurs_ambiance("nuit"):
            assert css.count(f"--da-color-{k}:") == 1, k
        assert "--da-font-accent:" in css

    def test_logo_nuit_et_tableau_publie(self) -> None:
        logo = (DA / "logo" / "b" / "logo-b-nuit.svg").read_text(encoding="utf-8")
        n = generer_da.couleurs_ambiance("nuit")
        assert n["ink"] in logo and n["accent-text"] in logo and "<text" not in logo
        doc = (DA / "DIRECTION_NUIT.md").read_text(encoding="utf-8")
        assert generer_da.tableau_contrastes_ambiance_md("nuit") in doc
        assert "Lumi (nom provisoire)" in doc and "Validation humaine requise" in doc
