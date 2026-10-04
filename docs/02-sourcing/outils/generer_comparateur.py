"""Génère ``docs/02-sourcing/COMPARATEUR_OFFRES.xlsx`` (comparateur d'offres fournisseurs).

Le classeur calcule, par formules vivantes, le coût rendu CHF par unité (BP §4) de chaque offre,
le prix plancher (formule BP §4), l'écart à la référence marché (règle BP §5 : +10 %) et le
classement des fournisseurs par référence. Les formules reproduisent ``pokeshop.pricing``
(``landed_unit_cost``, ``floor_price_exact``) ; ``test_comparateur_offres.py`` le vérifie après un
recalcul LibreOffice.

Aucun prix réel : seules deux lignes d'exemple **FICTIF** sont remplies. Les paramètres r, b, L,
R, A, m, t viennent de ``config/pricing_rules.v1.yaml`` (source unique).

Usage ::

    python docs/02-sourcing/outils/generer_comparateur.py              # génère + recalcule + contrôle
    python docs/02-sourcing/outils/generer_comparateur.py --sans-recalcul
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "engine"))

from pokeshop.models import VatMode  # noqa: E402
from pokeshop.rules import load_all_profiles  # noqa: E402

OUTPUT = REPO / "docs" / "02-sourcing" / "COMPARATEUR_OFFRES.xlsx"
PANIER = REPO / "docs" / "02-sourcing" / "PANIER_PILOTE.csv"
RULES = REPO / "config" / "pricing_rules.v1.yaml"

PARAM_SHEET = "Paramètres"
SUP_SHEET = "Fournisseurs"
OFF_SHEET = "Offres"
RANK_SHEET = "Classement"
SYN_SHEET = "Synthèse fournisseurs"
HELP_SHEET = "Mode d'emploi"

SUP_FIRST, SUP_LAST = 5, 24  # lignes fournisseurs
OFF_FIRST, OFF_LAST = 6, 205  # lignes offres
ERROR_TOKENS = ("#VALUE!", "#DIV/0!", "#NAME?", "#REF!", "#N/A", "#NUM!", "#NULL!", "Err:")

BP_SUPPLIERS = (
    "Asmodee France",
    "Matoo et Miao",
    "TCG Distribution",
    "OtakuWorld",
    "CardCosmos",
    "Carletto AG (hors BP)",
)
PRIORITY_FR = BP_SUPPLIERS[:3]
FICTIF_REF = "FICTIF_R00"

# ---------------------------------------------------------------- styles
YELLOW = PatternFill("solid", fgColor="FFF2CC")
GREY = PatternFill("solid", fgColor="F2F2F2")
ORANGE = PatternFill("solid", fgColor="FCE4D6")
HEAD = PatternFill("solid", fgColor="1F2937")
INPUT_FONT = Font(color="1F4E79")
HEAD_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(bold=True, size=14)
BOLD = Font(bold=True)
ITALIC = Font(italic=True, color="7F7F7F")
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CHF = "#,##0.00"
CHF4 = "#,##0.0000"
PCT = "0.0%"
FX = "0.0000"
WRAP = Alignment(wrap_text=True, vertical="top")


@dataclass(frozen=True)
class Params:
    """Valeurs de la feuille Paramètres (issues du fichier de règles)."""

    vat_mode: str
    vat_rate_ch: Decimal
    payment_pct: Decimal
    payment_fixed: Decimal
    logistics: Decimal
    after_sales: Decimal
    acquisition: Decimal
    target_margin: Decimal
    market_threshold: Decimal
    floor_pct: Decimal
    floor_chf: Decimal
    rules_version: str


def load_params(vat_mode: str = "EFFECTIVE") -> Params:
    """Lit ``config/pricing_rules.v1.yaml`` ; le taux CH vient du profil EFFECTIVE."""
    if vat_mode not in ("EFFECTIVE", "NOT_REGISTERED"):
        raise ValueError(f"mode TVA inconnu : {vat_mode}")
    profiles = load_all_profiles(RULES)
    eff = profiles[VatMode.EFFECTIVE]
    p = eff.pricing
    return Params(
        vat_mode=vat_mode,
        vat_rate_ch=p.vat_rate_sales,
        payment_pct=p.payment_pct,
        payment_fixed=p.payment_fixed,
        logistics=p.logistics_cost,
        after_sales=p.after_sales_provision,
        acquisition=p.acquisition_cost,
        target_margin=p.target_margin,
        market_threshold=p.market_review_threshold,
        floor_pct=p.hard_floor_margin,
        floor_chf=p.hard_floor_chf_per_order,
        rules_version=eff.rules_version,
    )


def gtin13(body12: str) -> str:
    """GTIN-13 avec chiffre de contrôle GS1 (pour les codes de test FICTIFS en 200…)."""
    if len(body12) != 12 or not body12.isdigit():
        raise ValueError("12 chiffres attendus")
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - total % 10) % 10)


# Cellules de la feuille Paramètres (colonne B)
P_CELLS = {
    "mode": 4,
    "t": 5,
    "r": 6,
    "b": 7,
    "L": 8,
    "R": 9,
    "A": 10,
    "m": 11,
    "seuil": 12,
    "tva_ch": 13,
    "tva_import": 14,
    "floor_pct": 15,
    "floor_chf": 16,
    "version": 17,
}


def pref(key: str) -> str:
    """Référence absolue vers un paramètre."""
    return f"'{PARAM_SHEET}'!$B${P_CELLS[key]}"


def _header(ws: Worksheet, row: int, labels: list[str], widths: list[int]) -> None:
    for col, (label, width) in enumerate(zip(labels, widths, strict=True), start=1):
        c = ws.cell(row=row, column=col, value=label)
        c.fill, c.font, c.alignment, c.border = HEAD, HEAD_FONT, WRAP, BORDER
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[row].height = 48


# ---------------------------------------------------------------- feuilles
def build_help(ws: Worksheet, params: Params) -> None:
    ws.title = HELP_SHEET
    ws.column_dimensions["A"].width = 120
    lines = [
        ("Comparateur d'offres fournisseurs — {{NOM_BOUTIQUE}}", TITLE_FONT),
        (
            "AUCUN PRIX RÉEL. Seules les lignes marquées FICTIF (fournisseurs FICTIF_FOURNISSEUR_A et _B, "
            "référence FICTIF_R00) sont remplies, pour montrer le calcul. Les supprimer avant usage réel.",
            BOLD,
        ),
        (
            "Source : BP du 4.10.2026, §1 (devis sur les mêmes références), §2 (demande commerciale), "
            "§4 (coût rendu et prix plancher), §5 (règles), §13 (même panier aux 3 fournisseurs FR).",
            None,
        ),
        (
            f"Paramètres de prix : config/pricing_rules.v1.yaml, version {params.rules_version} "
            "(hypothèses BP §4-5, à confirmer par devis).",
            None,
        ),
        ("", None),
        ("MODE D'EMPLOI", BOLD),
        (
            "1. Paramètres : choisir le mode TVA de l'entité (B4) selon la décision de la fiduciaire (B10). "
            "Les autres valeurs viennent du fichier de règles : ne les modifier qu'en créant une nouvelle version.",
            None,
        ),
        (
            "2. Fournisseurs : une ligne par fournisseur. Saisir pays d'expédition, devise, taux de change vers CHF "
            "(source + date), TVA facturée par le fournisseur (0 si facture d'export HT) et son pays, port amont et "
            "frais fixes de la commande (en devise), frais de dédouanement (CHF). "
            "Une case vide = fournisseur INCOMPLET.",
            None,
        ),
        (
            "3. Offres : une ligne par couple (référence, fournisseur), à partir du devis écrit. Saisir unités par "
            "conditionnement, prix du conditionnement, HT ou TTC, remise du palier atteint pour la quantité commandée, "
            "quantité commandée (en conditionnements), MOQ, disponibilité, allocation ferme, et la référence marché "
            "(médiane du prix total livré, docs/01-marche/GRILLE_CONCURRENCE.csv).",
            None,
        ),
        (
            "4. Les colonnes grises se calculent seules : coût rendu C par unité (CHF), prix plancher, "
            "écart au marché, "
            "contribution au prix marché, statut, rang.",
            None,
        ),
        (
            "5. Classement : meilleur et 2e fournisseur par référence. Synthèse fournisseurs : couverture du panier, "
            "valeur de la commande, minimum de commande atteint.",
            None,
        ),
        ("", None),
        ("RÈGLES DE CALCUL (identiques au moteur pokeshop.pricing)", BOLD),
        (
            "C = achat HT unitaire en CHF + TVA fournisseur non récupérable + port et frais ventilés + dédouanement "
            "ventilé + TVA import (seulement si NOT_REGISTERED). La TVA fournisseur n'est récupérable que si elle est "
            "suisse ET l'entité assujettie (EFFECTIVE). Port, frais et dédouanement sont ventilés au prorata de la "
            "valeur HT des lignes du même fournisseur. "
            "Droits de douane = 0 (produits industriels, depuis le 1.1.2024).",
            None,
        ),
        ("TVA import = (achat HT + port + dédouanement) × taux : ESTIMATION à remplacer par le décompte OFDF.", None),
        ("Prix plancher P = (C + b + L + R + A) / ((1 − m)/(1 + t) − r)  (BP §4).", None),
        (
            "Statut : OK si P ≤ marché × (1 + seuil) ; À REVOIR si au prix marché la contribution reste ≥ plancher dur "
            "(12 % et 8 CHF) ; NON RENTABLE sinon ; INCOMPLET si un champ manque (= brouillon, BP §5).",
            None,
        ),
        ("", None),
        ("CODES COULEUR", BOLD),
        ("Jaune, texte bleu : saisie. Gris : formule (ne pas modifier). Orange : ligne FICTIF.", None),
        (
            "Généré par docs/02-sourcing/outils/generer_comparateur.py ; recalculé par LibreOffice ; "
            "contrôlé par test_comparateur_offres.py.",
            ITALIC,
        ),
        ("", None),
        ("VALIDATION HUMAINE REQUISE", BOLD),
        ("- Confirmer le mode TVA (B4) avec la fiduciaire avant toute décision d'achat.", None),
        ("- Vérifier chaque devis saisi (prix, HT/TTC, devise, conditionnement) avant le gate G3.", None),
        ("- Valider le fournisseur retenu par référence (C08) ; le classement est une aide, pas une décision.", None),
    ]
    for i, (text, font) in enumerate(lines, start=1):
        c = ws.cell(row=i, column=1, value=text)
        c.alignment = WRAP
        if font is not None:
            c.font = font


def build_params(ws: Worksheet, params: Params) -> None:
    ws["A1"] = "Paramètres de calcul"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Source : config/pricing_rules.v1.yaml ({params.rules_version}) — hypothèses BP §4-5, à confirmer."
    ws["A2"].font = ITALIC
    _header(ws, 3, ["Paramètre", "Valeur", "Note"], [46, 18, 90])
    rows = [
        (
            "mode",
            "Mode TVA de l'entité (EFFECTIVE / NOT_REGISTERED)",
            params.vat_mode,
            "Décision de la fiduciaire (B10). EFFECTIVE = hypothèse du BP §10.",
            None,
            True,
        ),
        (
            "t",
            "t — TVA sur ventes",
            f'=IF({pref("mode")}="EFFECTIVE",{pref("tva_ch")},0)',
            "0 si non assujetti (BP §4).",
            PCT,
            False,
        ),
        (
            "r",
            "r — frais de paiement proportionnels",
            float(params.payment_pct),
            "Hypothèse BP §4 ; contrat PSP.",
            PCT,
            True,
        ),
        ("b", "b — frais fixes de paiement (CHF/commande)", float(params.payment_fixed), "Hypothèse BP §4.", CHF, True),
        (
            "L",
            "L — logistique nette (CHF/commande)",
            float(params.logistics),
            "Hypothèse BP §4 ; devis transporteur.",
            CHF,
            True,
        ),
        ("R", "R — provision SAV (CHF/commande)", float(params.after_sales), "Hypothèse BP §4.", CHF, True),
        ("A", "A — acquisition attribuée (CHF/commande)", float(params.acquisition), "Hypothèse BP §4.", CHF, True),
        ("m", "m — contribution cible (% du CA net)", float(params.target_margin), "BP §5.", PCT, True),
        (
            "seuil",
            "Seuil « au-dessus du marché »",
            float(params.market_threshold),
            "BP §5 : > 10 % ⇒ à revoir.",
            PCT,
            True,
        ),
        (
            "tva_ch",
            "Taux normal de TVA suisse",
            float(params.vat_rate_ch),
            "Au 4.10.2026 [S6] ; à confirmer.",
            PCT,
            True,
        ),
        (
            "tva_import",
            "Taux de TVA à l'importation (estimation)",
            float(params.vat_rate_ch),
            "Estimation ; la base réelle se lit sur le décompte OFDF [S7].",
            PCT,
            True,
        ),
        ("floor_pct", "Plancher dur (% du CA net)", float(params.floor_pct), "BP §5 = stop-loss produit.", PCT, True),
        ("floor_chf", "Plancher dur (CHF/commande)", float(params.floor_chf), "BP §5 = stop-loss produit.", CHF, True),
        ("version", "Version des règles", params.rules_version, "Recopiée dans chaque décision de prix.", None, False),
    ]
    for key, label, value, note, fmt, editable in rows:
        r = P_CELLS[key]
        ws.cell(row=r, column=1, value=label).border = BORDER
        c = ws.cell(row=r, column=2, value=value)
        c.border = BORDER
        if fmt:
            c.number_format = fmt
        c.fill, c.font = (YELLOW, INPUT_FONT) if editable else (GREY, Font())
        n = ws.cell(row=r, column=3, value=note)
        n.alignment, n.border = WRAP, BORDER
    dv = DataValidation(type="list", formula1='"EFFECTIVE,NOT_REGISTERED"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(f"B{P_CELLS['mode']}")
    ws.freeze_panes = "A4"


SUP_HEAD = [
    "Fournisseur",
    "Pays d'expédition (ISO2)",
    "Devise",
    "Taux → CHF (CHF pour 1 unité)",
    "Source du taux",
    "Date du taux",
    "TVA facturée par le fournisseur (taux)",
    "Pays de cette TVA (ISO2)",
    "Incoterm",
    "Port amont total de la commande (devise)",
    "Frais fixes de commande (devise)",
    "Dédouanement / transitaire total (CHF)",
    "Minimum de commande (devise)",
    "Délai annoncé (jours ouvrés)",
    "Paiement",
    "Flux de données",
    "Exemple de fichier reçu (O/N)",
    "Statut",
    "Fictif (O/N)",
    "Complet (calculé)",
]
SUP_WIDTH = [26, 12, 9, 13, 18, 12, 14, 12, 10, 15, 14, 16, 14, 12, 16, 16, 12, 18, 9, 11]

FICTIF_SUPPLIERS = [
    # nom, pays, devise, taux, source, date, tva, pays tva, incoterm, port, frais, dédouanement,
    # minimum, délai, paiement, flux, exemple, statut
    (
        "FICTIF_FOURNISSEUR_A",
        "FR",
        "EUR",
        0.94,
        "FICTIF – exemple",
        date(2026, 10, 4),
        0,
        "FR",
        "DAP",
        40,
        0,
        25,
        500,
        5,
        "Prépaiement",
        "CSV",
        "N",
        "FICTIF",
    ),
    (
        "FICTIF_FOURNISSEUR_B",
        "CH",
        "CHF",
        1,
        "CHF (aucune conversion)",
        date(2026, 10, 4),
        0.081,
        "CH",
        "DAP",
        15,
        0,
        0,
        300,
        2,
        "30 jours",
        "XLSX",
        "N",
        "FICTIF",
    ),
]


def build_suppliers(ws: Worksheet) -> None:
    ws["A1"] = "Fournisseurs — conditions communes à toutes les lignes d'un même fournisseur"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "Aucune donnée réelle : les 6 fournisseurs du BP (et la piste hors BP) sont à compléter à réception "
        "des devis. Lignes orange = FICTIF."
    )
    ws["A2"].font = ITALIC
    _header(ws, 4, SUP_HEAD, SUP_WIDTH)
    rows: list[tuple] = [(name,) + ("",) * 16 + ("non contacté",) for name in BP_SUPPLIERS]
    rows += [tuple(s) for s in FICTIF_SUPPLIERS]
    for i in range(SUP_FIRST, SUP_LAST + 1):
        data = rows[i - SUP_FIRST] if i - SUP_FIRST < len(rows) else ("",) * 18
        fictif = str(data[0]).startswith("FICTIF")
        for col in range(1, 19):
            value = data[col - 1] if col - 1 < len(data) else ""
            c = ws.cell(row=i, column=col, value=value if value != "" else None)
            c.fill = ORANGE if fictif else YELLOW
            c.font, c.border = INPUT_FONT, BORDER
        ws.cell(row=i, column=19, value="O" if fictif else ("N" if data[0] else None)).fill = (
            ORANGE if fictif else YELLOW
        )
        ws.cell(row=i, column=19).border = BORDER
        req = ["B", "C", "D", "E", "F", "G", "H", "J", "K", "L"]
        cond = ",".join(f'{c}{i}<>""' for c in req)
        f = ws.cell(row=i, column=20, value=f'=IF(A{i}="","",IF(AND({cond}),1,0))')
        f.fill, f.border = GREY, BORDER
        ws.cell(row=i, column=4).number_format = FX
        ws.cell(row=i, column=6).number_format = "yyyy-mm-dd"
        ws.cell(row=i, column=7).number_format = PCT
        for col in (10, 11, 12, 13):
            ws.cell(row=i, column=col).number_format = CHF
    sup_lists = (("P", '"API,CSV,XLSX,XML,PDF/email,portail seul,inconnu"'), ("Q", '"O,N"'), ("S", '"O,N"'))
    for letter, formula in sup_lists:
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{letter}{SUP_FIRST}:{letter}{SUP_LAST}")
    ws.freeze_panes = "B5"


OFF_INPUT = [
    ("ref_id", 12),
    ("Désignation (format + extension + langue)", 40),
    ("Fournisseur", 22),
    ("SKU fournisseur", 14),
    ("EAN / GTIN", 15),
    ("Langue confirmée", 9),
    ("Extension", 20),
    ("Format", 10),
    ("Unités par conditionnement", 11),
    ("Prix du conditionnement (devise, avant remise)", 13),
    ("Base de prix (HT/TTC)", 9),
    ("Remise du palier atteint (fraction)", 10),
    ("Quantité commandée (conditionnements)", 11),
    ("MOQ (conditionnements)", 10),
    ("Disponibilité annoncée (unités)", 11),
    ("Allocation ferme (O/N)", 9),
    ("Date de dispo / sortie", 12),
    ("Prix marché observé TTC (CHF, médiane)", 13),
    ("Fictif (O/N)", 8),
]
OFF_CALC = [
    "Devise",
    "Taux → CHF",
    "TVA fournisseur (taux)",
    "Pays TVA",
    "Pays d'expédition",
    "Complet (1/0)",
    "Prix cond. après remise (devise)",
    "Prix HT cond. (devise)",
    "TVA fournisseur cond. (devise)",
    "Valeur ligne HT (CHF)",
    "Part de la commande fournisseur",
    "Port + frais ventilés / unité (CHF)",
    "Dédouanement ventilé / unité (CHF)",
    "Achat HT / unité (CHF)",
    "TVA fournisseur / unité (CHF)",
    "TVA fournisseur récupérable (1/0)",
    "TVA import estimée / unité (CHF)",
    "COÛT RENDU C / unité (CHF)",
    "Prix plancher TTC (CHF)",
    "Écart plancher / marché",
    "Contribution au prix marché (CHF)",
    "Contribution au prix marché (% CA net)",
    "Statut",
    "Alertes",
    "Rang (1 = moins cher)",
    "Clé de classement",
    "Total ligne rendu (CHF)",
]


def _lookup(col: str, i: int) -> str:
    sup_rng = f"'{SUP_SHEET}'!$A${SUP_FIRST}:$A${SUP_LAST}"
    tgt = f"'{SUP_SHEET}'!${col}${SUP_FIRST}:${col}${SUP_LAST}"
    return f'IF($C{i}="","",IFERROR(INDEX({tgt},MATCH($C{i},{sup_rng},0)),""))'


def offer_formulas(i: int) -> dict[str, str]:
    """Formules de la ligne ``i`` de la feuille Offres (colonnes T à AT)."""
    sup = f"MATCH($C{i},'{SUP_SHEET}'!$A${SUP_FIRST}:$A${SUP_LAST},0)"

    def sup_col(col: str) -> str:
        return f"INDEX('{SUP_SHEET}'!${col}${SUP_FIRST}:${col}${SUP_LAST},{sup})"

    a = f"$A${OFF_FIRST}:$A${OFF_LAST}"
    c = f"$C${OFF_FIRST}:$C${OFF_LAST}"
    y = f"$Y${OFF_FIRST}:$Y${OFF_LAST}"
    ac = f"$AC${OFF_FIRST}:$AC${OFF_LAST}"
    ak = f"$AK${OFF_FIRST}:$AK${OFF_LAST}"
    t, r_, b, L, R, A, m = (pref(k) for k in ("t", "r", "b", "L", "R", "A", "m"))
    complete = (
        f'IF(AND($A{i}<>"",$C{i}<>"",ISNUMBER($I{i}),ISNUMBER($J{i}),ISNUMBER($M{i})),'
        f'IF(AND($I{i}>=1,$J{i}>0,OR($K{i}="HT",$K{i}="TTC"),$M{i}>=1,'
        f"IFERROR({sup_col('T')},0)=1),1,0),0)"
    )
    return {
        "T": "=" + _lookup("C", i),
        "U": "=" + _lookup("D", i),
        "V": "=" + _lookup("G", i),
        "W": "=" + _lookup("H", i),
        "X": "=" + _lookup("B", i),
        "Y": f'=IF($A{i}="","",{complete})',
        "Z": f'=IF($Y{i}=1,$J{i}*(1-N($L{i})),"")',
        "AA": f'=IF($Y{i}=1,IF($K{i}="TTC",$Z{i}/(1+$V{i}),$Z{i}),"")',
        "AB": f'=IF($Y{i}=1,IF($K{i}="TTC",$Z{i}-$AA{i},$AA{i}*$V{i}),"")',
        "AC": f'=IF($Y{i}=1,$AA{i}*$U{i}*$M{i},"")',
        "AD": f'=IF($Y{i}=1,$AC{i}/SUMIFS({ac},{c},$C{i},{y},1),"")',
        "AE": f'=IF($Y{i}=1,({sup_col("J")}+{sup_col("K")})*$U{i}*$AD{i}/($I{i}*$M{i}),"")',
        "AF": f'=IF($Y{i}=1,{sup_col("L")}*$AD{i}/($I{i}*$M{i}),"")',
        "AG": f'=IF($Y{i}=1,$AA{i}*$U{i}/$I{i},"")',
        "AH": f'=IF($Y{i}=1,$AB{i}*$U{i}/$I{i},"")',
        "AI": f'=IF($Y{i}=1,IF(AND({pref("mode")}="EFFECTIVE",$W{i}="CH",$AB{i}>0),1,0),"")',
        "AJ": f'=IF($Y{i}=1,IF($X{i}<>"CH",($AG{i}+$AE{i}+$AF{i})*{pref("tva_import")},0),"")',
        "AK": (
            f'=IF($Y{i}=1,$AG{i}+IF($AI{i}=1,0,$AH{i})+$AE{i}+$AF{i}+IF({pref("mode")}="NOT_REGISTERED",$AJ{i},0),"")'
        ),
        "AL": f'=IF($Y{i}=1,($AK{i}+{b}+{L}+{R}+{A})/((1-{m})/(1+{t})-{r_}),"")',
        "AM": f'=IF(AND($Y{i}=1,ISNUMBER($R{i})),IF($R{i}>0,$AL{i}/$R{i}-1,""),"")',
        "AN": f'=IF(AND($Y{i}=1,ISNUMBER($R{i})),IF($R{i}>0,$R{i}/(1+{t})-$AK{i}-($R{i}*{r_}+{b})-{L}-{R}-{A},""),"")',
        "AO": f'=IF(ISNUMBER($AN{i}),$AN{i}/($R{i}/(1+{t})),"")',
        "AP": (
            f'=IF($A{i}="","",IF($Y{i}<>1,"INCOMPLET",IF(NOT(ISNUMBER($AM{i})),"SANS RÉF. MARCHÉ",'
            f'IF($AM{i}<={pref("seuil")},"OK",IF(AND($AO{i}>={pref("floor_pct")},$AN{i}>={pref("floor_chf")}),'
            f'"À REVOIR","NON RENTABLE")))))'
        ),
        "AQ": (
            f'=TRIM(IF(AND($Y{i}=1,ISNUMBER($N{i})),IF($M{i}<$N{i},"MOQ ",""),"")'
            f'&IF(AND($Y{i}=1,ISNUMBER($O{i})),IF($O{i}<$I{i}*$M{i},"DISPO ",""),"")'
            f'&IF($S{i}="O","FICTIF ","")'
            f'&IF($Y{i}=1,IF(AND($K{i}="TTC",$W{i}<>"CH"),"TVA-ÉTRANGÈRE ",""),""))'
        ),
        "AR": f'=IF($Y{i}=1,COUNTIFS({a},$A{i},{ak},"<"&$AK{i},{y},1)+1,"")',
        "AS": f'=IF(ISNUMBER($AR{i}),$A{i}&"|"&$AR{i},"")',
        "AT": f'=IF($Y{i}=1,$AK{i}*$I{i}*$M{i},"")',
    }


CALC_FORMATS = {
    "U": FX,
    "V": PCT,
    "Z": CHF,
    "AA": CHF4,
    "AB": CHF4,
    "AC": CHF,
    "AD": PCT,
    "AE": CHF4,
    "AF": CHF4,
    "AG": CHF4,
    "AH": CHF4,
    "AJ": CHF4,
    "AK": CHF,
    "AL": CHF,
    "AM": PCT,
    "AN": CHF,
    "AO": PCT,
    "AT": CHF,
}


def panier_rows() -> list[dict[str, str]]:
    """Lignes du panier pilote (même panier pour tous les fournisseurs)."""
    with PANIER.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def fictif_offers() -> list[list[object]]:
    """Deux lignes d'exemple FICTIF (même référence, deux fournisseurs FICTIFS)."""
    des = "FICTIF – ETB d'exemple (aucun produit réel)"
    return [
        [
            FICTIF_REF,
            des,
            "FICTIF_FOURNISSEUR_A",
            "FICTIF-A-001",
            gtin13("200000000101"),
            "FR",
            "FICTIF",
            "etb",
            1,
            40,
            "HT",
            0.05,
            10,
            6,
            50,
            "N",
            date(2026, 11, 2),
            69.90,
            "O",
        ],
        [
            FICTIF_REF,
            des,
            "FICTIF_FOURNISSEUR_B",
            "FICTIF-B-001",
            gtin13("200000000101"),
            "FR",
            "FICTIF",
            "etb",
            1,
            49.90,
            "TTC",
            None,
            10,
            1,
            20,
            "N",
            date(2026, 10, 20),
            69.90,
            "O",
        ],
    ]


