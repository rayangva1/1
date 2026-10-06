# Pré-drop — qui fait quoi (réservation garantie)

> Décision de la propriétaire du 6.10.2026 : avant la réception du stock, une **réservation garantie** à supplément (« pré-drop »). Le supplément paie la **garantie** d'être servi en premier et expédié dès réception, **pas le produit** ; **aucun remboursement de la différence** si des unités restent au drop.
> Sources : `docs/SPEC.md` §2.11 ; `engine/pokeshop/predrop.py` ; matrice `docs/08-agents/MATRICE_API.md` (version `2026-10-06.predrop-annulation`) ; conditions `docs/04-legal/PRECOMMANDES.md` (partie « Pré-drop », §2.5) et CGV ch. 7.7 à 7.12 ; contenus `docs/06-contenu/PLAN_JOUR_DE_DROP.md` et emails 15 à 19 ; actes de la propriétaire C32, C33, C34 (`docs/00-pilotage/INTERVENTIONS_HUMAINES.md`).
> Principe : **fermé par défaut** et **aucune valeur décisive fournie par son bénéficiaire**. L'agent qui ouvre un pré-drop ne pose ni l'allocation ferme, ni la demande, ni la référence marché ; aucun agent n'écrit de prix, de quota, de montant ni de statut : le moteur les calcule depuis ses registres.

## 1. Le pré-drop en une phrase

Paramètres signés par la propriétaire ; allocation ferme validée par elle ; demande agrégée des inscrits ; deux prix calculés par le moteur (drop = `decide_price`, pré-drop ≤ drop × 1,10 et ≤ marché, marge revérifiée) ; fiche « Réservation garantie » publiée par le moteur ; réservations payées jamais perdues ; réservations servies en premier, dans l'ordre de paiement ; l'argent encaissé reste une **dette** jusqu'à l'expédition ; le chiffre d'affaires est reconnu à l'expédition ; un statut (« Réservations ouvertes / fermées ») et une date, jamais un minuteur ni un nombre d'unités.

## 2. Étapes et responsables

