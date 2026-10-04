# Test publicitaire — plan, plafonds et règles d'arrêt

> Propriétaire (build) : agent « site-contenu ». Exécution : agent 10 Acquisition (BL-130, BL-133), calcul de contribution : agent 05, surveillance : agent 12. Décisions : propriétaire (G4/C15, G5/C16).
> Sources : BP §9 « Test publicité 500 CHF maximum » (J46-60) ; « Tester 2 ou 3 créations et une offre claire. Calculer le coût d'acquisition sur commandes payées, après annulations et remboursements. Fixer un plafond quotidien et arrêter si l'acquisition absorbe la contribution » ; « CAC inférieur à la contribution disponible » ; « une campagne s'arrête si le stock passe sous le seuil ou si la marge est insuffisante » ; BP §3 (test acquisition 500 CHF, plafond avant validation CAC) ; BP §10 (sensibilité au CAC). Gouvernance : `docs/00-pilotage/STOP_LOSS.md` (stop-loss pub), `config/stoploss.v1.yaml`, `config/mandate.v1.yaml`, `docs/00-pilotage/GATES_GO_NO_GO.md` (G4, G5), brief `docs/08-agents/10_acquisition.md`.
> Étoile polaire : la publicité n'est utile que si chaque commande qu'elle apporte laisse une contribution positive **après** son coût d'acquisition.

## 1. La question à trancher