def build_offers(ws: Worksheet) -> None:
    ws["A1"] = "Offres — une ligne par couple (référence, fournisseur), à partir d'un devis écrit"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "Aucun prix réel. Lignes 6-7 = exemple FICTIF. Lignes suivantes = panier pilote pré-rempli pour les "
        "3 fournisseurs FR prioritaires (BP §13), à compléter avec leurs devis."
    )
    ws["A2"].font = ITALIC
    ws["A3"] = "Saisie : colonnes A à S (jaune). Calcul : colonnes T à AT (gris)."
    ws["A3"].font = ITALIC
    labels = [h for h, _ in OFF_INPUT] + OFF_CALC
    widths = [w for _, w in OFF_INPUT] + [12] * len(OFF_CALC)
    _header(ws, OFF_FIRST - 1, labels, widths)
    rows: list[list[object]] = fictif_offers()
    for sup in PRIORITY_FR:
        for p in panier_rows():
            rows.append(
                [
                    p["ref_id"],
                    p["designation_attendue"],
                    sup,
                    None,
                    None,
                    None,
                    p["extension"] or None,
                    p["format"],
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "N",
                ]
            )
    if len(rows) > OFF_LAST - OFF_FIRST + 1:
        raise ValueError("trop de lignes pré-remplies")
    n_input = len(OFF_INPUT)
    for idx in range(OFF_LAST - OFF_FIRST + 1):
        i = OFF_FIRST + idx
        data = rows[idx] if idx < len(rows) else [None] * n_input
        fictif = data[-1] == "O"
        for col in range(1, n_input + 1):
            cell = ws.cell(row=i, column=col, value=data[col - 1])
            cell.fill = ORANGE if fictif else YELLOW
            cell.font, cell.border = INPUT_FONT, BORDER
        ws.cell(row=i, column=10).number_format = CHF
        ws.cell(row=i, column=12).number_format = PCT
        ws.cell(row=i, column=17).number_format = "yyyy-mm-dd"
        ws.cell(row=i, column=18).number_format = CHF
        for col_letter, formula in offer_formulas(i).items():
            cell = ws[f"{col_letter}{i}"]
            cell.value = formula
            cell.fill, cell.border = GREY, BORDER
            if col_letter in CALC_FORMATS:
                cell.number_format = CALC_FORMATS[col_letter]
        ws[f"AK{i}"].font = BOLD
    validations = (
        ("C", f"='{SUP_SHEET}'!$A${SUP_FIRST}:$A${SUP_LAST}"),
        ("K", '"HT,TTC"'),
        ("P", '"O,N"'),
        ("S", '"O,N"'),
    )
    for letter, formula in validations:
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{letter}{OFF_FIRST}:{letter}{OFF_LAST}")
    status = f"AP{OFF_FIRST}:AP{OFF_LAST}"
    for text, color in (("OK", "C6EFCE"), ("À REVOIR", "FFEB9C"), ("NON RENTABLE", "FFC7CE"), ("INCOMPLET", "E7E6E6")):
        ws.conditional_formatting.add(
            status, CellIsRule(operator="equal", formula=[f'"{text}"'], fill=PatternFill("solid", fgColor=color))
        )
    ws.conditional_formatting.add(
        f"AR{OFF_FIRST}:AR{OFF_LAST}",
        FormulaRule(formula=[f"$AR{OFF_FIRST}=1"], font=Font(bold=True, color="006100")),
    )
    ws.freeze_panes = f"D{OFF_FIRST}"


