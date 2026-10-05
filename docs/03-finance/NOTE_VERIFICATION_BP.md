# Note de vérification du BP — volet finance

> Objet : recalcul chiffre par chiffre des §3, §4 et §10 du business plan « Boutique Pokémon JCC FR en Suisse » (version du 4 octobre 2026), puis lecture de ces chiffres sous l'angle de l'**étoile polaire** (contribution nette cumulée) et des **stop-loss** du mandat.
> Auteur : agent finance. Date de référence : 4 octobre 2026. Montants en CHF.
> Reproductible : `python -m pytest -q tests/test_forecast.py tests/test_treasury.py` et `pokeshop.forecast.verify_against_bp()`.

## 1. En bref

| Constat | Détail |
|---|---|
| **38 chiffres recalculés** | 35 ✅ conformes · 2 ⚠️ écarts d'arrondi (seuils 31 et 181) · 1 ⚠️ écart de 1 CHF (CA HT développement 17 577) |
| **Mécanique du BP** | Juste. Aucun écart ne change une conclusion. |
| **Étoile polaire** | Par mois, la contribution nette = le « résultat avant rémunération » du BP : **53 / 933 / 2 467 CHF**. Avec 4 semaines de charges fixes avant l'ouverture, le cumul part de **−369 CHF** et redevient positif en semaine **34** (prudent), **6** (central) ou **5** (développement). |
| **Stop-loss global** | Seuil : perte cumulée de **1 600 CHF** (20 % de 8 000). Jamais atteint dans les 3 scénarios du BP. Au rythme du jalon de validation (≈ 15 commandes/mois, CAC 8), il se déclenche en **semaine 28**. |
| **Stop-loss cash** | Le budget de 8 000 CHF laisse 2 100 CHF en banque (dont la réserve de 1 600 et le test pub de 500). Les charges fixes d'avant l'ouverture ne sont pas budgétées : dans l'exemple FICTIF, la réserve est entamée dès la **semaine 5** et le test publicitaire tombe en stop-loss. |
| **Risque n° 1** | Le stock de 3 000 CHF couvre **14,6 jours** de ventes du scénario central (achats consommés 6 152 CHF HT/mois). |
| **Risque n° 2** | Le scénario central annualisé (114 000 CHF TTC) **dépasse le seuil TVA** de 100 000 CHF. |
| **Risque n° 3** | Temps non rémunéré : **1,19 CHF/h** implicite au scénario prudent, 15,64 CHF/h au central (hypothèse fictive de 15 min de préparation par colis). |
| **Incohérence §5/§10** | 22 % de contribution *avant* acquisition donne **15,2 %** après CAC au central, sous la cible de 20 % du §5. Les deux cas de sensibilité passent **sous le plancher dur de 8 CHF/commande**. |

## 2. Méthode

- Calcul en `decimal.Decimal`, sans arrondi intermédiaire. Arrondi « demi supérieur » uniquement à l'affichage : franc entier pour les totaux, centime pour les montants par commande, comme dans le BP.
- **Exact** = valeur non arrondie. **Recalcul** = valeur arrondie selon la convention du BP.
- Statut : ✅ identique au BP · ⚠️ arrondi = écart dû à une convention d'arrondi (BP reproduit avec sa convention) · ⚠️ écart = différence non expliquée par un arrondi.
- Double contrôle : les mêmes formules sont écrites en formules Excel vivantes dans `modele_financier.xlsx`. Le classeur est recalculé par LibreOffice 24.2 en mode headless et relu avec `openpyxl` (`data_only=True`). Les tests vérifient que Python et le classeur donnent les mêmes valeurs, semaine par semaine pour l'étoile polaire.

## 3. Tableau chiffre par chiffre

