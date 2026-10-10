# SOP — Préparation et expédition des colis

> SOP v0.1 du 4.10.2026, rédigée par l'agent legal-ops. À tester à blanc avec le colis test (BL-105, A02) avant l'ouverture.
> Sources : BP §12 workflow commande → livraison (« paiement confirmé → réservation de stock → contrôle de doublon et anomalies → bon de préparation → étiquette et tâche colis → scan du produit et confirmation → remise au transporteur → suivi client → rapprochement paiement/facture » ; « un robot logiciel ne prépare pas un colis ») ; §7 (emails exacts) ; §8 (packaging : sticker, carte merci, repère de commande) ; BACKLOG BL-120 ; INTERVENTIONS A07.
> Fichiers DA du packaging : `docs/05-da/packaging/` (sticker Ø 50 mm, carte A6, repère 70 × 37 mm).

## 1. En bref

| | |
|---|---|
| Qui | **Agent 11** prépare la liste, les bons et les étiquettes. **Propriétaire** (ou prestataire logistique) : picking, scan, emballage, dépôt. |
| Quand | Les jours de dépôt : {{JOURS_EXPEDITION}}. Engagement client : remise au transporteur sous {{DELAI_EXPEDITION}} après le paiement. |
| Durée | 10 à 15 min par colis (hypothèse INTERVENTIONS A07, **à mesurer** : BL-171). |
| Matériel | Cartons à la taille des produits, calage papier, ruban, stickers de fermeture, cartes merci, repères de commande, imprimante d'étiquettes ou A4, smartphone pour scanner, balance de cuisine ou postale. |

## 2. Ce que l'agent 11 prépare avant chaque session

- [ ] Liste des commandes **payées** à expédier, avec réservation de stock confirmée (statut `RESERVED`).
- [ ] Commandes **exclues** de la liste et pourquoi : soupçon de fraude, dépassement de la limite par foyer, adresse incomplète, doublon, paiement en litige (SOP SAV, cas SAV-17 et SAV-18).
- [ ] Un **bon de préparation** par commande : numéro, articles (référence, GTIN, format, extension, langue, quantité), emplacement, statut de chaque ligne (stock local / précommande), option « cadeau » (bon sans prix).
- [ ] Les **étiquettes transporteur** générées (service avec suivi ; envoi contre signature ou assuré au-delà de {{SEUIL_ENVOI_SIGNATURE}}).
- [ ] Le **repère de commande** pré-rempli (numéro de commande).

## 3. Étapes par colis (propriétaire)

- [ ] P1. Prendre le bon de préparation et le repère de la commande.
- [ ] P2. **Picking** : prendre chaque article à son emplacement, la plus ancienne réception d'abord.
- [ ] P3. **Scan** : scanner le code-barres de chaque article. Le GTIN doit correspondre à la ligne du bon. Pas de code-barres lisible : vérifier visuellement référence, langue et extension, et le noter.
- [ ] P4. **Contrôle visuel** : langue FR, extension, format, quantité, film et scellé intacts, pas d'enfoncement. Un article abîmé ne part pas : le remplacer par une autre unité ou signaler à l'agent 11 (mouvement `MARK_DAMAGED`).
- [ ] P5. Cocher les cases du repère de commande (« langue FR », « scellé », « quantité »).
- [ ] P6. **Photo du contenu** posé dans le carton ouvert, repère de commande visible, **sans l'étiquette d'adresse** (preuve SAV, conservée {{DUREE_CONSERVATION_PHOTOS_COLIS}}).
- [ ] P7. **Emballage** selon le tableau §4 : calage sur les six faces, aucun jeu quand on secoue le carton.
- [ ] P8. Glisser la carte merci et, si demandé, le bon sans prix (cadeau).
- [ ] P9. Fermer, poser le sticker de fermeture sur la jonction (signale une ouverture).
- [ ] P10. Coller l'étiquette transporteur bien à plat, sur la plus grande face, sans ruban sur le code-barres.
- [ ] P11. Peser si le tarif dépend du poids ; noter le poids sur le bon si l'agent l'a demandé.
- [ ] P12. Marquer la commande « préparée » (scan ou case dans l'outil) : le système envoie alors le numéro de suivi par email au client.

## 4. Emballage par type de produit

| Produit | Emballage | Calage | À éviter |
|---|---|---|---|
| Booster seul, sleeves, petits accessoires | Enveloppe rigide ou petit carton | Papier autour du produit | Enveloppe souple seule (pliage) |
| Coffret Dresseur d'élite (ETB), coffret | Carton à la taille, environ 2 cm de jeu par face | Papier froissé sur les six faces | Réutiliser un carton marqué « Pokémon » ou d'un fournisseur |
| Display | Carton double cannelure, ou carton d'origine du display suremballé dans un carton d'expédition | Protège-coins ou papier sur les arêtes | Envoyer le display dans son seul film |
| Commande de plusieurs articles | Un seul carton, articles lourds au fond, séparateurs en carton | Remplir tous les vides | Laisser glisser les boîtes l'une contre l'autre |

Règles communes :

- **Aucune mention de la marque ni du contenu** à l'extérieur du colis (prévention du vol).
- Les commandes mixtes partent en deux envois : la partie en stock d'abord, la précommande à sa réception (CGV ch. 6.4).
- Un colis d'une valeur supérieure à {{SEUIL_ENVOI_SIGNATURE}} part contre signature ou avec assurance complémentaire (plafonds d'indemnisation du transporteur à lire dans son contrat).