def rank_refs() -> list[tuple[str, str]]:
    refs = [(FICTIF_REF, "FICTIF – ETB d'exemple (aucun produit réel)")]
    refs += [(p["ref_id"], p["designation_attendue"]) for p in panier_rows()]
    return refs


def build_ranking(ws: Worksheet) -> None:
    ws["A1"] = "Classement par référence — le moins cher en coût rendu C (CHF/unité) est au rang 1"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "Aide à la décision : le choix final tient aussi compte de l'allocation, du délai, du flux de données "
        "et de la due diligence (C08). En cas d'égalité au rang 1, aucun « 2e » n'est affiché."
    )
    ws["A2"].font = ITALIC
    head = [
        "ref_id",
        "Désignation",
        "Offres complètes",
        "Meilleur fournisseur",
        "C du meilleur (CHF)",
        "2e fournisseur",
        "C du 2e (CHF)",
        "Écart 2e / 1er",
        "Prix marché (CHF)",
        "Plancher du meilleur (CHF)",
        "Statut du meilleur",
        "Alertes du meilleur",
    ]
    _header(ws, 4, head, [12, 44, 10, 24, 12, 24, 12, 10, 12, 12, 16, 18])
    off = f"'{OFF_SHEET}'!"
    key = f"{off}$AS${OFF_FIRST}:$AS${OFF_LAST}"

    def pick(col: str, rank: int, i: int) -> str:
        return f'IFERROR(INDEX({off}${col}${OFF_FIRST}:${col}${OFF_LAST},MATCH($A{i}&"|{rank}",{key},0)),"")'

    for n, (ref, des) in enumerate(rank_refs()):
        i = 5 + n
        ws.cell(row=i, column=1, value=ref)
        ws.cell(row=i, column=2, value=des)
        formulas = {
            3: f"=COUNTIFS({off}$A${OFF_FIRST}:$A${OFF_LAST},$A{i},{off}$Y${OFF_FIRST}:$Y${OFF_LAST},1)",
            4: "=" + pick("C", 1, i),
            5: "=" + pick("AK", 1, i),
            6: "=" + pick("C", 2, i),
            7: "=" + pick("AK", 2, i),
            8: f'=IF(AND(ISNUMBER($E{i}),ISNUMBER($G{i})),$G{i}/$E{i}-1,"")',
            9: "=" + pick("R", 1, i),
            10: "=" + pick("AL", 1, i),
            11: f'=IF($C{i}=0,"AUCUNE OFFRE",{pick("AP", 1, i)})',
            12: "=" + pick("AQ", 1, i),
        }
        for col, f in formulas.items():
            c = ws.cell(row=i, column=col, value=f)
            c.fill = GREY
        for col in range(1, 13):
            ws.cell(row=i, column=col).border = BORDER
        for col in (5, 7, 9, 10):
            ws.cell(row=i, column=col).number_format = CHF
        ws.cell(row=i, column=8).number_format = PCT
        if ref == FICTIF_REF:
            for col in (1, 2):
                ws.cell(row=i, column=col).fill = ORANGE
    ws.freeze_panes = "C5"


