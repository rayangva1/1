# SOP — Réception du stock

> SOP v0.1 du 4.10.2026, rédigée par l'agent legal-ops. À tester à blanc par la propriétaire avant la première livraison (BL-104).
> Sources : BP §4 (coût historique ≠ coût de remplacement), §5 (stock vendable = local après réservations, dommages, sécurité), §12 (« réception et authenticité » demandent une personne ; workflow facture → marge réelle) ; `docs/02-sourcing/CHECKLIST_DUE_DILIGENCE_FOURNISSEUR.md` §4 ; INTERVENTIONS_HUMAINES A03, A04, A05 ; BACKLOG BL-111, BL-112, BL-113, BL-196 (déclaration de la réception au moteur) ; API `POST /stock/receive` (`docs/SPEC.md` §2.7).
> Imprimer les pages « Bon de réception » (§5) : une par livraison.

## 1. En bref

| | |
|---|---|
| Qui | **Propriétaire** : réception, comptage, authenticité, photos (physique). **Agent 11 Opérations** : préparation du bon, **déclaration de la réception contrôlée au moteur** (`POST /stock/receive`, étape E2), saisie, réclamation. **Agent 05 Finance** : coût historique à la facture. **Agent 04 Catalogue** : publication. |
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
| Conforme | Vendable | `RECEIPT` (`POST /stock/receive`, étape E2) | Rangement | — | — |
| Manquant (reçu < bon) | — | `RECEIPT` de la quantité reçue seulement | Réclamation fournisseur avec photos (modèle §6) ; la facture ne doit pas compter les manquants | 48 h | — |
| Excédent (reçu > bon) | Non vendable « à régulariser » | aucun avant accord | Informer le fournisseur ; vendre seulement après facture ou accord écrit | 48 h | — |
| Langue différente du FR | QUARANTAINE | aucun | Réclamation ; fiche en brouillon ; jamais vendue comme FR | 48 h | Propriétaire si le fournisseur refuse la reprise |
| Produit différent (extension, format, contenu) | QUARANTAINE | aucun | Réclamation et retour fournisseur | 48 h | idem |
| Doute d'authenticité (scellé, impression) | **Tout le lot** en QUARANTAINE | aucun | Incident INC-11 ; réclamation ; aucune vente de ce lot | même jour | **Propriétaire, toujours** (C18) |
| Endommagé (enfoncement, film déchiré) | ENDOMMAGÉ (non vendable comme neuf) | aucun (hors du stock déclaré par `POST /stock/receive`, étape E2) | Réclamation avec photos : remplacement, avoir ou reprise | 48 h | Vente déclassée éventuelle : décision de la propriétaire (fiche et prix distincts, jamais vendue comme neuve) |
| Colis extérieur abîmé, contenu intact | Vendable | `RECEIPT` | Garder les photos (preuve) | — | — |

### E. Saisie (agent 11, avec les photos de la propriétaire)

