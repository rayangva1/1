# Gates go/no-go — {{NOM_BOUTIQUE}}

> Points de décision du lancement, avec seuils chiffrés, preuves exigées et décideur.
> Sources : BP du 4.10.2026, intro « Conditions de lancement », §1 « Indicateurs de validation », §9 (critères de passage), §13 (critères de recette et « Décision de poursuivre ou arrêter »).
> Les seuils marqués **(hypothèse)** ne figurent pas dans le BP : ce sont des propositions de l'agent pilotage, à valider (BL-016). Calendrier : `PLAN_90_JOURS.md`. Tâches : `BACKLOG.csv`.

## 1. Règles communes

**Métrique de décision : l'étoile polaire.** La contribution nette cumulée = ventes nettes HT − coût historique − paiement − logistique − SAV − acquisition − charges fixes. Le chiffre d'affaires et les followers ne servent jamais de critère. Les indicateurs du BP §1, comme « contribution positive après publicité » (avant charges fixes), sont suivis **en plus** (écart EC-12). Étoile polaire **incomplète** (`GET /northstar` : `incomplete: true`, écriture dérivée d'une commande impossible, détail dans `derivation_errors`) : tout critère qui la lit est ROUGE tant que la propriétaire n'a pas corrigé l'écriture (fermé par défaut, `ETOILE_POLAIRE.md` §2).

**Les stop-loss priment sur les gates.** Un stop-loss déclenché (produit, extension, pub, cash, global, temps) s'applique immédiatement, quel que soit le résultat du dernier gate. Les règles et leur calcul appartiennent à l'agent gouvernance : `docs/00-pilotage/STOP_LOSS.md` et `engine/pokeshop/stoploss.py`. Rappel des seuils :

| Niveau | Déclencheur | Effet automatique |
|---|---|---|
| Produit | contribution < 12 % ou < 8 CHF par commande | vente/promo bloquée |
| Extension | > 25 % du budget stock, ou 45 j sans vente | plus de réassort + proposition de démarque |
| Pub | CAC > contribution sur 7 j glissants, ou plafond jour atteint | campagne coupée |
| Cash | cash disponible < 1 600 CHF | plus d'achat ni de pub |
| Global | perte de valeur nette ≥ 20 % du capital engagé de référence (840 CHF avec le point zéro recommandé, C19) ; photo non évaluable = tout refusé | tout gelé, retour au niveau d'autonomie 1, alerte ; réarmement par la propriétaire uniquement, avec son jeton et la valeur nette attestée |
| Temps | 60 j sans atteindre les seuils de validation | dossier continuer/ajuster/arrêter |

**Revue adverse de sécurité avant chaque niveau d'autonomie.** Le passage aux niveaux **2** (C14, ≈ J38), **3** (C15, avec G4, ≈ J45) et **4** (C17, option, ≈ J85) exige une **revue adverse de sécurité relancée et sans critical/high ouvert** sur la version mise en service (`REVUE_SECURITE.md` §5 ; intervention C31 ; tâches BL-200, BL-201, BL-202), et chaque risque résiduel « à traiter avant » ce niveau (`REVUE_SECURITE.md` §4) corrigé ou accepté par écrit par la propriétaire. Sinon, le gate peut conclure GO mais le niveau **n'est pas relevé** (REPORT du seul passage de niveau, rejoué après correction et nouvelle revue). Toute modification du code ou des workflows entre la revue et la hausse de niveau rend la revue caduque ; un composant qui écrit une valeur décisive et entre en service **après** la hausse de niveau (ex. le connecteur publicitaire, BL-198) exige d'abord une revue limitée à son diff, sans critical/high ouvert (BL-203, `REVUE_SECURITE.md` §1).

**Les quatre issues d'un gate :**

| Issue | Sens | Effet |
|---|---|---|
| **GO** | Tous les critères sont VERTS | Phase suivante selon le plan |
| **GO sous conditions** | Aucun critère ROUGE ; ORANGES avec action et date | Phase suivante avec un périmètre ou un budget réduit, précisé dans la fiche |
| **REPORT** | Au moins un critère ROUGE corrigeable | Pas de dépense de la phase suivante ; le gate est rejoué à une date fixée (14 j max) |
| **STOP** | Critère éliminatoire, ou REPORT déjà rejoué sans amélioration | Dossier d'arrêt : stock restant, abonnements, communication |

**Qui fait quoi.** L'agent 01 (chef de projet) remplit la fiche du gate (modèle au §4) avec les preuves. L'agent 05 (finance) fournit les chiffres et l'agent 12 (QA) certifie les tests. La décision revient à la **propriétaire** pour G0, G3, G4, G5 et G7. Pour G1, G2 et G6, l'agent 01 conclut seul et n'escalade qu'en cas de ROUGE, afin de limiter les interventions humaines.

**« Erreur critique »** (BP §9 et §13, non défini dans le BP ; écart EC-11) : toute occurrence d'un des cas suivants, en simulation comme en réel :

1. un prix public différent du prix validé, ou sous le plancher dur sans validation ;
2. un stock publié supérieur au stock vendable local, ou un stock fournisseur affiché comme expédiable ;
3. un champ de coût, de marge, de fournisseur ou une donnée personnelle dans un payload ou une page publics ;
4. une double écriture après une reprise (idempotence violée) ;
5. une promesse de disponibilité fondée sur une donnée amont de plus de 24 h ;
6. une commande payée sans réservation de stock, ou une réservation sans paiement confirmé ;
7. une TVA, une devise ou un taux de change erroné dans un calcul publié ;
8. une écriture réelle alors que le niveau d'autonomie ne l'autorise pas.

## 2. Les gates

### G0 — Démarrage des agents (J1)

| # | Critère | VERT | ROUGE | Preuve |
|---|---|---|---|---|
| 0.1 | Mandat écrit signé (plafonds, fournisseurs autorisés, interdits, journal) | signé | non signé | BL-002, `DELEGATION_AUTONOMIE.md` |
| 0.2 | Boîte email dédiée et coffre de secrets | actifs | absents | BL-003, BL-005 |
| 0.3 | Niveau d'autonomie 1 actif | consigné | — | BL-006 |
| 0.4 | Budget pilote et financement des charges d'avant ouverture | décidés | non décidés | BL-013 |
| 0.5 | Date de J1 et seuils des gates | validés | non validés | BL-016 |

**Décide :** la propriétaire. **Si ROUGE :** les agents préparent, mais n'envoient rien à l'extérieur.

### G1 — Fin de la semaine 1 (J7) : accès fournisseur et hypothèses critiques identifiés (BP §13 S1)

| # | Critère | VERT | ORANGE | ROUGE |
|---|---|---|---|---|
| 1.1 | Demandes fournisseurs envoyées (BP §2 : 3 prioritaires FR + 2 priorité 2) | 5/5 | 3/5 (les 3 FR) | < 3 |
| 1.2 | Parcours d'accès connu par fournisseur (canal, pièces exigées, acceptation d'une entreprise suisse) | 5/5 | 3/5 | < 3 |
| 1.3 | Grille concurrence : références relevées × boutiques | ≥ 10 × 3 | ≥ 6 × 3 | < 6 |
| 1.4 | Fiduciaire mandatée ou rendez-vous fixé avant J10 | oui | rendez-vous après J10 | aucune |
| 1.5 | Hypothèses critiques listées avec date de levée (entité, TVA, budget, J1) | toutes | — | manquantes |