| Réf. | BP | Chiffre | Valeur BP | Exact | Recalcul | Statut |
|---|---|---|---:|---:|---:|---|
| B1 | §3 | Budget initial total | 8 000 | 8 000,00 | 8 000 | ✅ |
| B2 | §3 | Charges fixes mensuelles (180 + 120 + 100) | 400 | 400,00 | 400 | ✅ |
| S0 | §10 | Panier HT (95 TTC / 1,081) | 87,88 | 87,8816 | 87,88 | ✅ |
| S1.1 | §10 | CA produits TTC — prudent | 3 800 | 3 800,00 | 3 800 | ✅ |
| S1.2 | §10 | CA produits HT — prudent | 3 515 | 3 515,26 | 3 515 | ✅ |
| S1.3 | §10 | Contribution avant acquisition — prudent | 773 | 773,36 | 773 | ✅ |
| S1.4 | §10 | Acquisition totale — prudent (40 × 8) | 320 | 320,00 | 320 | ✅ |
| S1.5 | §10 | Résultat avant rémunération — prudent | 53 | 53,36 | 53 | ✅ |
| S2.1 | §10 | CA produits TTC — central | 9 500 | 9 500,00 | 9 500 | ✅ |
| S2.2 | §10 | CA produits HT — central | 8 788 | 8 788,16 | 8 788 | ✅ |
| S2.3 | §10 | Contribution avant acquisition — central | 1 933 | 1 933,40 | 1 933 | ✅ |
| S2.4 | §10 | Acquisition totale — central (100 × 6) | 600 | 600,00 | 600 | ✅ |
| S2.5 | §10 | Résultat avant rémunération — central | 933 | 933,40 | 933 | ✅ |
| S3.1 | §10 | CA produits TTC — développement | 19 000 | 19 000,00 | 19 000 | ✅ |
| S3.2 | §10 | CA produits HT — développement | **17 577** | 17 576,32 | **17 576** | ⚠️ écart |
| S3.3 | §10 | Contribution avant acquisition — développement | 3 867 | 3 866,79 | 3 867 | ✅ |
| S3.4 | §10 | Acquisition totale — développement (200 × 5) | 1 000 | 1 000,00 | 1 000 | ✅ |
| S3.5 | §10 | Résultat avant rémunération — développement | 2 467 | 2 466,79 | 2 467 | ✅ |
| U1 | §10 | Contribution/commande avant acquisition (central) | 19,33 | 19,3340 | 19,33 | ✅ |
| U2 | §10 | Contribution/commande après CAC 6 (central) | 13,33 | 13,3340 | 13,33 | ✅ |
| T1 | §10 | Seuil cash d'exploitation (commandes/mois) | **31** | 29,9986 | **30** | ⚠️ arrondi |
| T2 | §10 | Seuil avec 2 000 CHF de rémunération | **181** | 179,9917 | **180** | ⚠️ arrondi |
| T3 | §10 | CA TTC annualisé (central) | 114 000 | 114 000,00 | 114 000 | ✅ |
| V1 | §10 | Contribution/commande à 15 % | 13,18 | 13,1822 | 13,18 | ✅ |
| V2 | §10 | Après CAC 6 à 15 % | 7,18 | 7,1822 | 7,18 | ✅ |
| V3 | §10 | Seuil à 15 % (commandes) | 56 | 55,6929 | 56 | ✅ |
| V4 | §10 | Contribution après CAC 15 (22 %) | 4,33 | 4,3340 | 4,33 | ✅ |
| V5 | §10 | Seuil avec CAC 15 (commandes) | 93 | 92,2946 | 93 | ✅ |
| K1 | §10 | CA net à 100 commandes | 8 788 | 8 788,16 | 8 788 | ✅ |
| K2 | §10 | Achats consommés HT/mois (70 %) | 6 152 | 6 151,71 | 6 152 | ✅ |
| P1 | §4 | Prix plancher (assujetti) | 208,79 | 208,79498 | 208,79 | ✅ |
| P2 | §4 | Prix public arrondi | 209,90 | 209,90 | 209,90 | ✅ (règle à préciser, §4.4) |
| P3 | §4 | Vente nette à 199,90 | 184,92 | 184,9214 | 184,92 | ✅ |
| P4 | §4 | Frais de paiement à 199,90 | 5,30 | 5,2975 | 5,30 | ✅ |
| P5 | §4 | Contribution à 199,90 | 30,62 | 30,6239 | 30,62 | ✅ |
| P6 | §4 | Contribution en % du CA net à 199,90 | 16,56 % | 16,5605 % | 16,56 % | ✅ |
| P7 | §4 | C non assujetti (140 × 1,081) | 151,34 | 151,3400 | 151,34 | ✅ |
| P8 | §4 | Prix plancher non assujetti (t = 0) | 207,28 | 207,2774 | 207,28 | ✅ |

Pour les seuils (T1, T2, V3, V5), la colonne « Exact » donne le quotient avant arrondi au-dessus. Le seuil retenu est l'entier supérieur.

## 4. Écarts détaillés

### 4.1 Seuil d'exploitation : 31 (BP) contre 30 (exact)

