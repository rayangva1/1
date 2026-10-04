# Écarts et ambiguïtés du business plan

> Registre central des écarts repérés dans le BP « Boutique Pokémon JCC FR en Suisse » (version du 4 octobre 2026, `docs/business-plan/business_plan_extrait.txt`).
> Règle (SPEC §0) : en cas de conflit, le BP gagne. Un écart n'est **jamais propagé** dans les livrables : il est noté ici, puis tranché par la propriétaire.
> Ouvert par l'agent « pilotage-marche-sourcing » le 4.10.2026. Les autres agents le complètent **via le coordinateur** (une ligne par écart, ID suivant).

## Mode d'emploi

| Colonne | Contenu |
|---|---|
| ID | `EC-NN` (pilotage, marché, sourcing) ; `EC-F-NN` (finance) ; les autres agents prennent le préfixe de leur domaine (`EC-G-` gouvernance, `EC-L-` légal, etc.) |
| Gravité | **Bloquant** : empêche une décision ou un gate · **Important** : fausse un chiffre, un délai ou un risque · **Mineur** : formulation, arrondi |
| Statut | `Ouvert` → `Proposition faite` → `Tranché (date, qui)` → `Reporté dans le BP` |
| Traitement provisoire | Ce que les livrables appliquent en attendant la décision. Il ne remplace pas la décision. |

## 1. Sourcing et fournisseurs (BP §2, §14)

| ID | § BP | Constat | Gravité | Traitement provisoire | Décision attendue |
|---|---|---|---|---|---|
| EC-01 | §2 | **Distributeur suisse absent.** La presse suisse présente **Carletto AG** (Brunnen, SZ) comme distributeur principal des cartes Pokémon en Suisse : il fournit les points de vente du pays et répartit les volumes entre régions linguistiques. Le BP ne cite que des sources françaises ou « suisses » sans ce distributeur. Conséquences : (a) un concurrent suisse peut acheter sans frais d'import, donc moins cher que nous ; (b) un distributeur français peut refuser l'export vers un territoire servi par un autre distributeur. Sources indexées le 4.10.2026 : https://www.srf.ch/news/gesellschaft/begehrte-sammelkarten-ein-schwyzer-unternehmen-als-drehscheibe-fuer-pokemon ; https://www.luzernerzeitung.ch/zentralschweiz/schwyz/pokemon-carletto-ag-in-brunnen-als-hauptdistributor-ld.4127394 | **Bloquant** | Carletto AG est ajouté comme **piste hors BP** dans `docs/02-sourcing/TRACKER_CONTACTS.csv` et `EMAILS_FOURNISSEURS.md` (§7). Il n'est contacté qu'après accord de la propriétaire. | Ajouter Carletto à la liste des fournisseurs autorisés du mandat ? Lui demander s'il vend du **FR** aux revendeurs en ligne de Romandie. |
| EC-02 | §2 | **CardCosmos n'est probablement pas suisse.** Le BP cite `cardcosmos.ch` (priorité 2, colonne « pays réel d'expédition » à obtenir). Selon l'index de recherche, `cardcosmos.ch` est une vitrine du groupe `cardcosmos.de` et expédie **depuis l'Allemagne**. | Important | CardCosmos est traité comme **fournisseur étranger** dans le comparateur : TVA import, frais de dédouanement, délai. | Confirmer le pays d'expédition, la facturation HT export et l'Incoterm. |
| EC-03 | §2 | **Adresse OtakuWorld non retrouvée.** L'adresse `distribuzione@otakuworld.ch` (BP) n'apparaît pas dans les sources indexées. Celles-ci donnent `info@otakuworld.ch` et le portail `https://b2b.otakuworld.ch/` (OtakuWorld.ch Sagl, Tessin, italophone). | Mineur | Email préparé pour l'adresse du BP, avec repli sur `info@` et sur le formulaire du portail. Une version italienne courte est jointe. | Vérifier l'adresse sur le site avant envoi. |
| EC-04 | §2 | **Territoire d'Asmodee.** Une source secondaire (Poképédia, indexée) indique qu'Asmodee détient les droits Pokémon pour **la France et la Belgique**. Le BP note déjà l'acceptation d'une entreprise suisse comme « à obtenir ». Le risque d'un renvoi vers le distributeur suisse est réel (voir EC-01). | Important | Asmodee reste en priorité 1 (BP). La question du territoire est posée en premier dans l'email. | Aucune : la réponse d'Asmodee tranche. |
| EC-05 | §14 | **Sources du BP non vérifiables depuis l'environnement de build.** Le 4.10.2026, les 5 URL fournisseurs (S1 à S5) et les sites concurrents sont refusés par le proxy de sortie (403). `wholesale.miao.matoocorp.com` ne se résout pas non plus. Les vérifications ont été faites **uniquement par index de recherche web**. | Important | Chaque URL porte le statut « indexée, page non ouverte » dans les livrables. La tâche BL-021 du backlog prévoit une re-vérification par un agent ayant l'accès, ou par la propriétaire. | Re-vérifier avant le premier envoi (5 min par URL). |
| EC-06 | §2, §13 | **Une 2e source est exigée sans critère.** « Une seconde source identifiée » (conditions de lancement) : ni le BP ni le §13 ne disent ce qui compte comme « identifiée ». | Mineur | `GATES_GO_NO_GO.md` : identifiée = devis écrit reçu **et** due diligence sans critère éliminatoire. | Valider la définition. |