**Décide :** l'agent 01 ; escalade si un critère est ROUGE. **Issue ROUGE type :** REPORT de G2 d'une semaine.

### G2 — J15 : flux fournisseur et marges pilote identifiés (BP §9 J1-15 ; §13 S2 « calculs contrôlés contre facture/devis »)

| # | Critère | VERT | ORANGE | ROUGE |
|---|---|---|---|---|
| 2.1 | Fournisseur FR ayant confirmé **par écrit** qu'il accepte une entreprise suisse et livre en Suisse (facture, pays d'expédition, Incoterm) | ≥ 1 | réponse positive orale ou partielle | aucun |
| 2.2 | Devis écrit sur le panier pilote, avec port et conditions | ≥ 1 devis couvrant ≥ 10 références | < 10 références chiffrées | aucun devis |
| 2.3 | Flux de données | exemple de fichier (CSV/XLSX/XML) ou documentation d'API reçus | tarif réel non structuré + exemple promis par écrit (écart EC-09) | rien |
| 2.4 | Marges pilote **(hypothèse)** : références dont le prix plancher (m = 20 %) ≤ référence marché × 1,10 | ≥ 8 | ≥ 8 en comptant ≤ 3 références « À REVOIR » (au prix marché : contribution ≥ 12 % et ≥ 8 CHF) | < 8 |
| 2.5 | Contrôle des calculs : comparateur = moteur `pokeshop.pricing` sur les lignes chiffrées | 0 écart > 0,01 CHF | — | écart non expliqué |
| 2.6 | Grille concurrence | ≥ 10 références × 5 boutiques | ≥ 10 × 4 | moins |
| 2.7 | Entretiens clients (BP §9 : 10) | ≥ 10 | 7 à 9 | < 7 |
| 2.8 | Statut TVA | décision écrite de la fiduciaire | profil provisoire documenté | inconnu |

