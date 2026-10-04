# SOP — Réception du stock

> SOP v0.1 du 4.10.2026, rédigée par l'agent legal-ops. À tester à blanc par la propriétaire avant la première livraison (BL-104).
> Sources : BP §4 (coût historique ≠ coût de remplacement), §5 (stock vendable = local après réservations, dommages, sécurité), §12 (« réception et authenticité » demandent une personne ; workflow facture → marge réelle) ; `docs/02-sourcing/CHECKLIST_DUE_DILIGENCE_FOURNISSEUR.md` §4 ; INTERVENTIONS_HUMAINES A03, A04, A05 ; BACKLOG BL-111, BL-112, BL-113.
> Imprimer les pages « Bon de réception » (§5) : une par livraison.

## 1. En bref

| | |
|---|---|
| Qui | **Propriétaire** : réception, comptage, authenticité, photos (physique). **Agent 11 Opérations** : préparation du bon, saisie, réclamation. **Agent 05 Finance** : coût historique à la facture. **Agent 04 Catalogue** : publication. |
| Quand | Le jour de la livraison ; contrôle complet dans les **24 h** ; réclamation fournisseur dans les **48 h** (BL-111). |
| Durée | 30 à 60 min par livraison, plus environ 15 min d'authenticité par lot (estimation INTERVENTIONS A03-A04, à mesurer). |
| Matériel | Bon de réception imprimé, cutter à lame rétractable (pour le carton extérieur seulement), smartphone (photos et lecture des codes-barres), étiquettes d'emplacement, bac « QUARANTAINE », bac « ENDOMMAGÉ ». |
| Lieu | {{EMPLACEMENT_STOCK}} : sec, à l'abri du soleil, rien posé au sol, hors de portée d'animaux. |

## 2. Règles d'or

1. **Rien n'est vendable tant que la réception n'est pas saisie.** Le stock fournisseur n'est jamais du stock boutique (BP §5).
2. **Le moindre doute d'authenticité met tout le lot en quarantaine** (CHECKLIST_DUE_DILIGENCE §4).
3. **On n'ouvre jamais un produit scellé** : tous les contrôles se font sur l'emballage.
4. **Photo d'abord, puis on déballe** : la photo est la preuve pour la réclamation.
5. **Pas de saisie de stock à la main dans Shopify** : la saisie passe par le moteur (mouvement `RECEIPT`), qui synchronise Shopify. Exception : moteur indisponible ; la propriétaire saisit alors dans Shopify, note la saisie au journal et l'agent rapproche ensuite (une seule autorité de stock, BP §6).

## 3. Étapes

### A. Avant l'arrivée (agent 11, la veille)

- [ ] A1. Générer le bon de réception attendu à partir de la commande fournisseur : références, GTIN, langue, quantités, numéro de commande, transporteur, date prévue.
- [ ] A2. Vérifier que les emplacements et les bacs QUARANTAINE et ENDOMMAGÉ sont libres.
- [ ] A3. Prévenir la propriétaire du créneau de livraison (digest quotidien).

### B. À la livraison (propriétaire)

- [ ] B1. Compter les colis livrés contre le bordereau du transporteur.
- [ ] B2. Examiner chaque colis **avant de signer** : carton enfoncé, ouvert, mouillé, ruban non d'origine ?
- [ ] B3. Si un colis est abîmé : le photographier sous deux angles, puis signer **avec réserve écrite** (« colis endommagé, sous réserve de contrôle du contenu ») si le transporteur le permet. Sinon, noter l'heure et le nom du livreur.
- [ ] B4. Ne pas refuser une livraison sans en avoir parlé à l'agent 11 (sauf colis manifestement détruit).

### C. Contrôle du contenu (propriétaire, dans les 24 h)

Pour chaque carton :

