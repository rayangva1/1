# Checklist de conformité e-commerce (Suisse) — {{NOM_BOUTIQUE}}

> **À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION**
> Brouillon v0.1 du 4.10.2026, rédigé par l'agent legal-ops. Ce texte n'est pas un avis juridique.
> Usage : à cocher avant l'ouverture (gate G3, critère 3.6 « textes légaux validés ») puis à chaque changement de thème, d'application ou de moyen de paiement. Chaque ligne renvoie à un cas de la recette (`docs/07-ops/RECETTE_AVANT_OUVERTURE.md`).

## 1. Source BP [S11] et vérification

| Élément | Constat au 4.10.2026 |
|---|---|
| Source du BP | [S11] Portail PME — « Obligations légales : les lois suisses et européennes sur le e-commerce », https://www.kmu.admin.ch/fr/obligations-legales-les-lois-suisses-et-europeennes-sur-le-e-commerce |
| Lecture directe (WebFetch, 4.10.2026) | **Échec** : domaine `www.kmu.admin.ch` bloqué par le proxy de sortie de l'environnement de build. Même blocage pour fedlex.admin.ch, help.shopify.com et post.ch. |
| Vérification de repli (index de recherche, 4.10.2026) | Page S11 indexée (versions FR et EN). Contenu concordant avec le Guide e-commerce de la Confédération (« Obligations du vendeur », https://www.e-commerce-guide.admin.ch/ecommerce/fr/home/vertragsabschluss/pflichten.html) : selon l'art. 3 al. 1 let. s LCD, en vigueur depuis le 1.4.2012, quiconque offre des biens en ligne doit (1) indiquer clairement et complètement son identité et son adresse de contact, y compris l'adresse email ; (2) indiquer les différentes étapes techniques menant à la conclusion du contrat ; (3) fournir des outils techniques appropriés pour détecter et corriger les erreurs de saisie avant l'envoi de la commande ; (4) confirmer sans délai la commande par courrier électronique. Un formulaire de contact ne remplace pas l'adresse email. Cadre : LCD (RS 241) et OIP (RS 942.211). Pas de droit général de rétractation en Suisse ; garantie art. 197 ss CO. |
| Statut | **Indexée, page non ouverte.** À relire à la source par la propriétaire ou un agent disposant de l'accès (5 min) avant la validation finale. |
| Écart BP | Le BP §7 résume S11 par « identité, adresse et email de contact, correction de la commande et confirmation électronique » : il **omet** l'obligation (2), décrire les étapes techniques de la commande. Elle est couverte ici (L-02) et dans les CGV ch. 4.1. |

## 2. Checklist

Statut : ☐ à faire · ☑ vérifié (date, initiales) · ✗ non conforme (bloque l'ouverture si « Bloquant » = O).

| ID | Obligation | Base | Mise en œuvre | Où | Recette | Bloquant | Statut |
|---|---|---|---|---|---|---|---|
| L-01 | Identité et adresse de contact complètes, y compris l'email (pas seulement un formulaire) | LCD art. 3 al. 1 let. s ch. 1 [L1][L2][L3] | Raison sociale, forme, adresse, email, IDE | `MENTIONS_LEGALES.md`, pied de page, CGV ch. 1.2, emails | R-H01 | O | ☐ |
| L-02 | Étapes techniques menant à la conclusion du contrat | LCD art. 3 al. 1 let. s ch. 2 | Six étapes décrites | CGV ch. 4.1 ; FAQ « Comment commander ? » | R-H02 | O | ☐ |
| L-03 | Outils pour détecter et corriger les erreurs de saisie avant la commande | LCD art. 3 al. 1 let. s ch. 3 | Panier modifiable ; récapitulatif complet avant le bouton de paiement ; retour arrière sans perte | Panier et checkout | R-A04, R-A07 | O | ☐ |
| L-04 | Confirmation de la commande sans délai par email | LCD art. 3 al. 1 let. s ch. 4 | Email de confirmation automatique, exact (articles, statut, prix, frais, total) | Notification « confirmation de commande » | R-G01 | O | ☐ |
| L-05 | Prix effectivement à payer, en CHF, taxes et suppléments non optionnels inclus, à proximité du produit | OIP [L9] | Prix TTC sur la fiche, le panier, le checkout | Thème | R-A03, R-C01 | O | ☐ |
| L-06 | Frais de livraison transparents avant le paiement | OIP ; BP §7 | Page Livraison et retours ; frais affichés au panier | `LIVRAISON_RETOURS.md` | R-C04, R-C05 | O | ☐ |
| L-07 | Prix barré = prix réellement pratiqué auparavant par la boutique (auto-comparaison) | OIP art. 16 (règles assouplies, version 2025 selon l'index, à confirmer) [L9] | Prix barré uniquement depuis l'historique des prix publiés (`PriceHistory`) ; durée selon la règle confirmée par le juriste | Moteur + thème | R-C07 | O | ☐ |
| L-08 | Pas de TVA affichée si l'entité n'est pas inscrite au registre TVA | LTVA art. 27 [L10] | Champ `MENTION_TVA` (variante A ou B) | Fiche, checkout, emails, factures | R-C06 | O | ☐ |
| L-09 | Garantie pour les défauts non supprimée | CO art. 197 ss, 210 [L4] ; BP §7 [S11] | CGV ch. 9 | CGV, page retours | — (revue juriste) | O | ☐ |
| L-10 | Politique de retour volontaire claire (pas de droit légal de rétractation) | BP §7 [S11] | CGV ch. 10, tableau de la page retours | CGV, `LIVRAISON_RETOURS.md`, FAQ | R-J02 | O | ☐ |
| L-11 | CGV sans clause abusive au détriment du consommateur | LCD art. 8 [L3] | Relecture du juriste (notes J1 à J13 des CGV) | `CGV.md` | — (revue juriste) | O | ☐ |
| L-12 | CGV accessibles avant la commande et transmises avec la confirmation | CO (intégration des CGV) ; bonne pratique | Lien au checkout et dans l'email de confirmation | Checkout, email | R-A12, R-G01 | O | ☐ |
| L-13 | For : fors impératifs du consommateur réservés | CPC art. 32, 35 [L11] | CGV ch. 15.2 | CGV | — (revue juriste) | O | ☐ |
| L-14 | Emails publicitaires : consentement préalable (ou client existant, produits semblables), expéditeur exact, refus gratuit et simple | LCD art. 3 al. 1 let. o [L3][L12] | Double opt-in, case non pré-cochée, lien de désinscription, désinscription propagée | Formulaires, emailing, checkout | R-H04, R-H05 | O | ☐ |
| L-15 | Information lors de la collecte de données personnelles | LPD art. 19 [L5] | Déclaration de confidentialité, liens au checkout et au formulaire d'inscription | `CONFIDENTIALITE.md` | R-H06 | O | ☐ |
| L-16 | Droit d'accès : réponse gratuite sous 30 jours | LPD art. 25 ; OPDo [L6] | Procédure SAV-21 | `docs/07-ops/SOP_SAV_RETOURS.md` | R-H09 | N | ☐ |
| L-17 | Communication de données à l'étranger encadrée (pays adéquat ou garanties) | LPD art. 16-17 ; OPDo annexe 1 ; Swiss-US DPF effectif depuis le 15.9.2024 pour les entreprises certifiées [L7] | Tableau des prestataires rempli à partir des contrats | `CONFIDENTIALITE.md` ch. 4-5 | — (revue juriste) | O | ☐ |
| L-18 | Annonce des violations de la sécurité des données au PFPDT | LPD art. 24 [L5] | Procédure INC-10 | `docs/07-ops/SOP_INCIDENTS.md` | R-K01 (procédure) | N | ☐ |
| L-19 | Cookies : information sur l'usage et la finalité, possibilité de refuser | LTC art. 45c [L8] | Bandeau « Accepter / Refuser », page cookies, relevé réel | `COOKIES.md` | R-H03 | O | ☐ |
| L-20 | Pas de confusion avec le titulaire de la marque ; non-affiliation | LPM ; LCD art. 3 al. 1 let. d [L18] ; BP §8 | Mentions courte et complète ; règles d'usage | `USAGE_MARQUES.md` | R-H07 | O | ☐ |
| L-21 | Avertissements de sécurité (âge minimum…) visibles avant l'achat, y compris en ligne | OSJo [L13] (langues exigées hors Suisse romande : **non vérifié**) | Avertissements repris sur chaque fiche | Fiches produit | R-H08 | O | ☐ |
| L-22 | Livraison en Suisse uniquement | BP (périmètre) | Zone d'expédition Suisse seule au checkout | Paramètres d'expédition | R-A08 | O | ☐ |
| L-23 | Aucune précommande encaissée sans allocation ferme | BP §1, §3, §5 | Quota moteur ; checklist d'ouverture | `PRECOMMANDES.md` §2 | R-D01, R-D02 | O | ☐ |
| L-24 | Aucun coût, marge, prix B2B ni donnée personnelle dans le HTML public | BP §6 ; SPEC §0.2 | Filtre de publication + test | `engine/pokeshop/publish.py` (agent integrations) | R-I01 | O | ☐ |
| L-25 | Aucune promesse de carte rare ni de valeur financière future | BP §7 | CGV ch. 2.3-2.4 ; contrôle QA | Fiches, contenus | R-A03 | O | ☐ |

## 3. Règle d'usage

- Une ligne **Bloquant = O** non cochée empêche le GO d'ouverture (gate G3, critère 3.6).
- Toute modification du checkout, d'une application, d'un moyen de paiement ou d'un pixel publicitaire rouvre les lignes concernées.

## Validation humaine requise

- [ ] Propriétaire ou agent avec accès : relire la page S11 à la source et dater la lecture (5 min).
- [ ] Juriste : valider les lignes marquées « revue juriste » (L-09, L-11, L-13, L-17) et la règle des prix barrés (L-07).
- [ ] Juriste : trancher l'exigence de langue des avertissements pour les ventes hors Suisse romande (L-21).
- [ ] Propriétaire : signer la checklist complétée avant l'ouverture (gate G3).