**Peut-on acquérir une commande payée (nette d'annulations et de remboursements) pour moins que la contribution qu'elle apporte avant acquisition ?** Le test répond oui, non, ou « pas encore », avec 500 CHF au plus. Il ne cherche ni des abonnés, ni des vues.

## 2. Préconditions (toutes obligatoires ; agent 12 coche, propriétaire décide)

- [ ] Gate **G4 VERT** (premières commandes livrées, contribution positive, aucune survente) et **niveau d'autonomie 3** activé (C15).
- [ ] **Mandat signé** avec `ads_daily_cap_chf` et l'enveloppe `ADVERTISING` (proposée : 500 CHF) ; sans mandat signé, le stop-loss pub refuse toute dépense.
- [ ] **Comptes publicitaires** créés par la propriétaire (B20) avec un **plafond de dépense réglé au niveau du compte** (500 CHF) en plus du plafond jour des campagnes.
- [ ] **Cash disponible ≥ 1 600 CHF + budget engagé** (G4, critère 4.5) ; rappel écart EC-F-06 : les charges d'avant ouverture peuvent entamer la réserve et interdire le test.
- [ ] **Stop-loss pub branché** : dépenses quotidiennes par campagne (`AdSpend`) et commandes attribuées (`AttributedOrder`) transmises chaque jour à `engine/pokeshop/stoploss.py`.
- [ ] Produits promus **en stock local** (au moins 3 unités vendables par produit promu, **hypothèse**), fiches conformes (`site/shopify/MODELE_FICHE_PRODUIT.md`), aucun stop-loss produit actif.
- [ ] Liens suivis (UTM) et, pour un créateur, code ou lien dédié prêts ; page d'arrivée testée sur mobile.
- [ ] Bandeau cookies conforme (`docs/04-legal/COOKIES.md`) : la mesure ne dépend **pas** du pixel publicitaire (§6).

## 3. Budget, plafonds et calendrier

| Élément | Valeur | Source |
|---|---|---|
| Budget total du test | **500 CHF maximum**, collaboration locale comprise | BP §3, §9 ; écart EC-17 |
| Plafond réglé sur le compte publicitaire | 500 CHF | Intervention B20 |
| Plafond quotidien (toutes campagnes) | Valeur du mandat signé ; **proposée : 33 CHF** (≈ 500 CHF / 15 jours) | `config/mandate.v1.yaml`, brief A-10 |
| Période Black Friday (27.11.2026, J54) | Option A : démarrer le **30.11** (J57) ; option B : démarrer à J50 avec le plafond jour **divisé par deux** (≈ 16.50 CHF) jusqu'au 30.11 | Écart EC-10, G4 |
| Durée | 14 à 15 jours de diffusion | Plafond jour × durée ≤ 500 CHF |
| Fin du test | Budget épuisé, **ou** coupure par une règle du §7, **ou** décision G5 | — |
| Décision G5 | Après 7 jours complets de données (J60 avec l'option B ; ≈ J64 avec l'option A) | GATES G5 |

Répartition proposée : 3 campagnes (une par création), budget quotidien égal au départ ; aucune hausse de budget par un agent (escalade E2). La collaboration locale (`BRIEF_CREATEURS.md`) est décomptée du même total de 500 CHF (produits offerts au coût historique + rémunération).

## 4. Les trois créations

Visuels : photos et vidéos **réelles** (session A06) dans les gabarits DA ; aucun personnage, logo ou police de la licence hors de la photo du produit vendu ; « Pokémon » seulement pour désigner le produit ; nom de la page publicitaire = nom de la boutique (jamais « Pokémon »).

| | C1 — Guide | C2 — Nouveauté accessible | C3 — Preuve de service |
|---|---|---|---|
| Identifiant (`campaign_id` = `utm_campaign`) | `test-pub-c1-guide` | `test-pub-c2-produit` | `test-pub-c3-service` |
| Format | Carrousel 4:5 (sujet S01) | Image 4:5 ou 1:1 : photo réelle du produit + prix validé | Reel 9:16 (script V4, coulisses) |
| Texte principal | « ETB ou display ? On vous explique la différence, puis on vous montre ce qui est en stock à Genève. » | « [Format] [extension] en français, en stock local à Genève. CHF [prix validé]. Livraison en Suisse. » | « Scanné, contrôlé, calé sur six faces : votre commande est préparée à la main à Genève. » |
| Titre | « ETB ou display : lequel choisir ? » | « En stock local à Genève » | « Expédié depuis Genève » |
| Bouton | En savoir plus | Voir le produit | Voir le stock |
| Destination | Guide S01 puis collection Displays / ETB | Fiche du produit | Collection « Disponible maintenant » |
| Lien | `…?utm_source=meta&utm_medium=paid&utm_campaign=test-pub-c1-guide` | `…&utm_campaign=test-pub-c2-produit` | `…&utm_campaign=test-pub-c3-service` |
| Condition propre | — | Prix sur le visuel **=** prix publié, relu moins d'une heure avant la mise en ligne ; tout changement de prix ⇒ pause et nouveau visuel | Aucune étiquette, adresse ou donnée client visible |

**Offre claire** (BP §9) : « Pokémon JCC en français, en stock local à Genève, livré en Suisse, frais affichés avant le paiement. » **Pas de code de réduction par défaut.** Un code n'est envisagé que si le moteur confirme, panier type compris (`pricing.basket_contribution`), que chaque commande reste ≥ 12 % et ≥ 8 CHF de contribution (plancher dur) ; dans ce cas, la remise est décomptée de la contribution et le code sert aussi à l'attribution.

**Audience** : Suisse, adultes (18 ans et plus) ; Romandie en priorité si les inscriptions de la landing le confirment (hypothèse H3 du protocole) ; langue française ; centres d'intérêt liés aux jeux de cartes à collectionner et aux cadeaux. Aucune audience construite à partir de listes de clients ou d'inscrits sans base légale validée par le juriste. Aucun ciblage de mineurs.

## 5. Calendrier type (option A, démarrage le 30.11)

| Jour | Action | Qui |
|---|---|---|
| J50-J56 | Préparer les 3 créations, liens, campagnes en brouillon ; contrôle conformité (agent 12) ; GO de la propriétaire | A-10, A-09, A-12, H |
| J57 (30.11) | Mise en ligne des 3 campagnes au plafond jour | A-10 |
| Chaque jour 09:00 | Rapport quotidien (§9) ; stop-loss évalué ; coupure si déclenché | A-10, moteur |
| J64 | Bilan après 7 jours complets ; dossier G5 | A-10, A-05, A-01 |
| J64-J71 | Selon G5 : poursuite de la meilleure création, ajustement, ou arrêt | H (C16) |

## 6. Mesure : commandes payées nettes, pas de clics

| Terme | Définition (identique au moteur) |
|---|---|
| Dépense d'acquisition | Dépense publicitaire facturée + produits offerts (au coût historique) + commissions de créateurs, par campagne et par jour (`AdSpend`) |
| Commande attribuée | Commande **payée** dont la session d'arrivée porte l'`utm_campaign` de la campagne, ou qui utilise le code dédié ; une commande sans attribution n'est comptée pour aucune campagne (prudent) |
| Commande nette | Commande attribuée non annulée et non remboursée (statut `PAID` de `AttributedOrder`) |
| Contribution avant acquisition | Contribution de la commande calculée par le moteur (prix net − coût historique − paiement − logistique − provision SAV), jamais estimée par un agent |
| **CAC** | Dépense d'acquisition ÷ commandes nettes, sur **7 jours civils glissants** (fuseau Europe/Zurich) |

Le pixel de la plateforme n'est qu'un indicateur secondaire : avec des cookies soumis au consentement, il sous-attribue ; les décisions se prennent sur les commandes de la boutique.

## 7. Règles d'arrêt (automatiques, sans attendre une personne)

| Déclencheur | Action | Appliquée par | Reprise |
|---|---|---|---|
| CAC **>** contribution moyenne avant acquisition des commandes nettes, sur 7 jours glissants | Campagne coupée (`CUT_CAMPAIGN`) | Stop-loss pub → agent 10 | Nouvelle décision de la propriétaire |
| Aucune commande nette et dépense ≥ 20 CHF sur 7 jours | Campagne coupée | Stop-loss pub | Idem |
| Dépense du jour ≥ plafond jour | **Toutes** les campagnes coupées jusqu'au lendemain | Stop-loss pub + plafond de la plateforme | Automatique le lendemain |
| Cash disponible < 1 600 CHF | Plus aucune dépense publicitaire | Stop-loss cash | Automatique quand le cash remonte |
| Stock local du produit promu < 3 unités (**hypothèse**) | Pause de la campagne du produit | Agent 10 (BP §9) | Réassort reçu |
| Stop-loss produit (contribution < 12 % ou < 8 CHF) sur un produit promu | Pause | Agent 10 | Nouvelle décision de prix conforme |
| Prix public modifié | Pause, visuel mis à jour avant reprise | Agent 10 | Visuel conforme |
| Gel global | Tout coupé | Stop-loss global | Propriétaire seule |
| 500 CHF dépensés | Fin du test | Plateforme + agent 10 | Nouveau budget = décision G5 |

La coupure doit intervenir **dans l'heure** (hypothèse du brief A-10) ; la plateforme applique aussi le plafond du compte, en dernier rempart.

## 8. Lecture des résultats (G5)

Seuils de `GATES_GO_NO_GO.md` (G5), avec l'ordre de grandeur du BP §10 (contribution avant acquisition ≈ 19.33 CHF par commande ; hypothèse à remplacer par la valeur réelle du moteur) :

| Situation sur 7 jours glissants | Statut | Décision |
|---|---|---|
| CAC ≤ contribution − 8 CHF (≈ 11.33 CHF) | VERT | Poursuivre ; le budget suivant se construit sur cette preuve |
| contribution − 8 CHF < CAC ≤ contribution | ORANGE | Réduire le plafond, changer de création ou d'offre, rejouer 7 jours |
| CAC > contribution | ROUGE | Coupé (déjà fait par le stop-loss) |

**Exemples chiffrés FICTIFS** (contribution avant acquisition supposée à 19.33 CHF par commande) :

| Cas | Dépense 7 j | Commandes payées | Annulées / remboursées | Nettes | CAC | Statut |
|---|---:|---:|---:|---:|---:|---|
| A | 70.00 | 8 | 0 | 8 | 8.75 | VERT (≤ 11.33) |
| B | 100.00 | 8 | 1 | 7 | 14.29 | ORANGE |
| C | 120.00 | 5 | 1 | 4 | 30.00 | ROUGE : coupée (exemple 5 de `STOP_LOSS.md`) |
| D | 21.00 | 0 | 0 | 0 | — | Coupée : ≥ 20 CHF sans commande nette |

## 9. Rapport quotidien (modèle, agent 10)

```markdown
# Test pub — {{AAAA-MM-JJ}} — niveau {{n}}
Dépense jour : {{CHF}} / plafond {{CHF}} · cumul : {{CHF}} / 500
| Campagne | Dépense 7 j | Commandes payées | Nettes | CAC 7 j | Contribution moyenne (moteur) | Statut stop-loss |
|---|---:|---:|---:|---:|---:|---|
| test-pub-c1-guide | … | … | … | … | … | actif / COUPÉE hh:mm |
| test-pub-c2-produit | … | … | … | … | … | … |
| test-pub-c3-service | … | … | … | … | … | … |
Pauses (stock, prix, stop-loss produit) : …
Remarques (refus d'annonce, commentaires sensibles) : …
## Validation humaine requise
- [ ] {{décision attendue, ou « aucune »}}
```

## 10. Checklist de conformité avant mise en ligne (agent 12)

- [ ] Aucun prix autre que le prix publié ; aucune fausse urgence ; aucune promesse de rareté ou de valeur (`TON_EDITORIAL.md`).
- [ ] Mentions de marque conformes (`docs/04-legal/USAGE_MARQUES.md`) ; politique publicitaire de la plateforme relue le jour même (marques, jeux, public mineur).
- [ ] Audience adulte, Suisse uniquement ; aucune liste de contacts importée.
- [ ] Liens UTM corrects ; page d'arrivée en stock local ; plafond jour et plafond du compte réglés.
- [ ] Stop-loss pub testé à blanc (dépense FICTIVE au-dessus du plafond ⇒ coupure).

## Validation humaine requise

- [ ] Signer le mandat avec `ads_daily_cap_chf` (proposé : 33 CHF) et l'enveloppe publicitaire (500 CHF).
- [ ] Choisir l'option Black Friday : A (démarrer le 30.11) ou B (plafond jour divisé par deux jusqu'au 30.11).
- [ ] Créer les comptes publicitaires et régler le plafond de dépense du compte (B20).
- [ ] Valider les trois créations, l'absence de code de réduction (ou un code validé par le moteur) et l'audience.
- [ ] Valider les deux hypothèses de ce plan : 3 unités minimum en stock local par produit promu ; coupure dans l'heure.
- [ ] Décider G5 sur le bilan des 7 jours.
