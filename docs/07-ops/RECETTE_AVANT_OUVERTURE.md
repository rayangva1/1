# Recette avant ouverture — cahier de tests

> Version v0.1 du 4.10.2026, rédigée par l'agent legal-ops. Exécutée par l'agent 12 QA (tests numériques) et la propriétaire (paiements réels, colis, retour) : BL-098, BL-099, BL-105.
> Sources : BP §7 « Recette avant ouverture » (« sur mobile et ordinateur : recherche → produit → panier → paiement → confirmation → préparation → suivi → remboursement. Vérifier le stock simultané, un panier avec remise, le port gratuit, une rupture pendant paiement et une commande mixte. Les pages de confirmation et les emails doivent afficher exactement ce qui a été acheté » ; « tester paiements réussis, refusés, doublons, remboursements et délais de versement ») ; §13 « Tests obligatoires du moteur » ; `docs/00-pilotage/GATES_GO_NO_GO.md` (G3, critères 3.4, 3.6, 3.7) ; `docs/04-legal/CHECKLIST_LCD_ECOMMERCE.md`.
> **Aucun résultat n'est pré-rempli.** Les colonnes « Résultat obtenu », « Statut » et « Preuve » sont remplies pendant la campagne, jamais avant.

## 1. Règles de la campagne

| Règle | Détail |
|---|---|
| Version figée | Noter avant de commencer : version du thème, applications installées, `rules_version` du moteur, date. Toute modification pendant la campagne oblige à rejouer les cas touchés. |
| Environnement | Boutique de test en mode test du prestataire de paiement pour les cas sans argent réel ; **paiements réels** de petits montants (carte et TWINT de la propriétaire, puis remboursés) pour R-E03, R-E06 à R-E08 et R-F01 à R-F03. Moteur et n8n en mode simulation, sauf indication. |
| Appareils | Mobile : un iPhone (Safari) et un Android (Chrome). Ordinateur : Chrome et un second navigateur (Firefox ou Safari). La colonne « Appareil » indique le minimum. |
| Données | Produits, commandes et clients **FICTIFS** (préfixe `FICTIF_`), sauf les paiements réels de la propriétaire. GTIN de test commençant par `200` (SPEC §0.7). |
| Statut | OK · KO · NA (non applicable, motif obligatoire). |
| Preuve | Capture, vidéo d'écran, numéro de commande de test, extrait de journal : chemin ou lien. |
| Critère de sortie | **100 % des cas bloquants OK dans une même campagne**, 0 erreur critique au sens de `GATES_GO_NO_GO.md` §1, et une date de correction pour chaque KO non bloquant. |
| Après une correction | Rejouer le cas KO **et** les cas de la même section. |

En-tête de campagne (à recopier) :

```
Campagne n° __  du ___/___/______   Thème v____  Apps : ____________  rules_version : ____________
Testeurs : agent 12 QA + propriétaire   Résultat : ___ cas bloquants OK / ___   Erreurs critiques : ___
```

## 2. Cas de test