## 2. Calendrier et gates (BP §1, §9, §13)

| ID | § BP | Constat | Gravité | Traitement provisoire | Décision attendue |
|---|---|---|---|---|---|
| EC-07 | §1 vs §9 | **Les indicateurs « 60 jours de vente » tombent après J90.** Les ventes démarrent entre J31 et J45 (§9). Soixante jours de vente se terminent donc entre J91 et J105, après la fin du plan de 90 jours. Le bilan J90 ne peut pas trancher les seuils du §1. | **Bloquant** | Deux rendez-vous dans `GATES_GO_NO_GO.md` : **bilan J90** (intermédiaire) et **décision G7 à J_V1 + 60** (J_V1 = date de la 1re commande payée), soit vers le 3 au 17 janvier 2027 si J1 = 5.10.2026. | Valider la date de décision. |
| EC-08 | §9 vs §8 | **La landing (J1-15) précède la validation du nom (J16-30).** Une page publique avec inscription exige un nom et un domaine, que le §8 ne fixe qu'« avant achat de domaine », pendant la phase « Identité » (J16-30). | Important | Plan 90 jours : validation du nom avancée à **J5-J7** (3 pistes + vérifications prêtes à J4). Repli : landing sur un sous-domaine neutre fourni par l'outil, sans marque. | Accepter l'avancement de la validation du nom. |
| EC-09 | §13 S2 | **Un « fichier réel » en semaine 2 est irréaliste.** Il suppose un compte fournisseur ouvert et une réponse technique en moins de 14 jours. Or l'ouverture de compte passe par une vérification (« quelques jours ouvrables » annoncés chez CardCosmos, selon l'index). | Important | Le plan vise le fichier réel en **S2 au mieux, S3 au plus tard**. Repli BP §6 priorité 3 : import assisté d'un tarif email/PDF. Le gate G2 accepte un tarif réel non structuré **si** l'exemple de fichier est promis par écrit. | Accepter le glissement possible d'une semaine. |
| EC-10 | §9 | **Saisonnalité absente du calendrier.** Si J1 = lundi 5.10.2026 : avant-premières Règne Delta le 24.10 (J20), sortie FR le **6.11 (J33)**, Black Friday le **27.11 (J54)**, Noël le 25.12 (J82). L'ouverture douce coïncide avec une sortie majeure. Un nouveau compte n'aura probablement **aucune allocation** sur cette sortie, et le test pub (J46-60) tombe pendant la hausse des enchères publicitaires du Black Friday. | Important | Assortiment pilote construit **sans dépendre** de Règne Delta (`docs/01-marche/ASSORTIMENT_PILOTE.md`). Test pub décalé après le 30.11 ou plafond jour réduit (`GATES_GO_NO_GO.md`, G5). Le registre des risques porte R04, R12 et R14. | Valider la date réelle de J1 et la position face à Règne Delta. |
| EC-11 | Intro, §13 | **Gates sans seuils chiffrés.** « Règles d'automatisation validées », « erreur critique » (§13 S3-4), « poursuivre/reporter » (§13) : aucun seuil, aucune date, aucun décideur. | Important | Définitions chiffrées dans `GATES_GO_NO_GO.md` (§2 et §3). | Valider les seuils. |
| EC-12 | §1, §9 | **Deux mesures de contribution coexistent.** L'indicateur « contribution positive après publicité » (§1, avant charges fixes) n'est pas l'étoile polaire de la propriétaire (contribution nette cumulée, **après** charges fixes). | Important | Les gates suivent les deux mesures et décident sur l'**étoile polaire**. Le §1 reste un indicateur de test. | Confirmer. |
| EC-13 | Mandat (gouvernance) | **Point de départ du stop-loss « temps » non défini.** « 60 j sans seuils de validation » ne dit pas d'où partent les 60 jours (J1 ? 1re vente ?). | Important | Interprétation provisoire : 60 jours à partir de J_V1, alignée sur le §1. L'agent gouvernance fait foi (`engine/pokeshop/stoploss.py`, `docs/00-pilotage/STOP_LOSS.md`). | À trancher avec l'agent gouvernance. |