| Méthode | Contribution après CAC | 400 / contribution | Seuil |
|---|---:|---:|---:|
| BP : contribution arrondie au centime | 13,33 | 30,0075 | **31** |
| Exact | 13,33395 | 29,9986 | **30** |

À 30 commandes, la couverture exacte des 400 CHF ne dépasse que de **0,02 CHF**. Le seuil « exact » est donc fragile.
**Recommandation :** garder **31**, la valeur prudente du BP, et indiquer la méthode (« contribution arrondie au centime »). Le classeur affiche les deux (`Seuil & sensibilité`, lignes 10 à 13).

### 4.2 Seuil avec rémunération : 181 (BP) contre 180 (exact)

Même mécanique : 2 400 / 13,33 = 180,05 ⇒ 181 ; 2 400 / 13,33395 = 179,99 ⇒ 180.
**Recommandation :** garder 181. Ce seuil exclut les cotisations sociales et les autres coûts de la rémunération (le BP le dit). Le vrai seuil est donc plus haut, à chiffrer avec la fiduciaire.

### 4.3 CA HT développement : 17 577 (BP) contre 17 576

19 000 / 1,081 = 17 576,32 ⇒ 17 576, et 200 × 87,88 = 17 576 aussi. Aucune convention d'arrondi ne donne 17 577. L'écart (1 CHF, 0,006 %) n'a **aucun effet** : la contribution (3 867) et le résultat (2 467) publiés correspondent à la valeur exacte.
**Recommandation :** corriger le tableau du BP en 17 576. Le classeur l'affiche (`Scénarios`, ligne 41 : « ÉCART -1 CHF »).

### 4.4 Règle d'arrondi du prix public : 208,79 → 209,90

- Le BP passe de 208,79 à **209,90**. La SPEC (`round_up_retail`, « prochain X,90 ») donnerait **208,90**.
- 209,90 correspond à la règle « terminaison 9,90, pas de 10 CHF ». Le classeur (`Prix plancher`, lignes 19 à 22) rend le pas et la terminaison paramétrables et affiche les deux lectures du BP.
- Avec un pas de 10 CHF, un petit produit dont le plancher serait 5,40 CHF (illustration, pas un prix) s'afficherait à 9,90 CHF (+83 %). Il faut une **règle par tranche de prix**.
- **Règle appliquée par le moteur** : la grille par tranches `rounding_tiers` de `config/pricing_rules.v1.yaml` (< 10 CHF → X,50/X,90 ; 10 à 99,99 → X,90 ; ≥ 100 → X4,90/X9,90), qui reproduit 208,79 → 209,90. Le classeur la reproduit en `Prix plancher` ligne 26 (formule construite depuis le fichier de règles), et c'est ce prix qu'utilise la colonne « Prix public arrondi » du contrôle de contribution. Les lectures du BP (lignes 19 à 22) diffèrent du moteur hors du cas du BP (coût 50 CHF : 89,90 contre 83,90).
- 209,90 donne 20,41 % de contribution (cible atteinte). 208,90 donne 20,04 %, ce qui atteint aussi la cible.

### 4.5 Marge d'arrondi du prix plancher

Le plancher exact vaut 208,79498. L'arrondi « demi supérieur » au centime donne 208,79 **à 0,00002 CHF près**. Pour un *plancher*, un arrondi au centime supérieur (208,80) serait plus cohérent. Sans effet pratique ici, puisque le prix public est de toute façon arrondi vers le haut.

## 5. Cohérence entre sections du BP