**Décide :** l'agent 01 ; escalade si ROUGE. **Issues :** GO = P2 complète (site, DA, connecteur). GO sous conditions = DA et site test seulement, sourcing prolongé de 14 jours. REPORT si 2.1 ou 2.2 est ROUGE : pas de dépense site au-delà de l'abonnement, gate rejoué à J29. Un **STOP** est proposé si, à J29, aucun fournisseur n'a donné d'accès (BP §13 : « reporter si les tarifs ne sont pas accessibles »).

### G3 — J30 : GO achat du stock pilote (conditions de lancement du BP + §9 J16-30 + §13 S3-4)

Les six conditions de lancement du BP, rendues mesurables :

| # | Condition BP | VERT | ORANGE | ROUGE |
|---|---|---|---|---|
| 3.1 | « Au moins un fournisseur FR accepté avec un flux exploitable » | compte ouvert + conditions écrites + import réel sans anomalie critique | compte ouvert + import assisté validé + fichier promis | pas de compte |
| 3.2 | « Une seconde source identifiée » (EC-06) | devis écrit + due diligence sans critère éliminatoire | devis sans due diligence | rien |
| 3.3 | « Des marges positives sur une sélection pilote » | 8 à 12 références en stock, chacune ≥ 12 % et ≥ 8 CHF par commande au prix public prévu ; contribution moyenne pondérée ≥ 20 % du CA net (cible §5) | moyenne entre 12 % et 20 % | une référence sous le plancher dur, ou moins de 8 références |
| 3.4 | « Des paiements et une expédition testés » | 5 scénarios de paiement OK (réussi, refusé, doublon, remboursement, versement reçu) en carte et TWINT ; colis test et retour test livrés avec suivi | TWINT pas encore actif, carte OK | paiement ou colis non testé |
| 3.5 | « Une trésorerie qui finance le stock et les remboursements » | prévision sur 13 semaines **avec** l'achat : cash disponible ≥ 1 600 CHF chaque semaine ; aucune précommande sans allocation ferme | réserve tenue avec un achat réduit (≤ 1 500 CHF) | réserve entamée |
| 3.6 | « Des règles d'automatisation validées » | règles de prix v1 approuvées (BL-084) ; seuils du stop-loss et règles de prix **signés** au coffre (BL-181) ; stop-loss testés (BL-085) ; **20 synchronisations sans erreur critique** (§13 S3-4), lues dans le moteur : `GET /sync/history`, `consecutive_clean_runs` ≥ 20 = 20 cycles PROPRES consécutifs sur 20 livraisons fournisseur **réelles et distinctes** (fichiers non FICTIFS, datés, de contenu différent, catalogue enregistré ; un cycle FICTIF, rejoué ou VIDE ne compte pas) ; recette du parcours OK (BL-099), dont **R-I04 OK** (restauration vérifiée, `db/backup.sh etat` code 0, copie hors de la machine) ; textes légaux validés (BL-096) | textes légaux en relecture, sans précommande ; seuils non signés (les valeurs les plus strictes s'appliquent) | une erreur critique sur les 20 dernières synchronisations |
| 3.7 | §9 J16-30 « Paiement et stock sans erreur critique » | 0 erreur critique | — | ≥ 1 |

**Décide :** la propriétaire (BL-107). **Issues :**

