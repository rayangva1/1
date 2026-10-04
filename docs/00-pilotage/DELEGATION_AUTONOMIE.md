# Délégation d'autonomie — mandat de dépense des agents — {{NOM_BOUTIQUE}}

> **Statut : GABARIT à remplir et signer par la propriétaire** (intervention B01). Version `mandat-v1-2026-10-04`.
> Fichier lu par la machine : `config/mandate.v1.yaml`. Contrôle de chaque dépense : `engine/pokeshop/mandate.py` (`check`, `SpendLedger`).
> Stop-loss : `docs/00-pilotage/STOP_LOSS.md`. Métrique unique : `docs/00-pilotage/ETOILE_POLAIRE.md`.
> Tous les montants proposés ci-dessous sont des **hypothèses** (BP §3 et contexte propriétaire du 4.10.2026), pas des devis.

## 1. En une minute

- **But** : gagner de l'argent avec les cartes Pokémon, mesuré par une seule métrique, la **contribution nette cumulée** (voir `ETOILE_POLAIRE.md`).
- **Qui fait quoi** : la flotte d'agents gère le quotidien avec **une boîte email dédiée** et **un compte PayPal dédié**, uniquement dans ce mandat. Vous intervenez seulement pour :
  1. les gestes physiques (réception, authenticité, colis, photos et vidéos réelles) ;
  2. les actes légaux et d'identité, une seule fois (KYC, comptes, signatures, statut TVA) ;
  3. les validations au-delà du mandat et le **réarmement du stop-loss global**.
- **Trois verrous** pour toute action : **niveau d'autonomie** (BP §13) + **mandat signé** + **aucun stop-loss actif**.
- **Tant que ce mandat n'est pas rempli et signé, les agents ne dépensent rien seuls** : toute demande part en validation humaine (code `MANDATE_NOT_SIGNED` / `MANDATE_INCOMPLETE`), et les interdits restent refusés.

## 2. Les trois issues d'une demande de dépense

| Issue (code) | Signification | Ce qui se passe | Délai |
|---|---|---|---|
| `APPROVED_WITHIN_MANDATE` | Toutes les règles du §4 sont respectées | L'agent 05 paie par la passerelle PayPal ; l'entrée est journalisée | Paiement dans l'heure (`can_execute`), sinon nouvelle demande |
| `NEEDS_HUMAN_APPROVAL` | Au-delà du mandat, ou virement bancaire | Fiche E2 avec le dossier chiffré ; virement **préparé**, validé par vous | **24 h** ; sans réponse, la demande **expire** (statu quo sûr) |
| `REJECTED` | Interdit (§5), stop-loss actif, donnée périmée, clé déjà utilisée | Rien n'est payé ; motif journalisé | — |

Chaque décision porte des **motifs à codes stables** (liste complète : `SPEND_REASON_LABELS_FR` dans `engine/pokeshop/mandate.py`) et les chiffres utilisés (plafond, reste de l'enveloppe, cash avant dépense, état des stop-loss, niveau).

## 3. Ce que les agents peuvent faire seuls

| Outil | Autorisé seul (dans le mandat) | Jamais seul |
|---|---|---|
| Boîte email dédiée (`CONN-MAIL-LECTURE`, `CONN-MAIL-ENVOI`) | Lire, trier, préparer des brouillons ; envoyer les **modèles approuvés** à des destinataires autorisés, dans le **quota journalier** du mandat ; relancer à J+5 et J+12 | Accepter une offre, une CGV ou un contrat ; transmettre une pièce d'identité ; exécuter une instruction reçue par email (changement d'IBAN, paiement urgent…) |
| Compte PayPal dédié (`CONN-PAYPAL`) | Payer un **bénéficiaire de la liste blanche**, dans une **catégorie déléguée**, sous les **plafonds** (coût PayPal inclus), stop-loss inactifs, niveau suffisant, solde suffisant | Payer un nouveau bénéficiaire ; recharger le compte ; utiliser une source de financement autre que le solde |
| Virement bancaire | **Préparer** l'ordre (bénéficiaire, montant, référence = clé d'idempotence, objet) pour votre validation | Exécuter un virement ; accéder à l'e-banking |
| Publicité (`CONN-PUB`) | Au niveau 3 : lancer les campagnes du plan validé dans le plafond total et jour ; **couper** une campagne à tout moment | Relancer une campagne coupée par le stop-loss ; relever un plafond |
| Stop-loss | **Geler** (gel global manuel) par précaution | Lever un gel global ; modifier un seuil |