| Point | Constat | Statut |
|---|---|---|
| Contribution §10 (22 % *avant* acquisition) vs cible §5 (20 % *après* acquisition, A dans la formule) | Après CAC : prudent 12,9 %, central 15,2 %, développement 16,3 % du CA HT. Les scénarios supposent donc des prix **sous la cible** du §5, mais au-dessus du plancher dur (≥ 12 % et ≥ 8 CHF). | ⚠️ à arbitrer |
| Sensibilités §10 vs plancher dur §5 | 15 % ⇒ 7,18 CHF et CAC 15 ⇒ 4,33 CHF par commande : **sous 8 CHF**. Le stop-loss produit doit bloquer ou alerter ces paniers. | ⚠️ cohérence |
| 22 % de contribution vs 70 % de coût produit | Il reste 8 % du CA HT, soit 7,03 CHF/commande, pour le paiement (2,68), le SAV (1,00) et l'emballage (3,36 implicites). C'est plausible au regard du §4 (L = 3, R = 1). Le classeur affiche ce solde (`Étoile polaire`, E12) et signale toute incohérence. | ✅ cohérent |
| Test acquisition §3 (500) vs jours 46 à 60 §9 (500 max) | Identiques. | ✅ |
| Répartition du stock §1 | 25 + 25 + 20 + 20 + 10 = 100 %, soit 750 / 750 / 600 / 600 / 300 CHF. Plafond par extension : 750 CHF. | ✅ |
| Objectif de validation §1 (30 commandes en 60 jours) vs seuil §10 (31/mois) | Le test vise environ 15 commandes/mois, la moitié du seuil. La phase pilote est donc **déficitaire par construction** : 15 × 13,33 − 400 ≈ −230 CHF/mois. C'est cohérent avec un test, mais à financer, et cela mène au stop-loss global (§6). | ⚠️ à assumer |
| Budget §3 vs charges mensuelles §3 | Le budget de 8 000 CHF ne contient pas de ligne « charges fixes avant les premières ventes ». Les ventes démarrent vers les jours 31 à 45 (§9), soit 1 à 1,5 mois de charges (400 à 600 CHF), imputées sur la réserve de 1 600 CHF. On ne sait pas si la ligne « Site et automatisation 1 500 » couvre les abonnements. | ⚠️ ambiguïté |
| Hypothèse TVA §10 (assujetti) vs seuil §4 | Le tableau ne couvre que le cas assujetti. Le prudent annualisé (45 600 TTC) est sous le seuil. Le central (114 000 TTC, 105 458 HT) est au-dessus. Le cas « non assujetti » n'est pas chiffré au §10 : prix sans TVA à reverser mais TVA d'achat non récupérable. | ⚠️ à compléter |

## 6. Étoile polaire et stop-loss du mandat

### 6.1 Définition retenue

Contribution nette = ventes nettes HT − coût historique − paiement − logistique − SAV − acquisition − charges fixes, cumulée chaque semaine depuis la semaine 1 du lancement. Les dépenses de lancement (site, DA, administration, emballages initiaux : 2 900 CHF) et le stock encore détenu n'y entrent pas : ce sont des décaissements, suivis en trésorerie.

Projection hebdomadaire d'un scénario du BP §10 (`project_north_star`, feuille `Étoile polaire`) : volumes mensuels × 12/52, charges fixes dès la semaine 1. Les 78 % de coûts variables sont ventilés : coût produit 70 % du CA HT, paiement 2,5 % × 95 + 0,30 = 2,68 CHF, SAV 1 CHF, emballage implicite 3,36 CHF par commande.

### 6.2 Résultats (ouverture des ventes en semaine 5, BP §9)

| Scénario | Contribution nette / semaine en régime | Creux du cumul | Cumul redevenu positif | Cumul à 52 semaines | Jalon §1 (8 semaines) |
|---|---:|---:|---:|---:|---|
| Prudent (40 cmd, CAC 8) | 12,31 | −369,23 (sem. 4) | semaine 34 | 221,81 | 73,8 cmd ✅ |
| Central (100 cmd, CAC 6) | 215,40 | −369,23 (sem. 4) | semaine 6 | 9 969,91 | 184,6 cmd ✅ |
| Développement (200 cmd, CAC 5) | 569,26 | −369,23 (sem. 4) | semaine 5 | 26 955,21 | 369,2 cmd ✅ |
| Rythme du jalon §1 (15 cmd, CAC 8) | −53,07 | — | jamais | **gel en semaine 28** (−1 643) | 27,7 cmd ❌ |

Contrôle : sur 52 semaines dès la semaine 1, le cumul vaut exactement 12 × le résultat mensuel du BP (640,30 / 11 200,74 / 29 601,48). Le classeur le vérifie (`Étoile polaire`, G24).

Au prudent, le cumul reste négatif pendant 8 mois. Un écart de 13 CHF par semaine suffit à le faire basculer : le scénario prudent est un plateau, pas une trajectoire.

### 6.3 Stop-loss : ce que les chiffres du BP impliquent