### A. Parcours complet (mobile et ordinateur)

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-A01 | O | Mobile | 10 fiches FICTIF publiées | Rechercher un nom d'extension ; filtrer par format, budget, FR, stock local, précommande | Résultats pertinents ; filtres cohérents avec les fiches ; aucun produit indisponible présenté comme en stock | | | |
| R-A02 | O | Ordinateur | idem | Même parcours que R-A01 | idem | | | |
| R-A03 | O | Mobile + ordinateur | Fiche en stock local et fiche en précommande | Ouvrir chaque fiche | Titre « format + extension + langue » ; prix en CHF ; lien vers les frais de livraison ; quantité autorisée ; état du stock explicite ; avertissement d'âge ; mention du contenu aléatoire ; aucune promesse de rareté ou de valeur | | | |
| R-A04 | O | Mobile | Panier avec 2 articles | Modifier une quantité, supprimer un article, dépasser la limite par foyer | Totaux recalculés ; la limite bloque l'ajout au-delà de {{LIMITE_PAR_CLIENT}} avec un message clair | | | |
| R-A05 | O | Mobile | Paiement carte en mode test | Recherche → fiche → panier → paiement carte → confirmation | Commande créée ; page de confirmation identique au panier (articles, prix, frais, total) | | | |
| R-A06 | O | Ordinateur | TWINT actif | Même parcours, paiement TWINT (code QR scanné avec un téléphone) | Commande créée ; confirmation exacte | | | |
| R-A07 | O | Mobile + ordinateur | Au récapitulatif du checkout | Revenir en arrière, corriger l'adresse puis une quantité, revenir au récapitulatif | Corrections prises en compte sans perte du panier (LCD art. 3 al. 1 let. s ch. 3) | | | |
| R-A08 | O | Ordinateur | — | Saisir une adresse en France, puis au Liechtenstein | Pays non proposés ou commande impossible ; message clair « Suisse uniquement » | | | |
| R-A09 | O | Ordinateur | Commande R-A05 | Suivre la commande jusqu'au bon de préparation, à l'étiquette (mode test) et au statut « expédiée » | Bon exact ; numéro de suivi transmis ; statut visible par le client | | | |
| R-A10 | O | Ordinateur | Commande payée | Rembourser intégralement depuis l'administration | Email de remboursement exact ; réservation libérée ; mouvement de stock correct | | | |
| R-A11 | O | Mobile + ordinateur | — | Ouvrir depuis le pied de page : CGV, livraison et retours, précommandes, confidentialité, cookies, mentions légales, FAQ, contact | Toutes les pages existent, à jour, datées ; aucun champ `{{…}}` visible | | | |
| R-A12 | O | Mobile | Checkout | Repérer le lien vers les CGV et la confidentialité avant le bouton de paiement | Liens présents et fonctionnels avant l'engagement de payer | | | |

### B. Stock

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-B01 | O | 2 appareils | Référence FICTIF avec **1** unité vendable | Deux testeurs paient la dernière unité en même temps | Une seule commande payée et réservée ; l'autre voit la rupture ; aucune survente (BP §13) | | | |
| R-B02 | O | 2 appareils | 1 unité ; testeur 1 sur la page de paiement | Testeur 2 achète l'unité ; testeur 1 valide ensuite son paiement | Testeur 1 : paiement refusé ou commande non finalisée ; si un paiement est capturé sans stock : remboursement automatique, email d'excuse, incident INC-06 ; jamais d'expédition promise | | | |
| R-B03 | O | Ordinateur | Stock local 0, stock fournisseur FICTIF disponible | Ouvrir la fiche | « Indisponible » + alerte réassort ; le stock fournisseur n'est jamais affiché comme expédiable | | | |
| R-B04 | O | — (moteur) | Offre fournisseur datée de plus de 24 h ; stock local 2 | Lancer la synchronisation | Promesse de précommande et achats bloqués ; les 2 unités locales restent vendables | | | |
| R-B05 | O | Ordinateur | Commande non payée ou annulée | Abandonner le paiement ; annuler une commande payée | Réservation libérée ; stock vendable revenu à sa valeur | | | |
| R-B06 | O | — (moteur) | 3 unités, 1 marquée endommagée | Mouvement `MARK_DAMAGED` | Stock vendable = 2 sur le site | | | |
| R-B07 | N | — (moteur) | Stock de sécurité = 1 | Vendre jusqu'à la dernière unité vendable | La dernière unité physique (sécurité) n'est pas proposée | | | |

### C. Prix, remises, port, TVA

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-C01 | O | Ordinateur | 10 fiches avec décision de prix `OK` | Comparer prix du site et prix validé du moteur | Écart 0 sur les 10 fiches | | | |
| R-C02 | O | Mobile | Code de remise valide | Panier avec remise | Total exact ; contribution du panier (`basket_contribution`) au-dessus des planchers | | | |
| R-C03 | O | — (moteur) | Référence à 16 % de contribution | Créer un code de −10 % sur cette référence | Création refusée : le panier passerait sous 12 % ou 8 CHF (stop-loss produit) | | | |
| R-C04 | O | Mobile | Panier au-dessus du seuil de livraison offerte | Aller au checkout | Livraison à 0 CHF ; contribution recalculée avec le coût réel du port | | | |
| R-C05 | O | Mobile | Panier juste sous le seuil | Aller au checkout | Frais de livraison {{FRAIS_LIVRAISON}} affichés avant le paiement | | | |
| R-C06 | O | Ordinateur | Statut TVA décidé | Lire fiche, panier, confirmation, email, facture | Mention conforme à `MENTION_TVA` ; **aucune TVA** affichée si l'entité n'est pas assujettie | | | |
| R-C07 | O | Ordinateur | Fiche avec prix barré | Vérifier l'historique des prix publiés | Le prix barré a réellement été pratiqué auparavant (OIP) ; sinon pas de prix barré | | | |
| R-C08 | O | — (moteur) | Nouveau prix +7 % sur 24 h | Synchroniser | Statut `REVIEW` ; pas de publication sans validation (BP §5) | | | |
| R-C09 | N | — (moteur) | Cas BP 208,79 CHF | Calculer | Prix arrondi 209,90 CHF puis marge revérifiée | | | |