- [ ] C1. Photographier le carton fermé, puis ouvert, avant de sortir quoi que ce soit.
- [ ] C2. Compter les unités par référence et les reporter sur le bon de réception (colonne « Reçu »).
- [ ] C3. Lire le code-barres (GTIN) de chaque référence avec le smartphone : il doit correspondre au bon.
- [ ] C4. **Langue** : la mention française figure sur l'emballage et correspond au bon et à la facture.
- [ ] C5. **Produit exact** : extension, format, contenu annoncé (nombre de boosters, accessoires) lus sur l'emballage, sans ouvrir.
- [ ] C6. **Scellé** : film d'origine intact, sans recollage ; scellés et languettes conformes ; aucune trace d'ouverture.
- [ ] C7. **Authenticité** : impression nette, couleurs cohérentes d'un exemplaire à l'autre, aucune faute ni logo approximatif, cohérence des numéros de lot s'ils existent.
- [ ] C8. **Dommages** : coins écrasés, enfoncements, film déchiré, humidité. Un produit endommagé va au bac ENDOMMAGÉ, photographié individuellement.
- [ ] C9. Ranger les unités conformes à leur emplacement, la plus ancienne réception devant (premier entré, premier sorti).

### D. Décisions (propriétaire constate, agent 11 exécute)

| Constat | Statut de l'unité | Mouvement moteur | Action | Délai | Escalade |
|---|---|---|---|---|---|
| Conforme | Vendable | `RECEIPT` | Rangement | — | — |
| Manquant (reçu < bon) | — | `RECEIPT` de la quantité reçue seulement | Réclamation fournisseur avec photos (modèle §6) ; la facture ne doit pas compter les manquants | 48 h | — |
| Excédent (reçu > bon) | Non vendable « à régulariser » | aucun avant accord | Informer le fournisseur ; vendre seulement après facture ou accord écrit | 48 h | — |
| Langue différente du FR | QUARANTAINE | aucun | Réclamation ; fiche en brouillon ; jamais vendue comme FR | 48 h | Propriétaire si le fournisseur refuse la reprise |
| Produit différent (extension, format, contenu) | QUARANTAINE | aucun | Réclamation et retour fournisseur | 48 h | idem |
| Doute d'authenticité (scellé, impression) | **Tout le lot** en QUARANTAINE | aucun | Incident INC-11 ; réclamation ; aucune vente de ce lot | même jour | **Propriétaire, toujours** (C18) |
| Endommagé (enfoncement, film déchiré) | ENDOMMAGÉ (non vendable comme neuf) | `RECEIPT` puis `MARK_DAMAGED` | Réclamation avec photos : remplacement, avoir ou reprise | 48 h | Vente déclassée éventuelle : décision de la propriétaire (fiche et prix distincts, jamais vendue comme neuve) |
| Colis extérieur abîmé, contenu intact | Vendable | `RECEIPT` | Garder les photos (preuve) | — | — |

### E. Saisie (agent 11, avec les photos de la propriétaire)

- [ ] E1. Créer le lot de coût : `LOT-AAAAMMJJ-[FOURNISSEUR]-NN`, une ligne par référence (`CostLot` : référence produit, date de réception, quantité **conforme**, coût unitaire estimé à partir du bon de commande, base `ESTIMATE`, référence du bon).
- [ ] E2. Enregistrer les mouvements : `RECEIPT` (conformes et endommagés), puis `MARK_DAMAGED` pour les endommagés. Les unités en quarantaine ne sont pas saisies.
- [ ] E3. Vérifier le stock vendable calculé : `on_hand − réservé − endommagé − sécurité` (`sellable_local`).
- [ ] E4. Si des précommandes attendent ce produit : les servir **avant** toute nouvelle vente (PRECOMMANDES §2.3).
- [ ] E5. Classer les photos : `réceptions/AAAA-MM-JJ/[LOT]/` (aucune donnée personnelle).
- [ ] E6. Signaler à l'agent 04 que les fiches peuvent passer de « alerte réassort » à « stock local » (après photos réelles si nécessaires, A06).

### F. Après la réception (agents 05 et 11)