| Niveau | Seuil | Constat chiffré | Statut |
|---|---|---|---|
| Produit | < 12 % ou < 8 CHF/commande | Les deux cas de sensibilité du BP (7,18 et 4,33 CHF) sont sous le seuil | ⚠️ |
| Extension | > 25 % du budget stock | 750 CHF par extension au lancement (25 % de 3 000 CHF) ; le nombre d'articles dépendra des devis réels | ✅ calculé |
| Publicité | CAC > contribution/commande | Contribution avant acquisition 19,33 CHF : la coupure n'intervient qu'à CAC > 19,33. Or le plancher produit (8 CHF après acquisition) est franchi dès CAC > **11,33**. Entre 11,33 et 19,33 CHF, la campagne continue alors que les paniers passent sous le plancher. | ⚠️ à harmoniser |
| Cash | Cash disponible < 1 600 | Budget dépensé : 8 000 − 2 900 − 3 000 = 2 100 CHF, dont 500 de test pub. Chaque mois de charges fixes avant l'ouverture (400 CHF) entame la réserve. Exemple FICTIF : stop-loss en semaines 6, 7, 8 et 10 ; 300 CHF de publicité à bloquer. | ⚠️ budget |
| Global | Perte cumulée ≥ 1 600 (20 % × 8 000) | Jamais atteint dans les scénarios du BP ; atteint en semaine 28 au rythme du jalon de validation | ✅ mesurable |
| Temps | 60 j sans seuils de validation | Le jalon §1 (30 commandes) correspond à ≈ 15 commandes/mois : en dessous, le dossier continuer/ajuster/arrêter arrive vers la semaine 13 (ouverture en semaine 5 + 8 semaines) | ✅ calculable |

Le stop-loss global n'a de sens que sur la contribution nette (exploitation). Calculé sur la perte cash, il se déclencherait avant la première vente : les 2 900 CHF de dépenses de lancement dépassent à eux seuls 1 600 CHF.

## 7. Risques

| # | Risque | Chiffres | Conséquence | Mesure proposée |
|---|---|---|---|---|
| R1 | **Le stock de 3 000 CHF ne finance pas un mois central** | Achats consommés 6 152 CHF HT/mois ; couverture 48,8 % = **14,6 jours** ; manque 3 152 CHF pour un mois | Ruptures, ou trésorerie absorbée par les réassorts | Réassort hebdomadaire plafonné par le cash disponible (classeur 13 semaines) ; montée en volume progressive |
| R2 | **Besoin en fonds de roulement** | Avec des délais FICTIFS (14 j de prépaiement, 30 j de stock, 7 j de versement PSP, 0 j de crédit), BFR central ≈ **11 239 CHF** contre 4 600 mobilisables (stock + réserve), soit ≈ 6 639 CHF à financer | Le scénario central n'est pas finançable avec le budget pilote sans crédit fournisseur ni apport | Obtenir les vrais délais (devis, contrat PSP) ; négocier un paiement à terme ; décider d'un apport ou d'un plafond de croissance |
| R3 | **Seuil TVA** | Central annualisé 114 000 TTC ; TVA contenue ≈ 712 CHF/mois au central | Assujettissement obligatoire à anticiper ; la TVA encaissée n'est pas du cash disponible | Examen fiduciaire **avant** l'ouverture, sur toute l'activité de l'entité exploitante |
| R4 | **Temps non rémunéré** | Supervision 26 à 43 h/mois (6 à 10 h/sem. × 52/12) + colis. Rémunération implicite : prudent 1,19 CHF/h, central 15,64, développement 29,14 (avant impôts et charges sociales ; 15 min/colis = hypothèse fictive) | Une activité « cash positive » peut ne pas payer le travail | Second compte de résultat avec le temps valorisé ; mesurer le temps réel par colis |
| R5 | **Fragilité de la contribution** | 22 % → 15 % : seuil de 31 à 56 commandes ; CAC de 6 à 15 : seuil de 31 à 93 | Une erreur de coût, de livraison ou de CAC annule le bénéfice | Contrôle de la marge réelle par facture (BP §12) ; stop-loss pub aligné sur le plancher produit (CAC max 11,33 au central) |
| R6 | **Réserve, précommandes et stop-loss cash** | Exemple FICTIF 13 semaines (réserve 1 600) : solde au plus bas **1 273 CHF** (semaine 6) ; 4 semaines en alerte, dont 1 où les précommandes encaissées ne sont pas couvertes ; 4 semaines ouvertes en stop-loss | Test publicitaire et réassorts bloqués au moment prévu par le plan 90 jours | Financer les charges d'avant l'ouverture (≈ 600 CHF) hors réserve, ou réduire les dépenses de lancement ; précommandes uniquement sur allocation ferme |
| R7 | **Paiements** | Frais PSP 2,5 % + 0,30 CHF = hypothèses du BP §4 ; délai de versement inconnu | Encaissements plus tardifs ou plus chers que prévu | Paiements tests (carte, TWINT) et lecture du contrat avant ouverture |
| R8 | **Pilote sous le seuil** | Au rythme du jalon (≈ 15 commandes/mois), −230 CHF/mois ; gel global en semaine 28 | Le test peut « réussir » ses jalons et mener quand même au gel | Fixer dès le départ le volume visé au-delà du test (≥ 31 commandes/mois) et la date de la décision continuer/arrêter |