### D. Précommandes et commandes mixtes

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-D01 | O | Ordinateur | Allocation ferme FICTIF de 10, réserve 1 | Vendre 9 précommandes | Quota = 10 − 9 − 1 = 0 ; badge « Précommande » retiré ; aucune 10e vente | | | |
| R-D02 | O | Ordinateur | Référence annoncée sans allocation ferme | Ouvrir la fiche | Aucun bouton de précommande ; aucun encaissement possible | | | |
| R-D03 | O | Mobile | Panier stock local + précommande | Commander | Email : statut par ligne ; port facturé une fois ; 2 expéditions prévues ; le moteur compte 2 coûts logistiques | | | |
| R-D04 | O | — | Précommande payée | Simuler un report de 40 jours | Email SAV-M06 avec option d'annulation ; date mise à jour sur la fiche | | | |
| R-D05 | O | — | 5 précommandes, allocation réduite à 3 | Simuler la réduction | Les 3 premières par ordre de paiement sont servies ; 2 annulées, remboursées, email SAV-M07 | | | |
| R-D06 | O | — | Précommande dans le délai d'annulation | Annuler | Remboursement intégral ; unité rendue au quota | | | |
| R-D07 | N | Mobile | Nouveauté en précommande | Commander au-delà de la limite par foyer | Limite appliquée comme en R-A04 | | | |

### E. Paiements

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-E01 | O | Mobile | Carte de test avec 3-D Secure | Payer | Authentification affichée ; commande créée | | | |
| R-E02 | O | Mobile | Carte de test refusée | Payer | Message clair ; **aucune** commande ni réservation | | | |
| R-E03 | O | Mobile | TWINT réel, petit montant | Payer | Commande créée ; montant exact débité | | | |
| R-E04 | O | Mobile | TWINT | Abandonner ou laisser expirer | Aucune commande ni réservation | | | |
| R-E05 | O | Mobile | Réseau lent | Double-cliquer sur le bouton de paiement ; recharger la page | Une seule commande ; si un double débit apparaît : détection, remboursement du doublon, alerte | | | |
| R-E06 | O | Ordinateur | Commande carte réelle | Remboursement total | Montant exact recrédité ; email exact | | | |
| R-E07 | O | Ordinateur | Commande de 2 lignes | Remboursement partiel d'une ligne | Montant exact ; stock de la ligne traité | | | |
| R-E08 | O | Ordinateur | Commande TWINT réelle | Remboursement | Montant recrédité sur le compte TWINT | | | |
| R-E09 | O | Ordinateur | Commande marquée à risque (test) | Lancer la préparation | Commande retenue, aucune étiquette ; escalade à la propriétaire (SAV-18) | | | |

### F. Versements et rapprochement

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-F01 | O | — | Paiements réels R-E03, R-E06 à R-E08 | Attendre le versement du PSP sur l'IBAN professionnel | Versement reçu ; délai réel en jours noté dans la trésorerie 13 semaines | | | |
| R-F02 | O | — | Versement reçu | Rapprocher commandes − remboursements − frais = versement | Écart 0 ou expliqué (BL-166) | | | |
| R-F03 | N | — | Relevé du PSP | Comparer les frais réels aux hypothèses r = 2,5 % et b = 0,30 CHF (BP §4) | Écart transmis à l'agent 05 ; paramètres mis à jour par une nouvelle version des règles si besoin | | | |