| # | Étape | Qui fait | Route ou outil | Qui valide | Interdit |
|---|---|---|---|---|---|
| 1 | Signer les paramètres (`config/predrop.v1.yaml`) | Propriétaire | `python -m pokeshop.predrop fingerprint`, empreinte `POKESHOP_PREDROP_FINGERPRINT` au coffre | — (C32) | Un agent qui modifie le fichier désactive le pré-drop : il propose une nouvelle version, la propriétaire signe |
| 2 | Extraire la confirmation écrite du fournisseur | Agent 02 `sourcing` | Passerelle 03 « allocations » (secret de l'agent 02, aucun jeton d'API) | Propriétaire (formulaire 03, 72 h, C33) | Jamais une allocation orale, « prévisionnelle » ou sans prix (§2.1 de `docs/04-legal/PRECOMMANDES.md`) |
| 3 | Enregistrer l'allocation ferme, puis chaque réduction | Workflow 03 (`n8n-03-factures`) après le formulaire ; propriétaire si le fournisseur n'est pas connu du moteur | `POST /predrop/allocations`, `POST /predrop/allocations/{product_key}/reduce` | Propriétaire (C33) | Aucun agent ne déclare une allocation ; une baisse passe par la réduction |
| 4 | Compter la demande (inscrits consentants intéressés) | Workflow 06 (`n8n-06-marketing`) | `POST /predrop/demand` (un nombre, une date, une source) | — | Aucune donnée personnelle ; jamais un compte posé par les agents 09 ou 10 |
| 5 | Valider la fiche normale | Agent 04 `catalogue` prépare | `POST /catalog/approvals` | Propriétaire (C30) | Fiche non validée : pas de pré-drop |
| 6 | Lire l'éligibilité | Agent 05 (et l'agent 01, en lecture) | `GET /predrop/eligibility/{product_key}` | — | Aucune condition déclarée par le demandeur : toutes sont évaluées sur les registres du moteur |
| 7 | Ouvrir le pré-drop | Agent 05 `finance-pricing` (jeton `finance-pricing`) ; la propriétaire avec la référence marché | `POST /predrop/open` (`market_ref_chf` : propriétaire seule) | Propriétaire si référence marché inconnue ou prix drop REVIEW (`POST /predrop/{predrop_id}/approve`, C33) | Ouvrir sans les conditions (409) ; deux pré-drops sur la même allocation |
| 8 | Publier la fiche « Réservation garantie » | Workflow 01 (`n8n-01-sync`) ; agent 07 `site-integrations` | `POST /predrop/{predrop_id}/publish` (simulation par défaut ; écriture réelle : niveau 2 pour une mise à jour, 3 pour une création) | — | Aucun prix, quota ni texte fourni par l'appelant (422) |
| 9 | Annoncer (emails 16 et 17, stories) | Workflow 06 (emails) ; agent 09 `communication` (stories du `docs/06-contenu/PLAN_JOUR_DE_DROP.md`) | Outil d'emailing (nœuds désactivés jusqu'au niveau 3) | Propriétaire (textes, BL-208) | Minuteur, heure de fermeture, « plus que N », prix en dur, coût, marge |
| 10 | Enregistrer les réservations payées (email 15) | Workflow 02 (`n8n-02-commandes`) | `POST /predrop/reservations` (identifiant client haché) | — | Refuser une commande payée : hors règles, elle est non servie et remboursée intégralement |
| 11 | Fermer par précaution | Agents 05 et 12 (et l'agent 01 quand son jeton est émis) ; workflow 03 dès qu'une réduction est annoncée | `POST /predrop/{predrop_id}/close` | — | — (acte protecteur) |
| 12 | Annuler une réservation à la demande **écrite** du client | Agent 11 `operations-sav` (SAV-27) | `POST /predrop/reservations/{order_id}/cancel` (motif, référence de la demande) | Propriétaire : remboursement en un clic aux niveaux 1 et 2 (C34) | Annuler sans demande écrite ; annulation libre à partir de la date du drop (refusée par le moteur) |
| 13 | Rembourser (réservation non servie, réduction, annulation) | Moteur (prépare) ; workflow 02 (exécute, relève, email 18) | `POST /predrop/refunds/{refund_id}/approve` (propriétaire), `POST /predrop/refunds/{refund_id}/executed` (02) | Propriétaire aux niveaux 1 et 2 (C34) ; le moteur dès le niveau 3 | Rembourser deux fois ; recalculer un montant |
| 14 | Réceptionner et servir en premier (email 19 à l'expédition) | Propriétaire (physique, A03) ; agent 11 (déclaration, étape E4 bis de `docs/07-ops/SOP_RECEPTION_STOCK.md`) | `POST /stock/receive`, `GET /predrop/reservations` ; réduction si reçu moins | — | Mettre en vente au prix du drop avant d'avoir préparé les réservations |
| 15 | Suivre la dette et l'étoile polaire | Agent 05 | Photo du stop-loss (dette **dérivée**), `GET /northstar` (`predrop_collected_not_recognized_chf`) | — | Déclarer les réservations pré-drop dans `preorders_collected_chf` (elles sont dérivées du registre) |
| 16 | Contrôler | Agent 12 `qa-conformite` | `python docs/04-legal/outils/verifier_legal_ops.py` (`check_predrop_alignment`), `python docs/06-contenu/outils/verifier_contenu.py` (pré-drop), `GET /predrop/offers` (liste blanche) | — | Écrire un fichier ; laisser publier une fausse urgence (fermer le pré-drop et escalader) |

Les agents 03, 06, 08 et 10 n'ont aucun acte propre au pré-drop : l'agent 08 reprend les textes de la fiche validée, l'agent 06 fournit les badges « Réservation garantie » et « Drop le JJ.MM » de la DA, l'agent 10 ne lance aucune publicité qui cite une quantité, une heure ou un minuteur (une campagne sur un produit en pré-drop suit le mandat et le stop-loss pub comme toute campagne).

## 3. Règles communes

1. **Fermé par défaut** : paramètres non signés, journal illisible, gel, stop-loss non évaluable ou quarantaine ⇒ réservations fermées, fiche de réservation retirée ; une commande payée n'est jamais perdue (non servie, remboursement intégral préparé).
2. **Deux phrases, mot pour mot** : « Le supplément pré-drop paie la garantie d'être servi en premier et expédié dès réception du stock, pas le produit. » et « Aucun remboursement de la différence avec le prix du drop, même s'il reste des unités au drop. » (moteur, fiche, page Précommandes, CGV, FAQ, emails 15 à 17, plan du jour de drop).
3. **Aucun coût, aucune marge, aucun quota publiés** : l'offre publique est une liste blanche (`PUBLIC_OFFER_FIELDS`) ; la lecture interne (quotas) ne sort jamais du dépôt ni d'un rapport public.
4. **Montants en `Decimal`**, simulation par défaut, aucune écriture vers un service tiers sans la porte de gouvernance et le niveau requis.
5. **Données personnelles** : le moteur ne reçoit qu'une empreinte de l'identifiant client et des comptes agrégés ; jamais un email ni un nom.

## 4. Escalade

| Situation | Qui | Vers |
|---|---|---|
| Confirmation fournisseur ambiguë (quantité, prix, langue, date) | Agent 02 | Propriétaire (formulaire 03 : refus ou demande de précision) |
| Réduction d'allocation annoncée ou constatée | Workflow 03 ou agent 11 | Propriétaire (validation de la réduction, puis des remboursements) |
| Plus de 5 réservations remboursées sur un même pré-drop | Agent 11 | Propriétaire (information, comme les précommandes) |
| Contestation de l'absence de remboursement de la différence | Agent 11 | Propriétaire (réexamen par une personne) ; juriste si litige |
| Texte public non conforme (urgence, chiffre, prix en dur) | Agent 12 | Fermeture du pré-drop (`POST /predrop/{predrop_id}/close`) puis agent 01 et propriétaire |

## Validation humaine requise

- [ ] Propriétaire : valider ce partage des rôles avant le premier pré-drop, en particulier l'ouverture par l'agent 05 (étape 7) et l'annulation à la demande du client par l'agent 11 (étape 12).
- [ ] Propriétaire : faire les actes C32 (signature), C33 (allocations, référence marché) et C34 (remboursements) dans les délais.
- [ ] Agent 12 : vérifier, à chaque pré-drop, que les contrôles de l'étape 16 sont verts.