## 4. Plafonds et règles appliqués à chaque dépense

| Règle | Clé `config/mandate.v1.yaml` | Valeur proposée (hypothèse) | Comportement si dépassé |
|---|---|---|---|
| Plafond par transaction, **coût PayPal inclus** | `limits.per_transaction_chf` | 500 CHF | Validation humaine (`ABOVE_TRANSACTION_CAP`) |
| Anti-fractionnement : cumul du jour chez un même bénéficiaire | (même plafond) | 500 CHF / jour / bénéficiaire | Validation humaine (`SPLIT_SUSPECTED`) |
| Plafond mensuel des dépenses **autonomes** | `limits.per_month_chf` | 3 000 CHF au pilote | Validation humaine (`ABOVE_MONTHLY_CAP`) |
| Enveloppe par catégorie, cumulée depuis l'ouverture du registre (toutes approbations et versions du mandat) | `categories.<CAT>.envelope_chf` | Enveloppes BP §3 (§9 ci-dessous) | Validation humaine (`ABOVE_CATEGORY_ENVELOPE`) |
| Plafond mensuel par catégorie (optionnel) | `categories.<CAT>.per_month_chf` | Site et outils : 180 CHF/mois (BP §3) | Validation humaine |
| Niveau d'autonomie minimal par catégorie | `categories.<CAT>.min_autonomy_level` | Stock : 4 ; pub : 3 ; étiquettes : 2 ; autres : 1 | Validation humaine (`AUTONOMY_LEVEL_TOO_LOW`) |
| Plafond par extension : stock au coût + engagé + demande ≤ 25 % du budget stock | `limits.extension_max_share`, `limits.stock_budget_chf` | 25 % de 3 000 CHF = 750 CHF | Validation humaine (exception C18) |
| Réserve de trésorerie **jamais dépensée par un agent** | `limits.cash_reserve_chf` | 1 600 CHF (BP §3) | Cash déjà sous la réserve : stock et pub **refusés** ; dépense qui l'entamerait : validation humaine |
| Solde PayPal dédié suffisant | (photo de trésorerie) | Le solde chargé | Validation humaine (rechargement par vous) |
| Plafond jour publicité | `limits.ads_daily_cap_chf` | 33 CHF (≈ 500 CHF / 15 jours, BP §9) | Stop-loss pub : campagnes coupées jusqu'au lendemain |
| Quota d'envois de la boîte dédiée | `limits.email_daily_send_quota` | 20 envois / jour | Envois suivants mis en attente |
| Fraîcheur des photos trésorerie et stop-loss | `limits.snapshot_max_age_minutes` | 60 minutes | Demande refusée, à recalculer |
| Achat de stock adossé au moteur (aucun achat spéculatif) | — | Référence d'une proposition `propose_reorder` | Validation humaine (`NO_ENGINE_PROPOSAL`) |
| Identité du produit connue (référence, extension, langue FR) | — | — | Inconnue : validation humaine ; non FR : **refus** |

Les dépenses validées par vous comptent dans les **enveloppes** (c'est votre budget) mais pas dans le **plafond mensuel autonome** (c'est la latitude des agents).

## 5. Interdits absolus