### G. Emails et notifications

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-G01 | O | Mobile | Commande R-A05 | Lire l'email de confirmation | Reçu immédiatement ; articles, statut par ligne, prix, frais, total, mention TVA, lien CGV, identité et email du vendeur exacts ; aucune donnée interne | | | |
| R-G02 | O | Mobile | Commande expédiée | Lire l'email d'expédition | Numéro et lien de suivi ; articles réellement expédiés (partiel si commande mixte) | | | |
| R-G03 | O | Mobile | Commande annulée | Lire l'email | Motif et montant remboursé exacts | | | |
| R-G04 | O | Mobile | Remboursement partiel | Lire l'email | Montant exact | | | |
| R-G05 | N | Mobile | Report de précommande | Lire l'email | Conforme au modèle SAV-M06 | | | |
| R-G06 | O | Mobile + ordinateur | — | Ouvrir les emails dans Gmail, Outlook et Apple Mail | Lisibles ; logo affiché (PNG, pas de SVG) ; liens fonctionnels | | | |
| R-G07 | O | — | — | Répondre à un email transactionnel | La réponse arrive à {{EMAIL_SUPPORT}} ; l'expéditeur est clairement identifié | | | |

### H. Conformité

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-H01 | O | Mobile + ordinateur | Mentions légales publiées | Lire la page et le pied de page | Raison sociale, adresse, email (pas seulement un formulaire), IDE (LCD art. 3 al. 1 let. s ch. 1) | | | |
| R-H02 | O | Ordinateur | CGV publiées | Lire CGV ch. 4.1 et la FAQ | Étapes techniques de la commande décrites (ch. 2) et conformes au parcours réel | | | |
| R-H03 | O | Ordinateur | Navigation privée | Relevé des cookies avant choix, après « Refuser », après « Accepter » (`docs/04-legal/COOKIES.md`) | Avant choix et après refus : cookies nécessaires seulement ; refus aussi simple qu'accepter ; tableau public complété | | | |
| R-H04 | O | Mobile | Formulaire d'alerte | S'inscrire | Case non pré-cochée ; email de confirmation (double opt-in) ; preuve de consentement enregistrée (date, texte) | | | |
| R-H05 | O | Mobile | Inscrit confirmé, aussi abonné marketing dans Shopify | Cliquer « se désinscrire » dans un email | Désinscription en un clic, propagée à **tous** les outils (emailing et statut marketing Shopify) ; aucun email promotionnel ensuite (BL-103) | | | |
| R-H06 | O | Mobile | — | Repérer le lien vers la confidentialité au checkout et sur le formulaire d'inscription | Lien présent et fonctionnel | | | |
| R-H07 | O | Mobile + ordinateur | — | Parcourir le site, les emails et un colis test | Mention de non-affiliation présente ; aucun logo ni personnage hors photos réelles des produits (`USAGE_MARQUES.md` §5) | | | |
| R-H08 | O | Mobile | Fiches publiées | Lire chaque fiche | Avertissements de sécurité (âge) visibles avant l'achat | | | |
| R-H09 | N | — | Client test | Faire une demande d'accès (SAV-21) | Export complet préparé ; réponse possible en moins de 30 jours | | | |

### I. Sécurité et confidentialité

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-I01 | O | Ordinateur | Fiches publiées | Lire le code source des pages, le JSON public des produits, le sitemap et les métadonnées ; lancer le test de fuite de `publish.py` | Aucun coût, marge, prix d'achat, nom de fournisseur ni donnée personnelle | | | |
| R-I02 | O | — | Comptes d'administration ; jetons et secrets de B21-B22 | Vérifier les comptes et les droits ; appeler une route d'écriture de l'API avec le jeton commun, avec un jeton de rôle non admis, puis avec le jeton propriétaire seul ; appeler chaque passerelle n8n (03, 04, 06, 08) avec le secret d'un autre agent | Double authentification active ; chaque compte limité à son rôle ; jeton commun et rôle non admis : 403, jeton propriétaire seul : accepté (`docs/08-agents/MATRICE_API.md`) ; passerelle avec le secret d'un autre agent : 403 ; administration de n8n par la propriétaire seule | | | |
| R-I03 | O | — | Moteur et n8n | Lancer une synchronisation sans drapeau d'écriture | Aucune écriture réelle (simulation par défaut, SPEC §0.6) | | | |
| R-I04 | O | Ordinateur | Sauvegarde du jour du service `db-backup` ; copie hors machine chiffrée avec la clé publique age de la propriétaire (A12) ; sa clé privée | Restaurer la base sur un environnement de test (`db/backup.sh verifier`) ; lancer `db/backup.sh etat` ; relire la copie chiffrée hors de la machine avec la clé privée (commande de contrôle `age -d` de `db/README.md`) | `db/backup.sh etat` répond code 0 (restauration vérifiée depuis moins de 36 h) ; restauration complète, durée notée (BP §6) ; copie chiffrée hors de la machine datée du mois | | | |