## 5. Remise au transporteur

- [ ] R1. Compter les colis et les comparer à la liste du jour.
- [ ] R2. Déposer au guichet ou à l'enlèvement ; **garder la preuve de dépôt** (quittance ou scan de prise en charge), photographiée et classée par date : indispensable en cas de perte.
- [ ] R3. Vérifier le soir que chaque numéro de suivi affiche une prise en charge ; sinon, l'agent 11 alerte le lendemain matin.

## 6. Clôture de la session (agent 11)

- [ ] Toutes les commandes de la liste sont « expédiées », ou leur blocage est expliqué dans le journal.
- [ ] Mouvements `FULFILL` saisis ; stock vendable à jour ; aucun écart entre le scan et la commande.
- [ ] Emails d'expédition partis (contenu exact, numéro de suivi, articles expédiés, en particulier pour une commande partielle).
- [ ] Temps passé noté (BL-171) : début, fin, nombre de colis.
- [ ] Rapprochement paiement / commande prévu au rapprochement hebdomadaire (BL-166).

## 7. Erreurs fréquentes et parades

| Erreur | Parade |
|---|---|
| Mauvaise langue (EN au lieu de FR, même boîte) | Scan GTIN obligatoire (P3) ; emplacements séparés par langue si un jour d'autres langues sont stockées |
| Quantité incorrecte | Repère de commande coché (P5) ; photo (P6) |
| Étiquette inversée entre deux colis | Coller l'étiquette **juste après** la fermeture de son propre colis ; un colis à la fois sur la table |
| Colis écrasé en transit | Calage six faces ; carton double cannelure pour les displays |
| Précommande envoyée avant réception réelle | L'agent ne génère jamais l'étiquette d'une ligne de précommande avant le mouvement `RECEIPT` |

## 8. Fiche de session (à imprimer)

```
SESSION D'EXPÉDITION — date ___/___/______   début ____  fin ____   colis préparés : ____
| N° commande | Bon OK | Scan OK | Photo | Sticker | Étiquette | Remarque |
|-------------|--------|---------|-------|---------|-----------|----------|
|             | ☐      | ☐       | ☐     | ☐       | ☐         |          |
|             | ☐      | ☐       | ☐     | ☐       | ☐         |          |
|             | ☐      | ☐       | ☐     | ☐       | ☐         |          |
|             | ☐      | ☐       | ☐     | ☐       | ☐         |          |
Preuve de dépôt photographiée : ☐     Préparé par : ______________
```

## Validation humaine requise

- [ ] Propriétaire : valider les jours de dépôt (`JOURS_EXPEDITION`) et le délai d'expédition annoncé (`DELAI_EXPEDITION`).
- [ ] Propriétaire : fixer `SEUIL_ENVOI_SIGNATURE` après lecture des plafonds d'indemnisation du contrat transporteur (B17).
- [ ] Propriétaire : envoyer le colis test et mesurer le temps réel par colis (BL-105, BL-171).
- [ ] Propriétaire : valider l'achat du matériel d'emballage dans l'enveloppe de 300 CHF (BL-076).