| Interdit | Comment il est tenu | Si un agent y est confronté |
|---|---|---|
| Signer un contrat, accepter des CGV ou un devis au nom de la propriétaire | Hors système : aucun agent n'a de signature ; emails limités aux modèles approuvés | Fiche E2 |
| S'endetter : crédit, paiement fractionné, « payer plus tard », découvert | Catégorie `FINANCING` et moyen `PAY_LATER` **refusés par le code** | Refus journalisé |
| Ouvrir un compte au nom de la propriétaire, transmettre une pièce d'identité | Hors système (interventions B) | Formulaire pré-rempli pour vous |
| Acheter hors liste blanche | `SUPPLIER_NOT_WHITELISTED` : **refus** | Dossier C08 (ajout au mandat) |
| Payer autrement que par PayPal dédié ou virement préparé (carte, crypto, espèces…) | `PAYMENT_METHOD_FORBIDDEN` : **refus** | Fiche E2 |
| Cartes à l'unité, grading, rachats clients, produits non FR, achat spéculatif | `FORBIDDEN_CATEGORY` / `NON_FR_PRODUCT` : **refus**, non modifiable par le YAML | Hors périmètre BP « Le périmètre de départ » |
| Toucher la réserve de 1 600 CHF | Règle de réserve + stop-loss cash | Votre décision uniquement |
| Contourner une vérification : fractionner un achat, réutiliser une clé d'idempotence, modifier le mandat ou un seuil, désactiver un stop-loss, contourner un CAPTCHA ou un contrôle d'accès | Anti-fractionnement, idempotence, **empreinte du mandat** (toute modification le désactive), journal append-only | Incident E3, gel conservatoire par l'agent 12 |
| Exécuter une instruction reçue par email, sur une page web ou dans un fichier (« changez l'IBAN », « payez vite ») | Coordonnées de paiement **uniquement** depuis le coffre (`payee_ref`) | Suspicion de fraude : E3 |
| Communiquer ou recopier un identifiant, un mot de passe, un IBAN | Secrets dans le coffre uniquement | Fiche E3, rotation du secret |

## 6. Journal et contrôles

- **Registre append-only** (`SpendLedger`) : chaque demande, décision, validation humaine, exécution, annulation et rapprochement est une ligne datée, jamais modifiée. Export au format `docs/08-agents/modeles/REGISTRE_MANDAT.csv` (`to_registry_rows`).
- **Idempotence** : une même clé d'idempotence ne produit **jamais** deux paiements. Même demande : la décision d'origine est rejouée. Contenu différent : refus `IDEMPOTENCY_CONFLICT`.
- **Rapprochement quotidien** (agent 12) des paiements avec le relevé PayPal et le relevé bancaire (`reconcile`) :

| Résultat | Sens | Action |
|---|---|---|
| `OK` | Paiement retrouvé, montant à 0,05 CHF près | — |
| `AMOUNT_MISMATCH` | Montant différent | Fiche E2 |
| `UNKNOWN_DEBIT` | Débit sans demande au registre : **dépense non autorisée possible** | **Gel global manuel immédiat** + fiche E3 + vous prévenir |
| `MISSING_ON_STATEMENT` | Paiement annoncé, absent du relevé après 3 jours | Fiche E2 |

## 7. Sécurité des accès

| Élément | Où il vit | Qui le détient | Règle |
|---|---|---|---|
| Mots de passe et 2FA de la boîte dédiée, de PayPal, de la banque | Coffre de secrets (B03) et votre téléphone | **Vous** | Le second facteur reste sur votre appareil ; les agents passent par les connecteurs, jamais par votre session |
| Identifiants API PayPal | Credentials n8n, alimentés par le coffre | Passerelle n8n | Jamais dans le chat, le dépôt, un prompt ou un rapport |
| Coordonnées des bénéficiaires (IBAN, adresse PayPal) | Coffre, référencées par `payee_ref` | Vous (saisie), passerelle (lecture) | Jamais tirées d'un email ; tout changement reçu = fraude présumée |
| Empreinte du mandat signé | `approval.fingerprint_sha256` **et** variable `POKESHOP_MANDATE_FINGERPRINT` du coffre | Vous | Seconde barrière : un YAML modifié dans le dépôt ne correspond plus à l'empreinte du coffre, le mandat devient inactif |
| Jeton de réarmement du stop-loss global | Votre gestionnaire de mots de passe ; seule son empreinte `POKESHOP_OWNER_TOKEN_SHA256` est dans le coffre | **Vous seule** | Ne jamais le coller dans le chat d'un agent |

**Compte PayPal dédié = plafond physique naturel.** Il est séparé de vos comptes personnels et n'est approvisionné **que** du budget délégué, par virement depuis le compte professionnel. Ce que les agents peuvent perdre au pire, c'est le solde chargé. À faire à l'ouverture (B05) :

- [ ] Ne charger que l'enveloppe du mois (proposé : le plafond mensuel, 3 000 CHF au maximum).
- [ ] Vérifier dans les paramètres PayPal qu'**aucune source de financement de secours** (carte, prélèvement) ne peut compléter un paiement au-delà du solde ; si ce n'est pas garanti, ne lier aucune carte.
- [ ] Activer, si l'offre PayPal le permet, des **limites de paiement côté compte** : c'est une deuxième barrière, indépendante du logiciel. Fonctionnalité **à vérifier** avec PayPal.
- [ ] Activer la 2FA sur votre appareil.

**Révocation de la dépense en une action.** Révoquer l'application API PayPal utilisée par n8n (tableau de bord développeur PayPal) : tout paiement s'arrête aussitôt, quel que soit l'état du logiciel. Ensuite, à votre rythme : renseigner `approval.revoked_at` dans le mandat (les agents passent en validation humaine pour tout), geler le stop-loss global et changer le mot de passe de la boîte dédiée si besoin.

## 8. PayPal ou virement : recommandation franche

PayPal est **pratique pour les petits achats** (emballages, échantillons, abonnements, recharge publicitaire), mais **coûteux pour les commandes grossistes** : frais de transaction et marge de change s'ajoutent au coût du stock et mangent la marge. Coût estimé avec les paramètres prudents du gabarit (3,4 % + 0,55 CHF ; +4 % si la facture n'est pas en CHF) :