## 3. Assortiment et budget (BP §1, §3)

| ID | § BP | Constat | Gravité | Traitement provisoire | Décision attendue |
|---|---|---|---|---|---|
| EC-14 | §1 | **Base du plafond de 25 % par extension.** Le plafond s'applique-t-il au budget stock total (3 000 CHF, soit 750 CHF) ou au seul scellé (90 %, soit 2 700 CHF) ? Avec 750 CHF par extension, il faut au moins **4 extensions** pour placer 2 700 CHF de scellé (2 700 / 750 = 3,6). Cela impose des extensions plus anciennes (Équilibre Parfait, Héros Transcendants), dont la disponibilité est incertaine. | Important | Base = budget stock total 3 000 CHF, plafond 750 CHF (cohérent avec `config/pricing_rules.v1.yaml` : `extension_budget_cap` × `stock_budget_chf`). Accessoires hors extension. | Valider la base du plafond. |
| EC-15 | §1 | **Extension « spéciale » à plusieurs produits.** L'extension 30ᵉ Anniversaire existe en coffrets, ETB, bundle, mini-tins et classeur. Le BP ne dit pas si tous ces produits comptent dans **une seule** extension pour le plafond. | Mineur | Traitement provisoire : oui, une seule extension (prudence). | Confirmer. |
| EC-16 | §1 | **Statut des références hors stock.** « 15 à 25 références dont 8 à 12 réellement en stock » : le BP ne dit pas sous quelle forme les 7 à 13 autres sont publiées. | Mineur | Fiches publiées **indisponibles avec alerte réassort**, ou précommande **uniquement** sur allocation ferme (BP §3, §5). Jamais de stock fournisseur affiché comme expédiable. | Confirmer. |
| EC-17 | §3, §9 | **Collaboration locale sans budget propre.** La « collaboration locale limitée » (J46-60) n'a pas de ligne dans le budget §3. | Mineur | Incluse dans l'enveloppe test acquisition de 500 CHF. Les produits offerts et commissions comptent dans le CAC (BP §9). | Confirmer. |
| EC-18 | §4 | **Droits de douane nuls à préciser.** Depuis le 1.1.2024, la Suisse a supprimé les droits de douane sur les produits industriels (chapitres SH 25 à 97, jouets et cartes compris). Restent la TVA à l'importation et les frais de dédouanement du transporteur. Le BP parle de « dédouanement et autres frais » sans le préciser. Sources indexées : https://www.seco.admin.ch/fr/suppression-droits-de-douane-produits-industriels ; https://www.admin.ch/fr/nsb?id=99580 | Mineur | Comparateur : droits de douane = 0. Seuls les frais de dédouanement et la TVA import sont saisis. | Confirmation par la fiduciaire pour la position tarifaire réelle. |

## 4. Marché et clients (BP §1)