## 8. Conclusions

1. Les calculs du BP sont **reproductibles** et justes sur le fond. Les trois écarts sont des questions d'arrondi ou de saisie, sans effet sur les décisions.
2. Garder les conventions prudentes du BP (seuil 31, et 181 avec rémunération) en précisant la méthode. Corriger 17 577 en 17 576.
3. L'étoile polaire se pilote avec les mêmes hypothèses : par mois, elle égale le « résultat avant rémunération » du BP. Le scénario central rembourse le creux de lancement en 2 semaines, le prudent en 30.
4. Le BP est **cohérent sur la rentabilité unitaire**, mais **sous-dimensionné en trésorerie** : charges d'avant l'ouverture non budgétées (le stop-loss cash se déclenche avant le test publicitaire), BFR central estimé à plus de 11 000 CHF avec des délais prudents.
5. Avant tout achat significatif, remplacer les hypothèses par des données réelles (devis fournisseur, contrat PSP, tarif colis, statut TVA). Les fichiers de ce dossier se recalculent automatiquement.

## 9. Sources

- BP « Boutique Pokémon FR en Suisse », version du 4 octobre 2026, §1, §3, §4, §5, §9 et §10 (`docs/business-plan/business_plan_extrait.txt`).
- Décisions de la propriétaire (étoile polaire, mandat, stop-loss) transmises à la flotte d'agents ; `engine/pokeshop/stoploss.py` (agent gouvernance) fait foi pour leur application.
- [S6] AFC — TVA, https://www.estv.admin.ch/fr/taxe-sur-la-valeur-ajoutee (citée par le BP). Consultation directe impossible le 4.10.2026 : domaine bloqué par le proxy de l'environnement de build (www.ch.ch également).
- Recherche web du 4.10.2026, extraits indexés des pages AFC https://www.estv.admin.ch/fr/taux-de-la-tva-suisse et https://www.estv.admin.ch/fr/assujettissement-a-la-tva : taux normal 8,1 % depuis le 1.1.2024 ; inscription obligatoire dès que la limite de 100 000 CHF est atteinte, ou dès qu'il est évident au début de l'activité qu'elle le sera. **À confirmer par la fiduciaire** sur la page officielle.

## Validation humaine requise

- [ ] Valider la convention de seuil (31 et 181 commandes, méthode BP prudente) et corriger 17 577 → 17 576 dans le BP.
- [ ] Valider la grille d'arrondi par tranches appliquée par le moteur (`rounding_tiers` de `config/pricing_rules.v1.yaml` : X,50/X,90 sous 10 CHF, X,90 de 10 à 99,99, X4,90/X9,90 dès 100 CHF), ou la modifier dans le fichier de règles (nouvelle signature) ; le classeur suit à la régénération.
- [ ] Arbitrer l'écart §5/§10 : la cible de 20 % s'entend-elle après acquisition, comme dans la formule du §4 ? Si oui, revoir les 22 % avant acquisition du §10.
- [ ] Confirmer la définition du stop-loss global : perte cumulée = contribution nette cumulée (hors dépenses de lancement) et capital engagé = 8 000 CHF (seuil 1 600 CHF).
- [ ] Harmoniser le stop-loss pub avec le plancher produit (couper dès que la contribution après CAC passe sous 8 CHF, soit CAC > 11,33 au panier du BP).
- [ ] Décider du financement des charges fixes d'avant l'ouverture (≈ 400 à 600 CHF) : ligne de budget dédiée ou réduction des dépenses de lancement, pour ne pas entamer la réserve de 1 600 CHF.
- [ ] Décider du financement du BFR (apport, crédit fournisseur, plafond de croissance) avant de viser le scénario central.
- [ ] Faire établir par la fiduciaire le statut TVA de l'entité exploitante et l'échéancier des décomptes.
- [ ] Mesurer le temps réel de préparation par colis (remplace l'hypothèse fictive de 15 minutes).