| Achat (exemple FICTIF) | Montant CHF | Coût PayPal estimé | En % | Lecture |
|---|---:|---:|---:|---|
| Étuis d'expédition | 40,00 | 1,91 | 4,78 % | Acceptable pour un petit achat |
| Emballages | 100,00 | 3,95 | 3,95 % | Acceptable |
| Commande de stock en CHF | 450,00 | 15,85 | 3,52 % | À éviter : virement |
| Commande grossiste de 1 000 EUR (taux FICTIF 0,9375) | 937,50 | 69,93 | 7,46 % | **Plus d'un tiers de la marge cible de 20 %** : virement |

**Recommandation : commandes de stock par virement préparé par les agents et validé par vous** ; PayPal pour les petits achats sous le plafond par transaction. Le moteur signale tout paiement PayPal dont le coût estimé dépasse 2 % (`PAYPAL_COST_ABOVE_THRESHOLD`). La « validation en 1 clic » dépend de votre banque : l'agent prépare l'ordre complet (bénéficiaire du coffre, montant, référence = clé d'idempotence) ; vous le signez dans l'e-banking. Vérifier à l'ouverture du compte professionnel (B14) si la banque accepte l'import d'un fichier de paiement à signer, ce qui réduit la saisie à une validation.

Sources des hypothèses de coût : recherche web du 4 octobre 2026 sur les tarifs PayPal Suisse. Les extraits de résultats indiquent 3 % à 4 % au-dessus du taux de change de base pour une conversion, et 3,4 % + 0,55 CHF pour une transaction commerciale reçue (à la charge du vendeur, souvent répercutée). Pages d'origine des extraits : <https://www.paypal.com/ch/webapps/mpp/paypal-fees>, <https://www.paypal.com/ch/business/paypal-business-fees>, <https://wise.com/fr-ch/blog/paypal-frais-suisse>. Ces pages n'ont **pas pu être ouvertes** depuis l'environnement des agents (accès bloqué) : les valeurs sont des hypothèses prudentes **à vérifier sur la grille officielle le jour de la signature**.

## 9. Formulaire à remplir

Remplir les valeurs (ou les dicter à l'agent 01, qui les reporte dans `config/mandate.v1.yaml` sans rien d'autre), puis signer selon le §10.

**Période et plafonds**

| Champ | Clé YAML | Proposé | Votre valeur |
|---|---|---|---|
| Début de validité | `valid_from` | Date de signature | ________ |
| Fin de validité | `valid_until` | Fin du pilote (J90) | ________ |
| Plafond par transaction | `limits.per_transaction_chf` | 500 CHF | ________ |
| Plafond mensuel autonome | `limits.per_month_chf` | 3 000 CHF | ________ |
| Budget stock de référence (base des 25 %) | `limits.stock_budget_chf` | 3 000 CHF | ________ |
| Plafond jour publicité | `limits.ads_daily_cap_chf` | 33 CHF | ________ |
| Quota d'envois de la boîte dédiée | `limits.email_daily_send_quota` | 20 / jour | ________ |
| Part maximale par extension | `limits.extension_max_share` | 25 % (= stop-loss) | 25 % (fixe) |
| Réserve de trésorerie | `limits.cash_reserve_chf` | 1 600 CHF (= stop-loss) | 1 600 CHF (fixe) |

**Catégories déléguées** (supprimer une ligne = ne pas déléguer)

| Catégorie | Clé | Enveloppe proposée (BP §3) | Niveau min. | Votre enveloppe |
|---|---|---:|---:|---|
| Stock scellé FR | `STOCK` | 3 000 CHF | 4 | ________ |
| Accessoires | `ACCESSORIES` | 300 CHF (10 % du stock, BP §1) | 4 | ________ |
| Échantillons payants | `SAMPLES` | 100 CHF | 1 | ________ |
| Site et outils | `SITE_TOOLS` | 1 500 CHF (180 CHF/mois) | 1 | ________ |
| DA et contenus | `DA_CONTENT` | 400 CHF | 1 | ________ |
| Emballages et matériel | `PACKAGING` | 300 CHF | 1 | ________ |
| Étiquettes et port des commandes payées | `SHIPPING` | 600 CHF | 2 | ________ |
| Test publicitaire | `ADVERTISING` | 500 CHF | 3 | ________ |
| Fiduciaire, juriste, assurances, contrats | `ADMIN` | **Non délégable** | — | — |

**Bénéficiaires autorisés** : **aucun** tant que vous ne les avez pas validés (C08, checklist `docs/02-sourcing/CHECKLIST_DUE_DILIGENCE_FOURNISSEUR.md`). Modèle de ligne (exemple FICTIF) :

| `supplier_id` | Libellé | Catégories | Moyens | Plafond / transaction (option) | Validé le | Due diligence | Référence coffre (`payee_ref`) |
|---|---|---|---|---|---|---|---|
| `FICTIF_EMBALLAGES` | Fournisseur d'emballages (fictif) | `PACKAGING` | `PAYPAL` | 150 CHF | 2026-10-10 | checklist remplie | `coffre:beneficiaires/FICTIF_EMBALLAGES` |

**Coût PayPal estimé** (`paypal`) : frais 3,4 % ; fixe 0,55 CHF ; change 4 % ; signalement au-delà de 2 % — à confirmer sur la grille officielle.

**Signature**

| Champ | Clé YAML | Valeur |
|---|---|---|
| Nom | `approval.approved_by` | ________ |
| Date et heure (avec fuseau) | `approval.approved_at` | ________ (ex. `2026-10-12T18:30:00+02:00`) |
| Empreinte | `approval.fingerprint_sha256` | ________ (calculée au §10) |

## 10. Signer, modifier, révoquer

**Signer (≈ 15 minutes)**

1. Remplir le §9 dans `config/mandate.v1.yaml`, y compris `approved_by` et `approved_at`.
2. Calculer l'empreinte :
   ```bash
   cd engine && python -m pokeshop.mandate fingerprint ../config/mandate.v1.yaml
   ```
   La ligne « à remplir » doit afficher `rien`.
3. Recopier l'empreinte dans `approval.fingerprint_sha256` **et** dans le coffre (`POKESHOP_MANDATE_FINGERPRINT`). C'est ce second report, fait par vous seule, qui vaut signature.
4. Relancer la commande : l'état doit être `ACTIF`.

**Modifier** : toute modification (plafond, bénéficiaire, date, signataire) change l'empreinte, donc **désactive le mandat** jusqu'à ce que vous recalculiez l'empreinte et la reportiez dans le coffre. Changer `mandate_version` à chaque modification de valeur.

**Révoquer** : voir §7 (une action : révoquer l'application API PayPal).

## Validation humaine requise

- [ ] Fixer et signer les plafonds du §9 (B01) ; à défaut, les agents restent à 0 CHF de dépense autonome.
- [ ] Valider la liste des bénéficiaires (C08), un par un, avec la checklist de due diligence.
- [ ] Ouvrir le compte PayPal dédié (B05) et appliquer la checklist du §7 (aucune source de secours, limites côté compte si disponibles, 2FA).
- [ ] Générer votre jeton de réarmement et placer son empreinte dans le coffre (`docs/00-pilotage/STOP_LOSS.md` §5).
- [ ] Confirmer la recommandation du §8 : stock par virement validé par vous, PayPal pour les petits achats.
- [ ] Vérifier les frais PayPal sur la grille officielle et corriger `paypal` si besoin.
- [ ] Trancher le paiement de la publicité : le brief commun (`docs/08-agents/BRIEF_COMMUN.md` §8) prévoit le moyen de paiement de l'entité au niveau du compte publicitaire (B20) ; ce mandat n'admet que PayPal ou un virement. Proposition : recharge publicitaire par PayPal si la plateforme l'accepte, sinon validation humaine.
- [ ] Valider les niveaux minimaux par catégorie (stock 4, pub 3, étiquettes 2, autres 1).