| ID | § BP | Constat | Gravité | Traitement provisoire | Décision attendue |
|---|---|---|---|---|---|
| EC-19 | §1 | **Entretiens sans recrutement ni cadre LPD.** Le BP ne prévoit ni canal de recrutement des 10 à 15 entretiens, ni information sur les données personnelles. | Mineur | `docs/01-marche/GUIDE_ENTRETIENS.md` : consentement lu en début d'entretien, données pseudonymisées, suppression à J90. | Valider le texte de consentement (juriste si souhaité). |
| EC-20 | §1, §9 | **Nombre d'entretiens.** « 10 à 15 entretiens » (§1) contre « 10 entretiens » (§9). | Mineur | Minimum 10 (gate), cible 15. | — |
| EC-21 | §1 | **Comparabilité des relevés.** La comparaison « 10 à 15 références identiques » ne précise pas le critère d'identité. Les boutiques suisses vendent souvent FR et EN sous des titres proches. | Mineur | `docs/01-marche/PROTOCOLE_CONCURRENCE.md` : identité = format + extension + langue + contenu, EAN lorsqu'il est affiché. Un relevé non comparable est exclu de la médiane. | — |

## 5. Écarts relevés par l'agent finance (rappel)

Détail et calculs dans `docs/03-finance/NOTE_VERIFICATION_BP.md`. Repris ici pour avoir une liste unique.

| ID | § BP | Constat | Gravité |
|---|---|---|---|
| EC-F-01 | §10 | CA HT du scénario développement : 17 577 dans le BP contre **17 576** recalculé (19 000 / 1,081). | Mineur |
| EC-F-02 | §10 | Seuils 31 et 181 commandes = convention « contribution arrondie au centime » (30 et 180 en valeur exacte). Garder 31 et 181. | Mineur |
| EC-F-03 | §4 vs SPEC | Arrondi du prix public : 208,79 → 209,90 (BP, pas de 10 CHF) contre « prochain X,90 » = 208,90 (SPEC). Le moteur applique une grille par tranches qui reproduit le BP. | Important |
| EC-F-04 | §5 vs §10 | La cible de 20 % (§5, après acquisition) ne correspond pas aux 22 % **avant** acquisition du §10 : 15,2 % après CAC au scénario central. | Important |
| EC-F-05 | §5 vs §10 | Les deux cas de sensibilité du §10 (7,18 et 4,33 CHF par commande) passent **sous le plancher dur** de 8 CHF par commande. | Important |
| EC-F-06 | §3 | Les charges fixes d'avant l'ouverture (≈ 400 à 600 CHF) ne sont pas budgétées. Elles entament la réserve de 1 600 CHF et déclenchent le stop-loss cash avant le test publicitaire. | **Bloquant** pour le test pub |
| EC-F-07 | §1 vs §10 | Le rythme du jalon de validation (≈ 15 commandes/mois) est déficitaire par construction (≈ −230 CHF/mois). Il mène au gel global vers la semaine 28. | Important |
| EC-F-08 | §10 | Le BFR du scénario central (≈ 11 239 CHF avec des délais FICTIFS) dépasse les 4 600 CHF mobilisables. | Important |

## 6. Journal des décisions

| Date | ID | Décision | Qui |
|---|---|---|---|
| — | — | Aucune décision enregistrée au 4.10.2026. | — |

## Validation humaine requise

- [ ] **EC-01** : ajouter Carletto AG comme piste (hors BP) dans le mandat et autoriser le premier contact.
- [ ] **EC-07** : valider la date de la décision « poursuivre/reporter/arrêter » à J_V1 + 60, et non à J90.
- [ ] **EC-08** : accepter d'avancer la validation du nom à J5-J7 pour publier la landing en S2.
- [ ] **EC-10** : fixer la date réelle de J1 et la position face à la sortie Règne Delta (6.11.2026).
- [ ] **EC-13** : trancher avec l'agent gouvernance le point de départ du stop-loss « temps ».
- [ ] **EC-14 et EC-15** : confirmer la base du plafond de 25 % (3 000 CHF, soit 750 CHF par extension) et le traitement de l'extension 30ᵉ Anniversaire.
- [ ] **EC-F-03 à EC-F-08** : arbitrages finance (voir la note de l'agent finance).
- [ ] Désigner qui reporte les décisions dans une version 2 du BP, et quand.