- **GO** : achat jusqu'à 3 000 CHF selon `ASSORTIMENT_PILOTE.md`, avec 750 CHF maximum par extension.
- **GO sous conditions** : achat réduit à 1 500 CHF maximum, sur les références VERTES uniquement.
- **REPORT** : si 3.1, 3.4 ou 3.6 est ROUGE.
- **Niveau 2 après G3** (C14, ≈ J38) : en plus de la recette signée et du point zéro posé, revue adverse de sécurité relancée et sans critical/high ouvert (BL-200, §1).
- **STOP** proposé si, sur au moins 10 références comparables, le prix rentable dépasse la référence marché de plus de 10 % pour **plus de 50 %** d'entre elles (BP §13 : « le prix rentable dépasse systématiquement le marché »), ou si le flux amont reste non fiabilisable à J45.

### G4 — J45 : premières commandes livrées, contribution positive → GO du test publicitaire (BP §9 J31-45 ; §13 S5-6)

| # | Critère | VERT | ORANGE | ROUGE |
|---|---|---|---|---|
| 4.1 | Commandes payées et livrées correctement (montant, contenu, suivi) | ≥ 5 payées dont ≥ 3 livrées **(hypothèse)** | 1 à 4 payées | 0 livrée |
| 4.2 | Contribution de chaque commande livrée | ≥ 12 % et ≥ 8 CHF | une commande sous le seuil, expliquée | plusieurs sous le seuil |
| 4.3 | Contribution cumulée des commandes (avant pub, avant charges fixes) | > 0 | — | ≤ 0 |
| 4.4 | Survente, erreur critique | 0 | — | ≥ 1 |
| 4.5 | Cash disponible avant le test (réserve + budget pub) | ≥ 1 600 + plafond pub engagé | — | < 1 600 (le stop-loss cash interdit la pub) |
| 4.6 | Revue adverse de sécurité avant le niveau 3 (BL-201, `REVUE_SECURITE.md` §5) | relancée sur la version mise en service, aucun finding critical/high ouvert, risques résiduels « avant le niveau 3 » traités ou acceptés par écrit | — | non relancée, ou un finding critical/high ouvert : niveau 3 non activé (REPORT du passage de niveau) |

**Décide :** la propriétaire (BL-123), avec activation du niveau 3 (BL-132). Aucune campagne ne démarre avant la recette du connecteur publicitaire (rôle `connecteur-publicite`, BL-198, J48) **et** la revue adverse limitée à son diff, sans critical/high ouvert (BL-203, J49) : la dépense pub n'est jamais déclarée par l'agent 10, et ce nouvel écrivain d'une entrée du stop-loss pub n'entre jamais en service sans revue. **Recommandation saisonnière (EC-10) :** le Black Friday tombe le 27.11.2026 (J54). Démarrer le test **après le 30.11** (option A, recommandée : premier jour complet de données le 30.11, J57) ou dès J50, après le connecteur et sa revue, avec le plafond quotidien divisé par deux jusqu'au 30.11 (option B). Le choix fixe la date de G5.

### G5 — J60 (option B) / J64, 7.12 (option A, recommandée) : CAC inférieur à la contribution disponible (BP §9 J46-60)

La décision exige **7 jours complets** de données. Option B (test dès J50, plafond réduit) : décision à J60 (3.12). Option A (test démarré le 30.11, J57) : à J60, il n'y aurait que 4 jours de données ; la décision tombe donc à **J64 (7.12)**, sur J57-J63, hors de la fenêtre J46-60 du BP (écart EC-22).