def build_synthesis(ws: Worksheet) -> None:
    ws["A1"] = "Synthèse par fournisseur"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "Couverture du panier, valeur de la commande, minimum de commande. "
        "Les montants ne valent que pour les lignes complètes."
    )
    ws["A2"].font = ITALIC
    head = [
        "Fournisseur",
        "Lignes complètes",
        "Lignes incomplètes",
        "Références au rang 1",
        "Valeur commande HT (CHF)",
        "Total rendu (CHF)",
        "Valeur commande HT (devise)",
        "Minimum de commande atteint",
        "Flux de données",
        "Exemple de fichier reçu",
        "Statut",
    ]
    _header(ws, 4, head, [26, 11, 11, 11, 14, 14, 14, 14, 16, 12, 18])
    off = f"'{OFF_SHEET}'!"
    sup = f"'{SUP_SHEET}'!"
    cc = f"{off}$C${OFF_FIRST}:$C${OFF_LAST}"
    for n in range(SUP_LAST - SUP_FIRST + 1):
        i = 5 + n
        s = SUP_FIRST + n
        formulas = {
            1: f'=IF({sup}$A${s}="","",{sup}$A${s})',
            2: f'=IF($A{i}="","",COUNTIFS({cc},$A{i},{off}$Y${OFF_FIRST}:$Y${OFF_LAST},1))',
            3: f'=IF($A{i}="","",COUNTIFS({cc},$A{i},{off}$Y${OFF_FIRST}:$Y${OFF_LAST},0))',
            4: f'=IF($A{i}="","",COUNTIFS({cc},$A{i},{off}$AR${OFF_FIRST}:$AR${OFF_LAST},1))',
            5: f'=IF($A{i}="","",SUMIFS({off}$AC${OFF_FIRST}:$AC${OFF_LAST},{cc},$A{i}))',
            6: f'=IF($A{i}="","",SUMIFS({off}$AT${OFF_FIRST}:$AT${OFF_LAST},{cc},$A{i}))',
            7: f'=IF(OR($A{i}="",NOT(ISNUMBER({sup}$D${s}))),"",IF({sup}$D${s}>0,$E{i}/{sup}$D${s},""))',
            8: (
                f'=IF($A{i}="","",IF(OR($B{i}=0,NOT(ISNUMBER($G{i})),NOT(ISNUMBER({sup}$M${s}))),"?",'
                f'IF($G{i}>={sup}$M${s},"OUI","NON")))'
            ),
            9: f'=IF($A{i}="","",IF({sup}$P${s}="","inconnu",{sup}$P${s}))',
            10: f'=IF($A{i}="","",IF({sup}$Q${s}="","?",{sup}$Q${s}))',
            11: f'=IF($A{i}="","",IF({sup}$R${s}="","",{sup}$R${s}))',
        }
        for col, f in formulas.items():
            c = ws.cell(row=i, column=col, value=f)
            c.fill, c.border = GREY, BORDER
        for col in (5, 6, 7):
            ws.cell(row=i, column=col).number_format = CHF
    ws.freeze_panes = "B5"


