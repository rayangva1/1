# Checklist de due diligence fournisseur

> À remplir par l'agent 02, avec le contrôle de l'agent 12, pour **chaque fournisseur qui répond** (BL-046), **avant** son ajout à la liste autorisée du mandat (C08) et avant toute commande.
> BP §2 : « Une mention Pokémon sur un site ne confirme ni une distribution officielle pour la France, ni un export vers la Suisse, ni une allocation FR régulière. » BP §6 : « Un portail visible dans un navigateur n'est pas la preuve d'une API. »
> Une checklist par fournisseur. Nom du fichier : `DD_{{fournisseur}}_{{AAAAMMJJ}}.md`. Chaque réponse cite une **preuve** : email daté, document, page datée. Une déclaration orale ne vaut pas preuve.

## Fiche d'identification

| Champ | Valeur | Preuve |
|---|---|---|
| Fournisseur (raison sociale exacte) | | Registre (SIREN, IDE, Handelsregister…) |
| Pays d'établissement | | |
| Numéro d'entreprise / TVA | | Registre officiel consulté le … |
| Contact commercial (fonction, pas de nom inventé) | | Email reçu le … |
| Date de la checklist | | |
| Rempli par / contrôlé par | Agent 02 / Agent 12 | |

## Légende

- **É** = critère **éliminatoire** : un « non » ou une absence de preuve exclut le fournisseur, sauf exception écrite de la propriétaire (C18).
- Score : 0 = non ou inconnu, 1 = partiel, 2 = oui avec preuve.

## 1. Existence et légitimité

| # | Question | É | Score | Preuve |
|---|---|---|---|---|
| 1.1 | L'entreprise existe au registre officiel, avec la même raison sociale que sur les factures proposées | É | | |
| 1.2 | Ancienneté et activité cohérentes avec la distribution de cartes à collectionner | | | |
| 1.3 | Conditions générales de vente B2B écrites et accessibles | | | |
| 1.4 | Aucun signal d'alerte public grave (fraude, liquidation, avis massivement négatifs sur les livraisons) | É | | Recherche datée |

## 2. Distribution officielle FR