### J. Opérations physiques

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-J01 | O | — | Compte transporteur actif | Envoyer un colis test réel (A02, BL-105) | Étiquette, dépôt, suivi et livraison OK ; coût réel noté | | | |
| R-J02 | O | — | Colis test reçu | Faire un retour volontaire test (SAV-13) | Instructions, réception, contrôle du scellé, remboursement exact | | | |
| R-J03 | O | — | Commande test | Imprimer le bon de préparation | Articles exacts ; option cadeau sans prix | | | |
| R-J04 | O | — | Bon de préparation | Scanner un mauvais GTIN | Préparation bloquée | | | |
| R-J05 | O | — | Lot FICTIF ; facture FICTIVE | Réception à blanc (`SOP_RECEPTION_STOCK.md`) : déclaration E2 par l'agent 11 (son jeton, ou la passerelle 06 avec **son** secret ; le secret d'un autre agent : 403), facture validée puis enregistrée par le workflow 03, coût `RECEIPT` de l'agent 05 | Lot de coût saisi ; stock vendable correct ; coût à ± 2 % de la ligne de facture accepté, coût hors ± 2 % (prix du carton saisi comme unité) refusé (403) puis inscrit par la propriétaire ; même réception valorisée deux fois : 409 ; temps noté | | | |

### K. Incidents et stop-loss

| ID | Bloquant | Appareil | Préconditions | Étapes | Résultat attendu | Résultat obtenu | Statut | Preuve |
|---|---|---|---|---|---|---|---|---|
| R-K01 | O | — | Import FICTIF avec un prix ×10 | Lancer l'import | Référence en quarantaine ; notification avec cause et action proposée (INC-01) | | | |
| R-K02 | O | — | Flux fournisseur coupé | Simuler la panne | Workflow suspendu ; stock local inchangé et vendable (INC-03) | | | |
| R-K03 | O | — | Photo simulée dont la perte de valeur nette atteint 20 % du capital engagé de référence (840 CHF avec le point zéro de 4 200 CHF) | Déclencher le stop-loss global | Achats, publicité, prix et nouvelles fiches gelés ; niveau 1 ; expéditions des commandes payées et remboursements toujours possibles ; réarmement réservé à la propriétaire | | | |
| R-K04 | O | — | Niveau d'autonomie 2 | Simuler un incident S1 | Retour automatique au niveau 1 ; notification immédiate | | | |

## 3. Synthèse à joindre au gate G3

| Section | Cas bloquants | OK | KO | NA |
|---|---|---|---|---|
| A. Parcours | 12 | | | |
| B. Stock | 6 | | | |
| C. Prix | 8 | | | |
| D. Précommandes | 6 | | | |
| E. Paiements | 9 | | | |
| F. Versements | 2 | | | |
| G. Emails | 6 | | | |
| H. Conformité | 8 | | | |
| I. Sécurité | 4 | | | |
| J. Opérations | 5 | | | |
| K. Incidents | 4 | | | |
| **Total** | **70** | | | |

## Validation humaine requise

- [ ] Propriétaire : réaliser les cas avec argent réel (R-E03, R-E06 à R-E08, R-F01) et les cas physiques (R-J01, R-J02, R-J05).
- [ ] Propriétaire : signer la synthèse (§3) avant le GO d'achat du stock (gate G3) et l'activation du niveau 2 (BL-116) ; la recette ne suffit pas seule : le niveau 2 exige aussi la revue adverse de sécurité relancée et sans critical/high ouvert (C31, BL-200, `docs/00-pilotage/REVUE_SECURITE.md` §5).
- [ ] Agent 12 QA : fixer la date de la campagne et rejouer la recette après tout changement de thème, d'application ou de moyen de paiement.