- [ ] E1. Créer le lot de coût : `LOT-AAAAMMJJ-[FOURNISSEUR]-NN`, une ligne par référence (`CostLot` : référence produit, date de réception, quantité **conforme**, coût unitaire estimé à partir du bon de commande, base `ESTIMATE`, référence du bon).
- [ ] E2. **Déclarer au moteur chaque réception contrôlée** (agent 11, après les contrôles C et les décisions D) : `POST /stock/receive` avec **son** jeton nommé `operations-sav` (jamais le jeton commun), corps `{"sku": "…", "qty": …, "ref": "<réf. du bon de livraison ou du lot>"}`, une ligne par référence ; ou par la passerelle n8n du workflow 06 « Réception contrôlée (passerelle agent 11) » (webhook `pokeshop-stock-recu`), qui appelle la même route avec le credential `operations-sav` ; ce webhook n'est ouvert que par le **secret de passerelle de l'agent 11** (credential « Passerelle 06 réception — secret de l'agent 11 (operations-sav) », remis à lui seul) : aucun autre agent ne peut déclarer une réception en son nom. La déclaration est idempotente par (SKU, référence) : la rejouer ne double rien ; la même référence avec une autre quantité est refusée (409) : ne pas insister, ouvrir une fiche E2. **Sans cette déclaration, le moteur publie les fiches en « rupture » et laisse les nouvelles références en brouillon.** Quantité déclarée = unités **conformes** seulement : l'API n'expose pas de mouvement `MARK_DAMAGED`, donc les unités endommagées restent hors du stock déclaré (bac ENDOMMAGÉ, photos, réclamation) jusqu'à la décision de la propriétaire ; les unités en quarantaine ne sont **jamais** déclarées.
- [ ] E3. Vérifier le stock vendable calculé : `on_hand − réservé − endommagé − sécurité` (`POST /stock/sellable` avec le SKU : `source = registre`).
- [ ] E4. Si des précommandes attendent ce produit : les servir **avant** toute nouvelle vente (PRECOMMANDES §2.3).
- [ ] E4 bis. **Pré-drop** (réservation garantie, PRECOMMANDES §2.5) : lire les réservations confirmées du produit (`GET /predrop/reservations?predrop_id=…`, état `CONFIRMED`) et les **préparer en premier**, dans l'ordre de paiement, avant toute vente au prix du drop ; les unités de ces réservations ne sont jamais mises en vente sur la fiche normale : le moteur **retient** tout le stock de la fiche normale jusqu'au jour du drop (une réception avant le drop ne rend rien vendable au prix du drop) puis en exclut les unités des réservations confirmées non expédiées (BL-212 ; `POST /stock/receive` le dit : `sellable_at_drop_price`, `predrop.hold_until_drop`, `predrop.reserved_unshipped_units`). Chaque réservation part **dans son propre envoi** enregistré avec la ligne `-RESA-` de la fiche de réservation (premier envoi de la commande : `<commande>` ; envoi suivant d'une commande mixte dont un article en stock est déjà parti : `<commande>/envoi-<n>`) : c'est cette ligne qui éteint la dette et reconnaît la vente. Reçu moins que l'allocation ferme : déclarer la réduction (`POST /predrop/allocations/{product_key}/reduce`, jeton `operations-sav`, référence du bon) **avant** toute préparation : toute la quantité reçue sert d'abord les réservations (ordre de paiement), puis le drop ; les dernières réservations sont remboursées s'il manque encore des unités. Aucune quantité n'est communiquée en public (`docs/06-contenu/PLAN_JOUR_DE_DROP.md`).
- [ ] E5. Classer les photos : `réceptions/AAAA-MM-JJ/[LOT]/` (aucune donnée personnelle).
- [ ] E6. Signaler à l'agent 04 que les fiches peuvent passer de « alerte réassort » à « stock local » (après photos réelles si nécessaires, A06).

### F. Après la réception (agents 05 et 11)

- [ ] F1. Réclamations envoyées dans les 48 h, avec photos et numéros de lot (modèle §6).
- [ ] F2. À réception de la facture et du justificatif d'import : rapprocher commande / réception / facture, ventiler les frais (port, dédouanement, et TVA d'import **à part** : l'agent 05 extrait le montant de TVA d'import du décompte de douane ou du transporteur dans `fees_chf.import_vat`, le workflow 03 le ventile par unité dans `import_vat_unit_chf`, et le moteur le compte au coût **selon son profil TVA** — méthode effective : récupérable, hors coût ; non assujettie : coût ; revue R5, R4-DOC-02), passer le lot en base `INVOICE` (`HistoricalCostLedger.apply_invoice`). Quantités et coûts **par unité de vente** : une ligne facturée au carton est convertie avant l'envoi (quantité × contenu, coût ÷ contenu), sinon 03 l'arrête en anomalie ; le formulaire de validation montre quantité, unité, frais et coût rendu unitaire calculé. Un écart de plus de 2 % entre estimation et facture est expliqué (BL-145). L'agent 05 transmet la facture extraite au workflow 03 (passerelle `pokeshop-facture`, son secret) ; après **votre validation** de l'extraction (formulaire 72 h), 03 l'**enregistre au moteur** (`POST /costs/invoices`, jeton `n8n-03-factures` : lignes au coût rendu unitaire ventilé, sur la clé produit canonique). La facture enregistrée devient la référence du coût de réception et une dette de la photo du stop-loss jusqu'à son paiement relevé (`POST /costs/invoices/{réf}/payments`, `connecteur-tresorerie` ou vous).
- [ ] F2 bis. **Coûts au registre du moteur** (agent 05, jeton `finance-pricing`, jamais celui de l'agent 11) : `POST /costs/movements` `RECEIPT` avec `product_key` = la clé canonique de la fiche (`product_id` = `listing.product_key`), `stock_ref` = la référence déclarée en E2 (même SKU, même quantité), `invoice_ref` = la facture enregistrée en F2 et le coût unitaire rendu ; `INVOICE_ADJUSTMENT` avec `invoice_ref` à réception de la facture définitive. Contrôles du moteur : une réception sans déclaration E2 d'un **autre** jeton est refusée (409) ; une réception physique (SKU **au moment de la réception**, bon) n'est valorisée **qu'une fois**, quelle que soit la clé citée ou le SKU actuel de la fiche (409) ; une référence `return:<avoir>` (retour client) n'est jamais une réception au coût d'une facture (409 : retour au coût par `RETURN`, SOP_SAV_RETOURS R5 bis) ; le coût unitaire doit rester à **± 2 % de la ligne de la facture enregistrée** citée (référence prioritaire, validée par la propriétaire), dont les unités reçues au coût ne dépassent jamais la **quantité facturée** (409 : carton saisi comme unité) et dont le fournisseur est **connu du moteur** pour la référence — lien fournisseur déclaré au catalogue par l'agent `catalogue`, ou offre de ce fournisseur rapprochée par un cycle `/sync/run` sur le catalogue du registre (409 sinon, y compris quand aucun fournisseur n'est connu : déclarer le lien ou laisser la propriétaire inscrire le coût) — à défaut, du coût rendu de la dernière offre évaluée par le moteur (`/sync/run`, catalogue et frais du registre) **avec des frais posés par la propriétaire** (des frais posés par l'agent 05, ou un cycle de simulation avec catalogue ou frais dans le corps, ne fournissent **jamais** de référence : revue R5, R2-NEW-01 / R4-DOC-09). Au-delà de 2 % ou sans aucune référence (facture pas encore enregistrée, par exemple pendant les 72 h de validation, ou après un redémarrage) : 403, la propriétaire inscrit le coût avec son jeton (C23) ou l'agent 05 attend l'enregistrement de la facture ; un ajustement de plus de 2 % par rapport au coût de réception attend aussi la propriétaire. La sortie d'une unité vendue n'est **jamais** saisie ici : le moteur la dérive des lignes de la commande expédiée (`POST /orders/shipped`, au CMP) ; une commande expédiée **avant** l'inscription du coût est enregistrée quand même, avec un coût des ventes **en attente** dérivé dès l'inscription du coût (revue R5, R4-NEW-01 : aucune vente perdue, mais étoile polaire et photo signalées incomplètes et toute dépense en validation humaine d'ici là). Sans ces mouvements, la photo du stop-loss ne compte pas ce stock.
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
