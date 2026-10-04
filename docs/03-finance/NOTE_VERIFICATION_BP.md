# Note de vérification du BP — volet finance

> Objet : recalcul chiffre par chiffre des §3, §4 et §10 du business plan « Boutique Pokémon JCC FR en Suisse » (version du 4 octobre 2026).
> Auteur : agent finance. Date de référence : 4 octobre 2026. Montants en CHF.
> Reproductible : `python -m pytest -q tests/test_forecast.py tests/test_treasury.py` et `pokeshop.forecast.verify_against_bp()`.

## 1. En bref

| Constat | Détail |
|---|---|
| **38 chiffres recalculés** | 35 ✅ conformes · 2 ⚠️ écarts d'arrondi (seuils 31 et 181) · 1 ⚠️ écart de 1 CHF (CA HT développement 17 577) |
| **Mécanique du BP** | Juste. Aucun écart ne change une conclusion. |
| **Risque n° 1** | Le stock de 3 000 CHF couvre **14,6 jours** de ventes du scénario central (achats consommés 6 152 CHF HT/mois). |
| **Risque n° 2** | Le scénario central annualisé (114 000 CHF TTC) **dépasse le seuil TVA** de 100 000 CHF. |
| **Risque n° 3** | Temps non rémunéré : **1,19 CHF/h** implicite au scénario prudent, 15,64 CHF/h au central (hypothèse fictive de 15 min de préparation par colis). |
| **Incohérence §5/§10** | 22 % de contribution *avant* acquisition donne **15,2 %** après CAC au central, sous la cible de 20 % du §5. Les deux cas de sensibilité passent **sous le plancher dur de 8 CHF/commande**. |
| **Point budget** | Les charges fixes des semaines sans ventes (≈ 400 à 600 CHF avant l'ouverture) ne figurent pas dans le budget de 8 000 CHF. Elles entament la réserve de 1 600 CHF. |

## 2. Méthode

- Calcul en `decimal.Decimal`, sans arrondi intermédiaire. Arrondi « demi supérieur » uniquement à l'affichage : franc entier pour les totaux, centime pour les montants par commande, comme dans le BP.
- **Exact** = valeur non arrondie. **Recalcul** = valeur arrondie selon la convention du BP.
- Statut : ✅ identique au BP · ⚠️ arrondi = écart dû à une convention d'arrondi (BP reproduit avec sa convention) · ⚠️ écart = différence non expliquée par un arrondi.
- Double contrôle : les mêmes formules sont écrites en formules Excel vivantes dans `modele_financier.xlsx`. Le classeur est recalculé par LibreOffice 24.2 en mode headless et relu avec `openpyxl` (`data_only=True`). Les tests vérifient que Python et le classeur donnent les mêmes valeurs.

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
**Recommandation :** corriger le tableau du BP en 17 576.

### 4.4 Règle d'arrondi du prix public : 208,79 → 209,90

- Le BP passe de 208,79 à **209,90**. La SPEC (`round_up_retail`, « prochain X,90 ») donnerait **208,90**.
- 209,90 correspond à la règle « terminaison 9,90, pas de 10 CHF ». Le classeur (`Prix plancher`, lignes 19 à 22) rend le pas et la terminaison paramétrables et affiche les deux lectures.
- Avec un pas de 10 CHF, un petit produit dont le plancher serait 5,40 CHF (illustration, pas un prix) s'afficherait à 9,90 CHF (+83 %). Il faut une **règle par tranche de prix**.
- 209,90 donne 20,41 % de contribution (cible atteinte). 208,90 donne 20,04 %, ce qui atteint aussi la cible.

### 4.5 Marge d'arrondi du prix plancher

Le plancher exact vaut 208,79498. L'arrondi « demi supérieur » au centime donne 208,79 **à 0,00002 CHF près**. Pour un *plancher*, un arrondi au centime supérieur (208,80) serait plus cohérent. Sans effet pratique ici, puisque le prix public est de toute façon arrondi vers le haut.

## 5. Cohérence entre sections du BP

| Point | Constat | Statut |
|---|---|---|
| Contribution §10 (22 % *avant* acquisition) vs cible §5 (20 % *après* acquisition, A dans la formule) | Après CAC : prudent 12,9 %, central 15,2 %, développement 16,3 % du CA HT. Les scénarios supposent donc des prix **sous la cible** du §5, mais au-dessus du plancher dur (≥ 12 % et ≥ 8 CHF). | ⚠️ à arbitrer |
| Sensibilités §10 vs plancher dur §5 | 15 % ⇒ 7,18 CHF et CAC 15 ⇒ 4,33 CHF par commande : **sous 8 CHF**. Le moteur prix devrait bloquer ou alerter ces paniers. | ⚠️ cohérence |
| 22 % de contribution vs 70 % de coût produit | Il reste 8 % du CA HT, soit 7,03 CHF/commande, pour le paiement (2,68), le SAV (1,00) et l'emballage (3,36 implicites). C'est plausible au regard du §4 (L = 3, R = 1). | ✅ cohérent |
| Test acquisition §3 (500) vs jours 46 à 60 §9 (500 max) | Identiques. | ✅ |
| Répartition du stock §1 | 25 + 25 + 20 + 20 + 10 = 100 %, soit 750 / 750 / 600 / 600 / 300 CHF. Plafond par extension : 750 CHF. | ✅ |
| Objectif de validation §1 (30 commandes en 60 jours) vs seuil §10 (31/mois) | Le test vise environ 15 commandes/mois, la moitié du seuil. La phase pilote est donc **déficitaire par construction** : ≈ 15 × 13,33 − 400 = −200 CHF/mois. C'est cohérent avec un test, mais à financer par la réserve. | ⚠️ à assumer |
| Budget §3 vs charges mensuelles §3 | Le budget de 8 000 CHF ne contient pas de ligne « charges fixes avant les premières ventes ». Les ventes démarrent vers les jours 31 à 45 (§9), soit 1 à 1,5 mois de charges (400 à 600 CHF) qui s'imputent sur la réserve de 1 600 CHF. On ne sait pas si la ligne « Site et automatisation 1 500 » couvre les abonnements. | ⚠️ ambiguïté |
| Hypothèse TVA §10 (assujetti) vs seuil §4 | Le tableau ne couvre que le cas assujetti. Le prudent annualisé (45 600 TTC) est sous le seuil. Le central (114 000 TTC, 105 458 HT) est au-dessus. Le cas « non assujetti » n'est pas chiffré au §10 : prix sans TVA à reverser mais TVA d'achat non récupérable. | ⚠️ à compléter |

## 6. Risques

| # | Risque | Chiffres | Conséquence | Mesure proposée |
|---|---|---|---|---|
| R1 | **Le stock de 3 000 CHF ne finance pas un mois central** | Achats consommés 6 152 CHF HT/mois ; couverture 48,8 % = **14,6 jours** ; manque 3 152 CHF pour un mois | Ruptures, ou trésorerie absorbée par les réassorts | Réassort hebdomadaire plafonné par la trésorerie disponible (classeur 13 semaines) ; montée en volume progressive |
| R2 | **Besoin en fonds de roulement** | Avec des délais FICTIFS (14 j de prépaiement, 30 j de stock, 7 j de versement PSP, 0 j de crédit), BFR central ≈ **11 239 CHF** contre 4 600 mobilisables (stock + réserve), soit ≈ 6 639 CHF à financer | Le scénario central n'est pas finançable avec le budget pilote sans crédit fournisseur ni apport | Obtenir les vrais délais (devis, contrat PSP) ; négocier un paiement à terme ; décider d'un apport ou d'un plafond de croissance |
| R3 | **Seuil TVA** | Central annualisé 114 000 TTC ; TVA contenue ≈ 712 CHF/mois au central | Assujettissement obligatoire à anticiper ; la TVA encaissée n'est pas du cash disponible | Examen fiduciaire **avant** l'ouverture, sur toute l'activité de l'entité exploitante |
| R4 | **Temps non rémunéré** | Supervision 26 à 43 h/mois (6 à 10 h/sem. × 52/12) + colis. Rémunération implicite : prudent 1,19 CHF/h, central 15,64, développement 29,14 (avant impôts et charges sociales ; 15 min/colis = hypothèse fictive) | Une activité « cash positive » peut ne pas payer le travail | Second compte de résultat avec le temps valorisé ; mesurer le temps réel par colis |
| R5 | **Fragilité de la contribution** | 22 % → 15 % : seuil de 31 à 56 commandes ; CAC de 6 à 15 : seuil de 31 à 93 | Une erreur de coût, de livraison ou de CAC annule le bénéfice | Contrôle de la marge réelle par facture (BP §12) ; coupure publicitaire automatique si CAC > contribution |
| R6 | **Réserve et précommandes** | Exemple FICTIF 13 semaines : solde au plus bas **497 CHF** (semaine 9) ; 3 semaines en alerte, dont 2 où les précommandes encaissées ne sont pas couvertes | Utiliser l'argent des précommandes pour d'autres achats | Précommandes uniquement sur allocation ferme ; achats « prévus » bloqués tant qu'une alerte est active |
| R7 | **Paiements** | Frais PSP 2,5 % + 0,30 CHF = hypothèses du BP §4 ; délai de versement inconnu | Encaissements plus tardifs ou plus chers que prévu | Paiements tests (carte, TWINT) et lecture du contrat avant ouverture |

## 7. Conclusions

1. Les calculs du BP sont **reproductibles** et justes sur le fond. Les trois écarts sont des questions d'arrondi ou de saisie, sans effet sur les décisions.
2. Garder les conventions prudentes du BP (seuil 31, et 181 avec rémunération) en précisant la méthode. Corriger 17 577 en 17 576.
3. Le BP est **cohérent sur la rentabilité unitaire**, mais **sous-dimensionné en trésorerie** pour le scénario central : stock 3 000 CHF, réserve 1 600 CHF, BFR estimé à plus de 11 000 CHF avec des délais prudents.
4. Avant tout achat significatif, remplacer les hypothèses par des données réelles (devis fournisseur, contrat PSP, tarif colis, statut TVA). Les fichiers de ce dossier se recalculent automatiquement.

## 8. Sources

- BP « Boutique Pokémon FR en Suisse », version du 4 octobre 2026, §1, §3, §4, §5, §9 et §10 (`docs/business-plan/business_plan_extrait.txt`).
- [S6] AFC — TVA et assujettissement, https://www.estv.admin.ch/fr/taxe-sur-la-valeur-ajoutee (citée par le BP). Consultation directe impossible le 4.10.2026 : domaine bloqué par le proxy de l'environnement de build.
- Sources secondaires consultées par recherche web le 4.10.2026 : taux normal de 8,1 % depuis le 1.1.2024, seuil de 100 000 CHF, décompte trimestriel à déposer dans les 60 jours. Voir https://fasoon.ch/fr/la-taxe-sur-la-valeur-ajoutee-tva-en-suisse/ et https://www.simulateur.ch/guide/tva-suisse-2026. **À confirmer par la fiduciaire** : ce ne sont pas des sources officielles.

## Validation humaine requise

- [ ] Valider la convention de seuil (31 et 181 commandes, méthode BP prudente) et corriger 17 577 → 17 576 dans le BP.
- [ ] Trancher la règle d'arrondi du prix public : terminaison 9,90 au pas de 10 CHF (BP) ou « prochain X,90 » (SPEC), et définir des tranches de prix pour les petits produits.
- [ ] Arbitrer l'écart §5/§10 : la cible de 20 % s'entend-elle après acquisition, comme dans la formule du §4 ? Si oui, revoir les 22 % avant acquisition du §10.
- [ ] Confirmer si les charges fixes des semaines sans ventes sont incluses dans le budget de 8 000 CHF, ou ajouter une ligne dédiée.
- [ ] Décider du financement du BFR (apport, crédit fournisseur, plafond de croissance) avant de viser le scénario central.
- [ ] Faire établir par la fiduciaire le statut TVA de l'entité exploitante et l'échéancier des décomptes.
- [ ] Mesurer le temps réel de préparation par colis (remplace l'hypothèse fictive de 15 minutes).
