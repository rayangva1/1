#!/usr/bin/env python3
"""Génère docs/06-contenu/CALENDRIER_90J.csv (import Notion : première colonne = titre).

Les données du calendrier sont ici, sous forme de lignes datées par numéro de jour (J1 = lundi
5 octobre 2026, hypothèse du plan 90 jours) : la date, le jour de la semaine, la semaine et la
phase BP §9 sont calculés, donc toujours cohérents. Pour décaler tout le calendrier si J1 change :
``python docs/06-contenu/outils/generer_calendrier.py --j1 AAAA-MM-JJ``.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "CALENDRIER_90J.csv"
J1_DEFAUT = date(2026, 10, 5)
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
COLONNES = (
    "Nom", "Date", "Jour", "J", "Semaine", "Phase BP §9", "Type", "Canal", "Format", "Pilier", "Sujet",
    "Accroche", "CTA", "Visuels réels nécessaires", "Condition de publication", "Responsable", "Statut", "Notes",
)
PILIERS = ("Guide", "Nouveauté accessible", "Preuve de service", "—")
TYPES = ("Publication", "Email", "Production", "Publicité", "SEO")
J_RECEPTION = 35  # réception du stock pilote (plan 90 jours, cible)
J_OUVERTURE = 38  # ouverture douce (plan 90 jours, cible)

RS = "Instagram + TikTok"
COND_EDUC = "Aucune donnée de stock ni de prix ; faits sourcés (15_SUJETS.md) ; ton validé"
COND_NOUV = (
    "Stock local > 0 sur la fiche publiée ; prix et stock relus sur la page publique moins d'1 h avant (hypothèse) ; "
    "aucun stop-loss produit ou pub actif sur la référence"
)
COND_RECAP = (
    "Inscrits confirmés ayant choisi le récapitulatif uniquement ; annulé s'il n'y a rien d'utile (BP §9 : 1 récapitulatif "
    "pertinent au maximum par semaine)"
)
VIS_GABARIT = "Gabarits DA (docs/05-da/social/), aucun emballage réel ni généré"
VIS_PRODUIT = "Photo réelle du produit en stock (session A06), sans prix incrusté"


@dataclass(frozen=True)
class Ligne:
    """Une entrée du calendrier (j = numéro de jour, J1 = premier lundi)."""

    j: int
    type: str
    canal: str
    format: str
    pilier: str
    sujet: str
    nom: str
    accroche: str
    cta: str
    visuels: str
    condition: str
    responsable: str
    notes: str = ""


LIGNES: tuple[Ligne, ...] = (
    # --- J1-15 : préparation, landing --------------------------------------------------------------
    Ligne(5, "Production", "Interne", "—", "—", "S01, S09", "Préparer les premiers carrousels avec les gabarits DA",
          "—", "—", VIS_GABARIT, "DA proposée disponible (docs/05-da)", "A-09", "Aucune publication avant les comptes (B08, J8)"),
    Ligne(8, "Production", "Interne", "—", "—", "—", "Créer les comptes Instagram et TikTok de la boutique",
          "—", "—", "—", "Nom validé (C06)", "H (B08)", "Acte de la propriétaire ; accès rangés dans le coffre"),
    Ligne(10, "Email", "Email automatique", "Emails 01 et 02", "—", "—", "Activer la confirmation d'inscription et l'email de bienvenue",
          "—", "—", "—", "Workflow n8n testé de bout en bout (site/landing/README.md §4)", "A-07, A-12", "Double opt-in : rien n'est envoyé avant le clic"),
    Ligne(10, "Publication", RS, "Carrousel 4:5", "Preuve de service", "S09", "Présentation : nos trois règles",
          "On prépare une boutique de cartes Pokémon en français, à Genève. Voici nos trois règles.",
          "Recevoir l'alerte d'ouverture (lien en bio)", VIS_GABARIT, "Landing publiée (GO C07) ; nom validé (C06)", "A-09", "UTM : utm_source=instagram / tiktok"),
    Ligne(12, "Publication", RS, "Carrousel 4:5", "Guide", "S01", "ETB ou display : lequel choisir ?",
          "ETB ou display ? La différence en 6 images.", "Recevoir l'alerte d'ouverture", VIS_GABARIT + " ; schémas sans emballage", COND_EDUC, "A-09"),
    # --- J16-30 : identité, site test, contenus éducatifs -------------------------------------------
    Ligne(15, "Publication", RS, "Carrousel 4:5", "Guide", "S09", "Stock local, précommande, rupture : ce que ça veut dire",
          "Trois mots, trois promesses.", "Recevoir l'alerte d'ouverture", VIS_GABARIT + " ; badges DA", COND_EDUC, "A-09"),
    Ligne(17, "Publication", RS, "Carrousel 4:5", "Preuve de service", "S07", "Comment marcheront nos précommandes",
          "Pourquoi nous n'ouvrirons pas de précommande sur chaque sortie.", "Lire nos conditions (page Précommandes)", VIS_GABARIT,
          COND_EDUC + " ; texte PRECOMMANDES validé par le juriste", "A-09"),
    Ligne(18, "Email", "Email aux inscrits", "Email 05 (avant ouverture)", "Guide", "S09, S07", "Récapitulatif n° 1 : où en est l'ouverture",
          "Où en est l'ouverture, et comment liront nos fiches.", "Lire le guide", "—", COND_RECAP, "A-09", "Aucune date d'ouverture ferme (protocole landing §2)"),
    Ligne(19, "Publication", RS + " + site", "Article SEO + carrousel 4:5", "Guide", "S02", "Premier achat de cartes Pokémon : par où commencer ?",
          "Premier achat de cartes Pokémon : par où commencer ?", "Lire le guide complet", VIS_GABARIT, COND_EDUC, "A-08, A-09"),
    Ligne(22, "Publication", RS, "Reel 25 s (texte seul)", "Guide", "S11", "Carte rare garantie ? Non.",
          "Peut-on vous garantir une carte rare ? Non. Voici pourquoi.", "Lire notre FAQ", VIS_GABARIT + " (version texte du script V8)", COND_EDUC, "A-09"),
    Ligne(24, "Publication", RS + " + site", "Article SEO + carrousel 4:5", "Guide", "S03", "C'est quoi, une extension ?",
          "Méga-Évolution, 30ᵉ Anniversaire… c'est quoi, une extension ?", "Recevoir les alertes", VIS_GABARIT,
          COND_EDUC + " ; dates de sortie reconfirmées sur la source officielle", "A-08, A-09", "Ne jamais présenter une date de sortie comme une date d'arrivée chez nous"),
    Ligne(25, "Email", "Email aux inscrits", "Email 05 (avant ouverture)", "Guide", "S02, S11", "Récapitulatif n° 2",
          "Premier achat : par où commencer.", "Lire le guide", "—", COND_RECAP, "A-09"),
    Ligne(26, "Publication", RS, "Carrousel 4:5", "Guide", "S14", "Sortie, avant-première, réassort : le vocabulaire",
          "Sortie, avant-première, réassort : qui fait quoi ?", "Recevoir les alertes", VIS_GABARIT,
          COND_EDUC + " ; aucune promesse sur la sortie du 6.11", "A-09", "Avant-premières du 24.10 dans des boutiques participantes : pas chez nous"),
    Ligne(29, "Publication", RS, "Carrousel 4:5", "Guide", "S04", "Offrir des cartes Pokémon : 3 questions",
          "Offrir des cartes Pokémon sans se tromper : 3 questions.", "Recevoir l'alerte d'ouverture", VIS_GABARIT, COND_EDUC, "A-09"),
    # --- J31-45 : réception, photos, ouverture douce ------------------------------------------------
    Ligne(31, "Publication", RS, "Carrousel 4:5 (photos)", "Preuve de service", "S13", "Coulisses : on prépare l'ouverture",
          "Étagères, cartons, contrôles : on se prépare.", "Recevoir l'alerte d'ouverture", "Photos réelles du lieu de stockage et des emballages (sans adresse)",
          "Lieu de stockage aménagé (A05) ; aucun produit présenté comme en stock", "A-09, H (photos)"),
    Ligne(32, "Email", "Email aux inscrits", "Email 05 (avant ouverture)", "Guide", "S14", "Récapitulatif n° 3",
          "Sortie, avant-première, réassort : le vocabulaire.", "Lire le guide", "—", COND_RECAP, "A-09", "Pas d'annonce d'ouverture avant réception et contrôle du stock"),
    Ligne(33, "Publication", RS, "Carrousel 4:5", "Preuve de service", "S15", "Commande passée : et maintenant ?",
          "Délais, suivi, colis abîmé : tout ce qui se passe après la commande.", "Lire Livraison et retours", VIS_GABARIT,
          "Champs DELAI_EXPEDITION, SEUIL_COLIS_BLOQUE et DELAI_SIGNALEMENT validés (registre légal)", "A-09"),
    Ligne(35, "Production", "Interne", "Reel V3 (rushes)", "—", "S13", "Réception du stock et tournage du script V3",
          "—", "—", "Réception réelle filmée (SOP réception C1-C9), sans document d'achat", "Livraison reçue", "H (A03, A04)"),
    Ligne(36, "Publication", RS, "Reel 35 s (V3)", "Preuve de service", "S13", "Réception : ce que nous contrôlons",
          "Avant d'être en vente, chaque boîte passe ce contrôle.", "Recevoir l'alerte d'ouverture", "Rushes V3 du J35",
          "Stock réceptionné et contrôlé ; aucun prix ; aucune promesse de date d'ouverture", "A-09"),
    Ligne(37, "Production", "Interne", "Session A06", "—", "S01, S05, S06, S04, S09, S11", "Session photos et vidéos (V1, V2, V5, V6, V7, V8 + photos des fiches)",
          "—", "—", "Tous les produits reçus ; décor table (SCRIPTS_VIDEO.md §1)", "Stock reçu (J35)", "H (A06)", "≈ 2 à 3 h"),
    Ligne(38, "Email", "Email aux inscrits", "Email 03", "Nouveauté accessible", "—", "Ouverture douce : la boutique est ouverte",
          "C'est ouvert : voici ce qui est en stock local.", "Voir le stock local", VIS_PRODUIT,
          "GO ouverture douce (C14) ; fiches publiées ; " + COND_NOUV, "A-09 (BL-118)", "Envoyé aux seuls inscrits confirmés"),
    Ligne(38, "Publication", RS, "Carrousel 4:5 (photos)", "Nouveauté accessible", "—", "Ouverture : ce qui est en stock local",
          "C'est ouvert. Voici ce qui est réellement en stock à Genève.", "Voir le stock local", VIS_PRODUIT, "GO ouverture douce (C14) ; " + COND_NOUV, "A-09"),
    Ligne(40, "Publication", RS, "Reel 30 s (V1)", "Guide", "S01", "ETB ou display ? (vidéo)",
          "ETB ou display : la différence en 30 secondes.", "Voir les displays et ETB en stock", "Rushes V1", COND_EDUC, "A-09"),
    Ligne(43, "Publication", RS, "Reel 25 s (V2)", "Guide", "S06", "FR, EN ou JP : repérer la langue",
          "FR, EN ou JP ? Comment repérer la langue d'une boîte.", "Voir le stock local", "Rushes V2", COND_EDUC, "A-09"),
    Ligne(43, "Production", "Interne", "—", "—", "—", "Dossier G4 et plan du test publicitaire",
          "—", "—", "—", "Premières commandes livrées", "A-01, A-10", "PUBLICITE_TEST.md"),
    Ligne(45, "Publication", RS, "Carrousel 4:5 (photos)", "Nouveauté accessible", "—", "Nouveauté accessible de la semaine",
          "[Format] [extension] en français : en stock local, expédié sous [délai].", "Voir la fiche", VIS_PRODUIT, COND_NOUV, "A-09"),
    Ligne(46, "Email", "Email aux inscrits", "Email 05", "Nouveauté accessible", "S06", "Récapitulatif hebdomadaire",
          "Ce qui est en stock cette semaine, et un guide.", "Voir le stock local", VIS_PRODUIT, COND_RECAP + " ; " + COND_NOUV, "A-09"),
    # --- J46-60 : test pub, collaboration, emails de réassort ---------------------------------------
    Ligne(47, "Publication", RS, "Reel 40 s (V4)", "Preuve de service", "S08", "Coulisses d'expédition",
          "Ce qui arrive à votre commande entre le clic et le dépôt du colis.", "Voir le stock local", "Rushes V4 (aucune étiquette lisible)",
          "Premières commandes préparées ; aucune donnée client visible", "A-09"),
    Ligne(50, "Publicité", "Meta (Instagram/Facebook)", "2-3 créations", "—", "S01, S08", "Test publicitaire : préparation et décision de date",
          "—", "—", "Créations de PUBLICITE_TEST.md §4", "G4 VERT ; niveau 3 (C15) ; comptes pub avec plafond (B20) ; cash ≥ 1 600 CHF + budget",
          "A-10", "Option A : démarrage le 30.11 ; option B : plafond jour divisé par deux jusqu'au 30.11 (EC-10)"),
    Ligne(50, "Publication", RS, "Carrousel 1:1 (photos)", "Guide", "S10", "Que contient vraiment la boîte ?",
          "Bundle, tripack, coffret : combien de boosters dedans ?", "Comparer dans la collection", "Photos réelles des produits reçus (mention de contenu lisible)",
          COND_EDUC + " ; contenus repris des fiches validées", "A-09"),
    Ligne(50, "Email", "Email automatique", "Email 04", "Nouveauté accessible", "—", "Alertes de stock local aux inscrits intéressés (à chaque réception)",
          "Ce que vous attendiez est en stock local.", "Voir la fiche", VIS_PRODUIT, "Déclenché par une entrée en stock local réelle ; " + COND_NOUV,
          "A-09 (BL-135)", "Événementiel, pas planifié ; segment = préférences + alerte produit"),
    Ligne(52, "Publication", RS, "Carrousel 4:5 (photos)", "Nouveauté accessible", "—", "Nouveauté accessible de la semaine",
          "[Format] [extension] en français : en stock local.", "Voir la fiche", VIS_PRODUIT, COND_NOUV, "A-09"),
    Ligne(53, "Email", "Email aux inscrits", "Email 05", "Guide", "S10", "Récapitulatif hebdomadaire",
          "Que contient vraiment la boîte ? Et ce qui est en stock.", "Lire le guide", VIS_PRODUIT, COND_RECAP, "A-09"),
    Ligne(54, "Publication", RS, "Reel 20 s (V7)", "Preuve de service", "S09", "Lire une fiche : les 3 statuts (vidéo)",
          "Sur nos fiches, trois mots, trois promesses.", "Voir le stock local", "Rushes V7 (captures de fiches réelles)",
          "Black Friday : aucune promotion hors moteur prix, aucun message d'urgence", "A-09"),
    Ligne(55, "Production", "Interne", "—", "—", "—", "Collaboration locale limitée : brief et validation",
          "—", "—", "—", "Dossier créateur complet (BRIEF_CREATEURS.md) ; contrat validé (C15)", "A-10, H", "Inclus dans les 500 CHF du test (EC-17)"),
    Ligne(57, "Publication", RS, "Reel 30 s (V5)", "Guide", "S05", "Protéger ses cartes",
          "Trois gestes pour protéger vos cartes.", "Voir les accessoires", "Rushes V5 (accessoires en stock)",
          COND_EDUC + " ; accessoires en stock local", "A-09"),
    Ligne(57, "Publicité", "Meta (Instagram/Facebook)", "2-3 créations", "—", "—", "Test publicitaire : démarrage (option A) ou suite (option B)",
          "—", "—", "—", "Stop-loss pub actif ; plafond jour du mandat ; mesure sur commandes payées nettes", "A-10"),
    Ligne(59, "Publication", RS, "Carrousel 4:5 (photos)", "Nouveauté accessible", "—", "Nouveauté accessible ou réassort de la semaine",
          "[Format] [extension] : de retour en stock local.", "Voir la fiche", VIS_PRODUIT, COND_NOUV, "A-09"),
    Ligne(60, "Email", "Email aux inscrits", "Email 05", "Preuve de service", "S15", "Récapitulatif hebdomadaire",
          "Délais, suivi, cadeaux : ce qu'il faut savoir.", "Voir le stock local", VIS_PRODUIT, COND_RECAP, "A-09"),
    Ligne(60, "Publicité", "Interne", "Bilan", "—", "—", "Gate G5 : CAC 7 jours contre contribution",
          "—", "—", "—", "7 jours de données ; commandes payées nettes", "A-10, A-05, H (C16)"),
    # --- J61-90 : réassort, SEO extensions, scénarios email, bilan ---------------------------------
    Ligne(61, "Publication", RS, "Carrousel 4:5", "Preuve de service", "S15", "Votre colis : délais, suivi, colis abîmé",
          "Commande passée : et maintenant ?", "Lire Livraison et retours", VIS_GABARIT, "Dates d'expédition de fin d'année confirmées par le transporteur avant de les citer", "A-09"),
    Ligne(64, "SEO", "Site", "Pages d'extension", "Guide", "S03", "Pages SEO par extension en stock (BL-143)",
          "—", "Voir l'extension", VIS_PRODUIT, "Une page par extension réellement proposée ; faits sourcés", "A-08", "SEO.md §2"),
    Ligne(64, "Publication", RS + " + site", "Article SEO + carrousel", "Guide", "S03", "Comprendre une extension (page d'extension)",
          "Une extension, plusieurs produits : on vous explique.", "Voir la page de l'extension", VIS_PRODUIT, COND_EDUC, "A-08, A-09"),
    Ligne(66, "Publication", RS, "Carrousel 4:5 (photos)", "Nouveauté accessible", "—", "Nouveauté accessible de la semaine",
          "[Format] [extension] en français : en stock local.", "Voir la fiche", VIS_PRODUIT, COND_NOUV, "A-09"),
    Ligne(67, "Email", "Email aux inscrits", "Email 05", "Guide", "S04", "Récapitulatif : idées cadeaux et dates d'expédition",
          "Offrir sans se tromper, et quand commander pour les fêtes.", "Voir les idées cadeaux", VIS_PRODUIT,
          COND_RECAP + " ; dates limites confirmées par le transporteur", "A-09"),
    Ligne(68, "Publication", RS, "Story + carrousel", "Preuve de service", "S15", "Dates d'expédition avant les fêtes",
          "Pour recevoir avant Noël : commandes jusqu'au [date transporteur].", "Voir le stock local", VIS_GABARIT,
          "Date limite confirmée par le transporteur (BL-053) ; pas de « dernière chance »", "A-09"),
    Ligne(71, "Publication", RS, "Reel 30 s (V6)", "Guide", "S04", "Offrir sans se tromper (vidéo)",
          "Vous voulez offrir des cartes Pokémon ? Trois questions avant d'acheter.", "Voir les idées cadeaux", "Rushes V6", COND_EDUC, "A-09"),
    Ligne(73, "Publication", RS, "Carrousel 4:5 (photos)", "Nouveauté accessible", "—", "Nouveauté accessible de la semaine",
          "[Format] [extension] en français : en stock local.", "Voir la fiche", VIS_PRODUIT, COND_NOUV, "A-09"),
    Ligne(74, "Email", "Email aux inscrits", "Email 05", "Preuve de service", "S15", "Récapitulatif : date limite d'expédition",
          "Les dates d'expédition avant les fêtes.", "Voir le stock local", VIS_PRODUIT, COND_RECAP + " ; dates confirmées", "A-09"),
    Ligne(75, "Email", "Email automatique", "Emails 11, 12 (et 13 si consentement)", "—", "—", "Activer les scénarios accueil, avis et réachat (BL-144)",
          "—", "—", "—", "Consentement et disponibilité vérifiés ; textes validés (L44)", "A-09, A-07"),
    Ligne(75, "Publication", RS, "Reel 30 s (rushes V4 renouvelés)", "Preuve de service", "S08", "Coulisses : la préparation avant les fêtes",
          "Une session de colis, du scan au sticker de fermeture.", "Voir le stock local", "Session de préparation réelle (aucune étiquette ni nom lisible)",
          "Aucune donnée client visible ; aucun « dernière chance »", "A-09, H (tournage)"),
    Ligne(78, "Publication", RS + " + site", "Article SEO + Reel", "Guide", "S12", "Ranger et classer sa collection",
          "Votre collection déborde ? Trois façons de la ranger.", "Voir les accessoires", "Photos réelles d'accessoires en stock", COND_EDUC, "A-08, A-09"),
    Ligne(80, "Publication", RS, "Story + carrousel", "Preuve de service", "S15", "Expéditions pendant les fêtes : notre calendrier",
          "Nos jours d'expédition entre Noël et Nouvel An.", "Voir le stock local", VIS_GABARIT,
          "Jours d'expédition décidés par la propriétaire (absence planifiée)", "A-09", "Pas d'email le 24.12 ni le 31.12, sauf information d'expédition"),
    Ligne(85, "Publication", RS, "Reel 25 s (V8)", "Guide", "S11", "Carte rare garantie ? Non. (vidéo)",
          "Peut-on vous garantir une carte rare ? Non.", "Lire notre FAQ", "Rushes V8", COND_EDUC, "A-09"),
    Ligne(87, "Publication", RS, "Carrousel 4:5 (photos)", "Nouveauté accessible", "—", "Réassort accessible de la semaine",
          "[Format] [extension] : de retour en stock local.", "Voir la fiche", VIS_PRODUIT, COND_NOUV + " ; réassort validé (C17)", "A-09"),
    Ligne(90, "Publication", RS, "Carrousel 4:5 (photos)", "Preuve de service", "S13", "Scellé et authentique : nos contrôles",
          "Avant d'être en vente, chaque boîte passe ce contrôle.", "Voir le stock local", "Photos réelles de réception", COND_EDUC, "A-09",
          "Publication programmée (samedi 2 janvier)"),
    Ligne(90, "Production", "Interne", "Bilan", "—", "—", "Bilan G6 : contenus, emails, publicité",
          "—", "—", "—", "—", "A-01, A-09, A-10", "Entrées et commandes par source UTM ; sujets qui convertissent"),
)


def phase(j: int) -> str:
    """Phase du BP §9 pour un numéro de jour."""
    if j <= 15:
        return "J1-15 Étude, entretiens, dossier B2B, landing et inscriptions"
    if j <= 30:
        return "J16-30 Identité, site test, contenus éducatifs"
    if j <= 45:
        return "J31-45 Réception, photos, ouverture douce, 3 contenus/semaine"
    if j <= 60:
        return "J46-60 Test pub ≤ 500 CHF, collaboration locale, emails réassort"
    return "J61-90 Réassort, SEO extensions, scénarios email, bilan"


def lignes_csv(j1: date = J1_DEFAUT) -> list[dict[str, str]]:
    """Lignes du calendrier prêtes à écrire, triées par jour puis par type."""
    ordre_type = {t: i for i, t in enumerate(TYPES)}
    sortie = []
    for ligne in sorted(LIGNES, key=lambda x: (x.j, ordre_type[x.type])):
        jour = j1 + timedelta(days=ligne.j - 1)
        sortie.append(
            {
                "Nom": ligne.nom,
                "Date": jour.isoformat(),
                "Jour": JOURS[jour.weekday()],
                "J": f"J{ligne.j}",
                "Semaine": f"S{(ligne.j - 1) // 7 + 1}",
                "Phase BP §9": phase(ligne.j),
                "Type": ligne.type,
                "Canal": ligne.canal,
                "Format": ligne.format,
                "Pilier": ligne.pilier,
                "Sujet": ligne.sujet,
                "Accroche": ligne.accroche,
                "CTA": ligne.cta,
                "Visuels réels nécessaires": ligne.visuels,
                "Condition de publication": ligne.condition,
                "Responsable": ligne.responsable,
                "Statut": "À préparer",
                "Notes": ligne.notes,
            }
        )
    return sortie


def contenu_csv(j1: date = J1_DEFAUT) -> str:
    """Texte CSV (UTF-8, virgules, guillemets si nécessaire, fins de ligne \\n)."""
    tampon = io.StringIO()
    ecrivain = csv.DictWriter(tampon, fieldnames=COLONNES, lineterminator="\n")
    ecrivain.writeheader()
    ecrivain.writerows(lignes_csv(j1))
    return tampon.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--j1", type=date.fromisoformat, default=J1_DEFAUT, help="date de J1 (lundi), AAAA-MM-JJ")
    parser.add_argument("--verifier", action="store_true", help="code 1 si le CSV diffère de la génération")
    args = parser.parse_args(argv)
    if args.j1.weekday() != 0:
        print("J1 doit être un lundi.")
        return 1
    texte = contenu_csv(args.j1)
    if args.verifier:
        ok = SORTIE.exists() and SORTIE.read_text(encoding="utf-8") == texte
        print("Calendrier synchronisé." if ok else "Calendrier désynchronisé : relancer le générateur.")
        return 0 if ok else 1
    SORTIE.write_text(texte, encoding="utf-8")
    print(f"{len(LIGNES)} lignes écrites dans {SORTIE.relative_to(RACINE.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