def build_workbook(path: Path, vat_mode: str = "EFFECTIVE") -> Path:
    """Construit le classeur (formules non calculées) à ``path``."""
    params = load_params(vat_mode)
    wb = Workbook()
    build_help(wb.active, params)
    build_params(wb.create_sheet(PARAM_SHEET), params)
    build_suppliers(wb.create_sheet(SUP_SHEET))
    build_offers(wb.create_sheet(OFF_SHEET))
    build_ranking(wb.create_sheet(RANK_SHEET))
    build_synthesis(wb.create_sheet(SYN_SHEET))
    wb.properties.title = "Comparateur d'offres fournisseurs — FICTIF uniquement"
    wb.properties.creator = "Agent pilotage-marche-sourcing"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


class RecalcError(RuntimeError):
    """Échec du recalcul LibreOffice."""


def soffice_path() -> str | None:
    """Chemin de LibreOffice (None si absent)."""
    return shutil.which("soffice") or shutil.which("libreoffice")


def recalculate(src: Path, dest_dir: Path, timeout: int = 180) -> Path:
    """Recalcule ``src`` avec LibreOffice headless ; écrit la copie recalculée dans ``dest_dir``."""
    soffice = soffice_path()
    if soffice is None:
        raise RecalcError("soffice introuvable")
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lo-sourcing-") as tmp:
        tmp_path = Path(tmp)
        out = tmp_path / "out"
        cmd = [
            soffice,
            "--headless",
            "--norestore",
            "--nologo",
            f"-env:UserInstallation={(tmp_path / 'profile').as_uri()}",
            "--convert-to",
            "xlsx:Calc Office Open XML",
            "--outdir",
            str(out),
            str(src.resolve()),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RecalcError(f"LibreOffice : délai dépassé ({timeout} s)") from exc
        produced = out / src.name
        if proc.returncode != 0 or not produced.exists():
            raise RecalcError(f"LibreOffice n'a pas converti {src.name} : {proc.stdout} {proc.stderr}".strip())
        target = dest_dir / src.name
        shutil.copyfile(produced, target)
    return target


def formula_errors(path: Path) -> list[str]:
    """Cellules en erreur après recalcul (doit être vide)."""
    wb = load_workbook(path, data_only=True)
    errors: list[str] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith(ERROR_TOKENS):
                    errors.append(f"{ws.title}!{cell.coordinate} = {cell.value}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sans-recalcul", action="store_true", help="ne pas recalculer avec LibreOffice")
    parser.add_argument("--sortie", type=Path, default=OUTPUT, help="chemin du classeur")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="comparateur-") as tmp:
        raw = build_workbook(Path(tmp) / args.sortie.name)
        if args.sans_recalcul:
            shutil.copyfile(raw, args.sortie)
            print(f"Écrit (sans recalcul) : {args.sortie}")
            return 0
        done = recalculate(raw, Path(tmp) / "recalc")
        errors = formula_errors(done)
        if errors:
            print("Erreurs de formules :", *errors[:20], sep="\n  ")
            return 1
        shutil.copyfile(done, args.sortie)
    print(f"Écrit et recalculé sans erreur : {args.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