On compare le CAC (calculé sur les commandes payées, nettes d'annulations et de remboursements, produits offerts et commissions des créateurs compris) à la contribution par commande **avant** acquisition :

| Situation (7 jours glissants) | Statut | Décision |
|---|---|---|
| CAC ≤ contribution avant acquisition − 8 CHF (le panier reste au-dessus du plancher dur) | VERT | Poursuivre ; le budget suivant se construit sur cette preuve |
| contribution − 8 CHF < CAC ≤ contribution | ORANGE | Réduire le plafond quotidien, changer de création ou d'offre, rejouer 7 jours |
| CAC > contribution | ROUGE | Campagne coupée (le stop-loss pub s'en charge automatiquement) |

Ordre de grandeur avec les hypothèses du BP §10 (panier de 95 CHF, contribution avant acquisition de 19,33 CHF) : le VERT s'arrête à un CAC de **11,33 CHF** et la coupure intervient au-delà de 19,33 CHF (voir l'harmonisation proposée par l'agent finance, EC-F-04, EC-F-05 et EC-F-10). **Décide :** la propriétaire (BL-136), à J60 (option B) ou J64 (option A).

### G6 — J90 : bilan des 90 jours (BP §9 J61-90 « rotation et trésorerie compatibles avec croissance » ; §13 S7-12)

| # | Critère | VERT | ORANGE | ROUGE |
|---|---|---|---|---|
| 6.1 | Stock pilote écoulé en valeur de coût (point intermédiaire de l'indicateur du §1) | ≥ 40 % **(hypothèse)** | 20 à 40 % | < 20 % |
| 6.2 | Extensions sans vente depuis 45 j (stop-loss extension) | 0 | 1, avec démarque proposée | ≥ 2 |
| 6.3 | Trésorerie à 13 semaines **avec** les réassorts prévus | cash disponible ≥ 1 600 chaque semaine | réserve tenue sans réassort | réserve entamée |
| 6.4 | Automatisation stable (§13 S7-12) | 0 incident critique sur 14 j | incidents résolus en < 24 h | incident critique ouvert |
| 6.5 | Deuxième fournisseur actif (§13 S7-12) | import ou commande réalisés | compte ouvert | rien |
| 6.6 | Étoile polaire : contribution nette des 4 dernières semaines | > 0 | entre −100 et 0 CHF | < −100 CHF **(hypothèse)** |
| 6.7 | Revue adverse de sécurité avant le niveau 4 (BL-202, seulement si le niveau 4 est envisagé) | relancée, aucun finding critical/high ouvert, risques résiduels « avant le niveau 4 » traités ou acceptés par écrit | niveau 4 non demandé | un finding critical/high ouvert : niveau 4 non activé |

**Décide :** l'agent 01 rédige le bilan (BL-147) ; aucune décision n'est requise, sauf si un critère est ROUGE (escalade).

### G7 — J_V1 + 60 : poursuivre, reporter ou arrêter (BP §1 et §13)

J_V1 est la date de la première commande payée. La décision tombe à J_V1 + 60, soit entre J91 et J105 si l'ouverture douce a lieu entre J31 et J45 (écart EC-07).

**Les quatre indicateurs du BP §1, sur les 60 premiers jours de vente :**

| # | Indicateur | Seuil BP | Mesure |
|---|---|---|---|
| 7.1 | Commandes payées | ≥ 30 | nettes d'annulations |
| 7.2 | Contribution après publicité | > 0 | cumul sur 60 j, avant charges fixes |
| 7.3 | Survente | 0 | incidents |
| 7.4 | Stock pilote écoulé en valeur de coût | ≥ 50 % | coût historique des unités vendues / coût du stock pilote |

**Les conditions du BP §13 « Poursuivre si… » :**

| # | Condition | Mesure proposée **(hypothèse)** |
|---|---|---|
| 7.5 | « Le sourcing FR est accepté » | ≥ 1 fournisseur actif, plus une 2e source en cours d'ouverture |
| 7.6 | « Les prix restent compétitifs après coûts » | ≥ 70 % des références actives à un prix public ≤ référence marché × 1,10 |
| 7.7 | « Le système évite les ventes non couvertes » | 0 survente et 0 vente sous le plancher dur sans validation |
| 7.8 | « Les premières commandes contribuent positivement » | 7.2 VERT |

**L'étoile polaire et sa trajectoire :**

| # | Mesure | Pourquoi |
|---|---|---|
| 7.9 | Contribution nette cumulée depuis S1 et moyenne hebdomadaire des 4 dernières semaines | Décision sur l'étoile polaire |
| 7.10 | Commandes par mois sur les 4 dernières semaines rapportées au seuil de 31 commandes/mois (BP §10) | Le rythme du §1 (30 commandes en 60 j, ≈ 15/mois) est **déficitaire par construction** (≈ −230 CHF/mois, EC-F-07) : réussir le test ne suffit pas, il faut une trajectoire vers 31/mois |

**Matrice de décision :**

| Décision | Conditions |
|---|---|
| **POURSUIVRE** | 7.1 à 7.4 VERTS, 7.5 à 7.8 VERTS, moyenne hebdomadaire 7.9 > 0 **ou** 7.10 ≥ 31 commandes/mois. Le budget suivant se construit sur la preuve (BP §9). |
| **AJUSTER** (poursuivre 30 j avec un levier nommé : assortiment, prix, canal, fournisseur) | 3 indicateurs sur 4 en 7.1-7.4, aucune condition 7.5-7.8 ROUGE, et étoile polaire en amélioration sur 4 semaines. |
| **REPORTER** (BP §13) | Tarifs non accessibles, **ou** prix rentable au-dessus du marché pour plus de 50 % des références, **ou** flux amont non fiabilisable. Effet : plus d'achat ; le stock local réel continue d'être vendu ; recherche d'une nouvelle source. |
| **ARRÊTER** | Stop-loss global déclenché et non réarmé, **ou** au plus 1 indicateur sur 4 et étoile polaire cumulée en baisse sur 4 semaines. Effet : démarque du stock restant selon les règles, arrêt des abonnements, information des inscrits. |

**Décide :** la propriétaire (BL-150). « Un joli site ne constitue pas un feu vert commercial » (BP §13).

## 3. Synthèse des gates

| Gate | Date (J1 = lun. 5.10.2026) | Question | Décideur | Livrable |
|---|---|---|---|---|
| G0 | J1 (5.10) | Les agents peuvent-ils agir ? | Propriétaire | Mandat signé |
| G1 | J7 (11.10) | Les accès et les hypothèses sont-ils identifiés ? | Agent 01 (escalade si ROUGE) | Fiche G1 |
| G2 | J15 (19.10) | Flux et marges pilote sont-ils identifiés ? | Agent 01 (escalade si ROUGE) | Fiche G2 + comparateur |
| G3 | J30 (3.11) | Achète-t-on le stock ? | Propriétaire | Fiche G3 + panier final |
| G4 | J45 (18.11) | Lance-t-on le test pub ? | Propriétaire | Fiche G4 |
| G5 | J60 (3.12) option B ; J64 (7.12) option A, recommandée | La pub est-elle rentable ? | Propriétaire | Fiche G5 |
| G6 | J90 (2.1.2027) | Bilan 90 jours | Agent 01 | Bilan |
| G7 | J_V1 + 60 (≈ 3 au 17.1.2027) | Poursuivre, ajuster, reporter ou arrêter ? | Propriétaire | Dossier de décision |

## 4. Modèle de fiche gate (à copier)

```markdown
# Fiche gate Gx — {{date}}
Rédigée par : Agent 01 · Chiffres : Agent 05 · Tests certifiés : Agent 12

| # | Critère | Mesure constatée | Statut (VERT/ORANGE/ROUGE) | Preuve (chemin, lien, date) |
|---|---|---|---|---|
| x.1 | … | … | … | … |

Stop-loss actifs à date : aucun / {{liste}}
Étoile polaire : cumul {{CHF}} ; 4 dernières semaines {{CHF}}
Revue adverse de sécurité (si le gate relève un niveau d'autonomie) : round {{n}} du {{date}} ; critical/high ouverts : {{0}} ; risques résiduels acceptés : {{RS-xx}}
Issue proposée : GO / GO sous conditions / REPORT / STOP
Conditions, actions et dates (si GO sous conditions ou REPORT) : …
Décision de la propriétaire (si requise) : … — date, signature
```

## Validation humaine requise

- [ ] Valider (ou amender) chaque seuil marqué **(hypothèse)** : 2.4, 4.1, 6.1, 6.6, 7.5, 7.6 et la définition de l'« erreur critique ».
- [ ] Valider la date de G7 (J_V1 + 60) à la place d'une décision à J90 (écart EC-07).
- [ ] Valider le principe d'une décision par l'agent 01 pour G1, G2 et G6, avec escalade uniquement en cas de ROUGE.
- [ ] Choisir la règle de démarrage du test publicitaire autour du Black Friday : après le 30.11 (option A, G5 à J64), ou plafond quotidien divisé par deux (option B, G5 à J60).
- [ ] Confirmer que le GO sous conditions de G3 autorise un achat réduit à 1 500 CHF.
- [ ] Confirmer avec l'agent gouvernance que les seuils de stop-loss cités ici sont identiques à `STOP_LOSS.md`.
- [ ] Valider la règle du §1 : aucun niveau d'autonomie 2, 3 ou 4 sans revue adverse de sécurité relancée et sans critical/high ouvert (`REVUE_SECURITE.md` §5) ; critères 4.6 et 6.7.