| # | Question | É | Score | Preuve |
|---|---|---|---|---|
| 2.1 | Statut déclaré : distributeur officiel du territoire, sous-distributeur ou grossiste secondaire | | | Réponse écrite |
| 2.2 | Pour un grossiste secondaire : origine des produits FR (distributeur officiel d'approvisionnement) indiquée | É | | Réponse écrite |
| 2.3 | Produits **scellés, neufs, version française officielle**, sans reconditionnement | É | | Réponse écrite |
| 2.4 | Factures nominatives avec désignation exacte, langue et EAN | É | | Modèle de facture ou devis |
| 2.5 | Engagement de reprise ou de remboursement en cas de produit non conforme ou contrefait | É | | CGV ou email |

## 3. Export vers la Suisse

| # | Question | É | Score | Preuve |
|---|---|---|---|---|
| 3.1 | Accepte un client établi en Suisse (avec ou sans numéro de TVA, préciser) | É | | Email |
| 3.2 | Livre en Suisse ; **pays réel d'expédition** indiqué | É | | Email |
| 3.3 | Facturation : HT avec documents d'exportation, ou TTC (TVA étrangère non récupérable, qui entre alors dans le coût rendu) | | | Devis |
| 3.4 | Incoterm, transporteur, délai et coût du port vers la Suisse écrits | | | Devis |
| 3.5 | Dédouanement : qui le fait, frais facturés par le transporteur, documents fournis (facture commerciale, preuve d'export) | | | Email |
| 3.6 | Aucune restriction territoriale qui interdirait la revente en Suisse (contrat de distribution, embargo) | É | | Email |

> Rappel coût rendu (BP §4) : C = achat net en CHF + transport amont réparti + dédouanement et frais non récupérables + TVA non récupérable. Droits de douane sur les produits industriels : supprimés depuis le 1.1.2024 (SECO, indexé ; écart EC-18). La TVA import et les frais du transporteur restent dus. Les montants se saisissent dans `COMPARATEUR_OFFRES.xlsx`.

## 4. Authenticité et contrôle à réception

| # | Question | É | Score | Preuve |
|---|---|---|---|---|
| 4.1 | Traçabilité des lots (numéros de lot ou de carton, bons de livraison) | | | |
| 4.2 | Délai de réclamation en cas de casse, manquant ou non-conformité (idéalement ≥ 48 h après réception) | | | CGV |
| 4.3 | Emballage d'expédition adapté (cartons d'origine, calage) | | | |
| 4.4 | Politique écrite en cas de suspicion de contrefaçon | | | |

**Points de contrôle physique à réception** (action A04, propriétaire) :

- [ ] Le film d'origine est intact et sans recollage ; les scellés et la languette sont conformes ; aucune trace d'ouverture.
- [ ] La langue **française** figure sur l'emballage et correspond à la facture.
- [ ] Le contenu annoncé est conforme (nombre de boosters, accessoires, promo) : sur l'emballage, sans ouvrir.
- [ ] L'impression est nette et les couleurs cohérentes d'un exemplaire à l'autre ; aucune faute ni logo approximatif.
- [ ] Les quantités et les EAN correspondent au bon de livraison.
- [ ] Photo de chaque carton à l'ouverture (preuve SAV fournisseur).
- [ ] Le moindre doute met **tout le lot en quarantaine** (non vendable), avec réclamation au fournisseur.

## 5. Allocations et disponibilité

| # | Question | É | Score | Preuve |
|---|---|---|---|---|
| 5.1 | Règles d'allocation sur les nouveautés écrites (critères, délai de confirmation) | | | |
| 5.2 | Possibilité d'**allocation ferme** confirmée par écrit avant l'ouverture de précommandes | | | |
| 5.3 | Historique ou profondeur de stock en FR sur les extensions récentes | | | |
| 5.4 | Délai de réassort habituel | | | |

> Sans allocation ferme écrite : aucune précommande (BP §3, §5). Les allocations rares ne justifient pas un produit à faible marge (BP §1).

## 6. Flux de données automatisable — « un portail n'est pas une API »

| # | Question | É | Score | Preuve |
|---|---|---|---|---|
| 6.1 | Mode de mise à disposition : API documentée, fichier CSV/XML/Excel régulier, téléchargement authentifié, email périodique, ou **portail seulement** | | | Documentation ou fichier reçu |
| 6.2 | **Exemple de fichier ou de réponse d'API reçu** et archivé (capture datée) | | | Chemin du fichier |
| 6.3 | Import d'essai réussi par l'importeur (`engine/pokeshop/importers/`), sans anomalie critique | | | Rapport d'import |
| 6.4 | Identifiants stables (SKU, EAN) d'une version à l'autre | | | Deux fichiers comparés |
| 6.5 | Stock **quantifié** (et non un simple statut), horodaté | | | Fichier |
| 6.6 | Fréquence de mise à jour (prix : idéalement ≤ 6 h ; stock : 30 à 60 min si API fiable, sinon fréquence du fichier ; BP §5) | | | |
| 6.7 | Commandes et accusés de réception électroniques (EDI, API, email structuré) | | | |
| 6.8 | Usage des données **autorisé par écrit** (licence, fréquence d'appel). Aucune lecture automatisée d'un portail sans accord écrit, aucun contournement de CAPTCHA (BP §6, SPEC §0.9) | É (pour tout flux automatisé) | | Email |

**Test « un portail n'est pas une API »** : un fournisseur qui n'offre qu'un portail web, sans export ni accord écrit d'usage automatisé, est classé **« import assisté »**. Les agents travaillent alors à partir de l'email ou du PDF tarifaire reçu (BP §6, priorité 3), avec contrôle des unités et des totaux. Le niveau d'autonomie 4 (réassort automatique) reste alors impossible pour ce fournisseur.

## 7. Conditions commerciales

| # | Question | Score | Preuve |
|---|---|---|---|
| 7.1 | Prix nets, devise, HT ou TTC clairement indiqués | | Devis |
| 7.2 | MOQ et cartons compatibles avec le budget pilote (enveloppes de 100 à 375 CHF par case, `ASSORTIMENT_PILOTE.md`) | | |
| 7.3 | Paiement : prépaiement, délai, moyens (impact BFR, note finance) | | |
| 7.4 | Droit de réutiliser textes et images, écrit | | |
| 7.5 | Interlocuteur et délai de réponse SAV | | |

## 8. Synthèse et décision

| Bloc | Score max | Score | Éliminatoire en échec ? |
|---|---:|---:|---|
| 1. Existence | 8 | | |
| 2. Distribution FR | 10 | | |
| 3. Export Suisse | 12 | | |
| 4. Authenticité | 8 | | |
| 5. Allocations | 8 | | |
| 6. Flux de données | 16 | | |
| 7. Conditions | 10 | | |
| **Total** | **72** | | |

| Classement proposé | Règle |
|---|---|
| **Autorisable – flux** | Aucun éliminatoire en échec ; total ≥ 50 ; 6.2 et 6.3 à 2 |
| **Autorisable – import assisté** | Aucun éliminatoire en échec ; total ≥ 40 |
| **2e source** | Aucun éliminatoire en échec ; devis écrit reçu (définition d'EC-06) |
| **Non retenu** | Un éliminatoire en échec, ou total < 40 |

Décision de la propriétaire (C08) : ☐ ajouté à la liste autorisée, plafond de commande : … CHF · ☐ refusé · ☐ en attente de : … — Date : … — Signature : …

## Validation humaine requise

- [ ] Valider la liste des critères éliminatoires (É) et les seuils de classement (50 / 40 points), qui sont des **hypothèses** de l'agent pilotage.
- [ ] Décider, fournisseur par fournisseur, de l'ajout à la liste autorisée et du plafond de commande (C08).
- [ ] Réaliser les contrôles physiques du §4 à chaque réception (A04).