- [ ] F1. Réclamations envoyées dans les 48 h, avec photos et numéros de lot (modèle §6).
- [ ] F2. À réception de la facture et du justificatif d'import : rapprocher commande / réception / facture, ventiler les frais (port, dédouanement, TVA non récupérable selon le statut), passer le lot en base `INVOICE` (`HistoricalCostLedger.apply_invoice`). Un écart de plus de 2 % entre estimation et facture est expliqué (BL-145).
- [ ] F3. Ne **jamais** modifier le prix d'une commande déjà conclue, même si la facture est plus chère (BP §5). Le moteur recalcule la contribution réalisée ; le stop-loss produit agit sur les ventes futures.
- [ ] F4. Le coût historique du lot ne change pas si le fournisseur baisse ensuite son tarif (BP §4) : seule la valeur de remplacement change.

## 4. Stock endommagé et quarantaine : règles

- Une unité ENDOMMAGÉE n'est jamais vendue comme neuve. Sa sortie (retour fournisseur, vente déclassée sur décision, destruction) est saisie (`WRITE_OFF` si elle sort sans vente).
- La quarantaine est **physique** (bac étiqueté) **et** logique (non saisie, ou bloquée au catalogue). Elle se lève seulement par écrit : réponse du fournisseur et décision de la propriétaire pour l'authenticité.
- Une panne du flux fournisseur n'efface jamais le stock local confirmé (BP §12).

## 5. Bon de réception (à imprimer)

```
BON DE RÉCEPTION — {{NOM_BOUTIQUE}}                    N° lot : LOT-____________-____
Fournisseur : ______________________   Commande fournisseur n° : ______________
Date de livraison : ___/___/______  Heure : ____  Transporteur : _______________
Colis annoncés : ____  Colis reçus : ____  Réserve écrite au transporteur : ☐ oui ☐ non
Photos des colis fermés : ☐   Photos des colis ouverts : ☐

| Réf. / GTIN | Désignation (format, extension) | Langue FR | Attendu | Reçu | Conforme | Endommagé | Quarantaine | Remarque |
|-------------|--------------------------------|-----------|---------|------|----------|-----------|-------------|----------|
|             |                                | ☐         |         |      |          |           |             |          |
|             |                                | ☐         |         |      |          |           |             |          |
|             |                                | ☐         |         |      |          |           |             |          |
|             |                                | ☐         |         |      |          |           |             |          |
|             |                                | ☐         |         |      |          |           |             |          |

Authenticité contrôlée (film, scellés, impression, contenu annoncé) : ☐ OK  ☐ DOUTE → lot entier en quarantaine
Contrôlé par : ______________________  Signature : ______________  Date : ___/___/______
Saisi dans le moteur par : ____________  Date : ___/___/______  Réclamation envoyée le : ___/___/______
```

## 6. Modèle de réclamation fournisseur (agent 11, dans les 48 h)

> Objet : Réclamation réception — commande [NUMERO_COMMANDE_FOURNISSEUR] — livraison du [DATE]
>
> Bonjour,
>
> Nous avons réceptionné la livraison citée en objet le [DATE]. Notre contrôle fait apparaître les écarts suivants :
>
> | Référence / GTIN | Attendu | Reçu | Écart constaté |
> |---|---|---|---|
> | [REF] | [QTE] | [QTE] | [manquant / endommagé / langue / produit différent] |
>
> Vous trouverez les photos en pièces jointes (colis fermé, colis ouvert, unités concernées). Les unités concernées sont isolées et ne sont pas vendues.
>
> Merci de nous indiquer la solution proposée (remplacement, avoir ou reprise) et la procédure de retour éventuelle.
>
> Meilleures salutations,
> {{RAISON_SOCIALE}} — {{EMAIL_SUPPORT}}

## Validation humaine requise

- [ ] Propriétaire : tester cette SOP à blanc avec un colis fictif avant la première livraison (BL-104) et noter le temps réel.
- [ ] Propriétaire : définir et aménager le lieu de stockage (`EMPLACEMENT_STOCK`, A05).
- [ ] Propriétaire : décider la politique pour le stock endommagé (retour fournisseur seulement, ou vente déclassée sur fiche distincte).
- [ ] Propriétaire : lever chaque quarantaine d'authenticité par écrit (jamais un agent).
