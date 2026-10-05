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
- **Signé = empreinte reportée par vous dans le coffre** (`POKESHOP_MANDATE_FINGERPRINT`, §10). Une empreinte recopiée dans le YAML ne suffit jamais : n'importe quel agent sait la calculer. Sans l'empreinte du coffre, le mandat reste inactif (`MANDATE_NOT_SIGNED`).
- **Aucun chiffre décisif n'est fourni par l'agent qui demande** : trésorerie, solde PayPal, exposition par extension, taux de change, proposition de réassort et plafonds viennent des **registres du moteur** (§4). Faute de registre, la demande part en validation humaine.

## 2. Les trois issues d'une demande de dépense

| Issue (code) | Signification | Ce qui se passe | Délai |
|---|---|---|---|
| `APPROVED_WITHIN_MANDATE` | Toutes les règles du §4 sont respectées | L'agent 05 paie par la passerelle PayPal ; l'entrée est journalisée | Paiement dans l'heure (`can_execute`), sinon nouvelle demande (un rejeu tardif est refusé, §6) |
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
| Solde PayPal dédié suffisant | (relevé du connecteur, `POST /treasury/paypal-balance`, moins de 60 minutes ; perdu au redémarrage) | Le solde chargé | Inconnu, périmé ou insuffisant : validation humaine (rechargement par vous) |
| Plafond jour publicité | `limits.ads_daily_cap_chf` | 33 CHF (≈ 500 CHF / 15 jours, BP §9) | Stop-loss pub : campagnes coupées jusqu'au lendemain |
| Quota d'envois de la boîte dédiée | `limits.email_daily_send_quota` | 20 envois / jour | Envois suivants mis en attente |
| Fraîcheur des photos trésorerie et stop-loss (date de la **photo**, pas de l'évaluation) | `limits.snapshot_max_age_minutes` | 60 minutes | Demande refusée, à recalculer |
| Âge de chaque entrée de la photo (revue R5, R4-DOC-10) : la photo est datée du **plus ancien relevé de cash** (PayPal, banque : relevés horaires du connecteur) ; la **déclaration des dettes** de l'agent 05 (quotidienne) a un âge accepté **explicite** de 24 h (`state_max_age_hours` du stop-loss signé) et ne vieillit pas la photo ; vos **créances** restent en vigueur jusqu'à votre prochain relevé de créances ; les factures enregistrées non payées sont toujours à jour | `state_max_age_hours` | Cash : 60 min pour une dépense autonome ; dettes : 24 h | Relevé de cash de plus de 60 min : demande refusée, à recalculer ; dettes de plus de 24 h : aucune photo (dépenses refusées) |
| Étoile polaire et photo **complètes** : aucune commande au coût des ventes en attente (revue R5, R4-NEW-01 : une commande payée expédiée avant l'inscription du coût de réception est enregistrée, son coût des ventes dérivé ensuite) | — | — | Incomplètes : validation humaine (`TREASURY_UNVERIFIED`, motif listé dans `unverified`) |
| Trésorerie lue dans les **registres du moteur** : cash et exposition par extension de la dernière photo stop-loss acceptée, solde PayPal relevé par un connecteur (`POST /treasury/paypal-balance`) ; une trésorerie jointe à la demande est **ignorée** | — | — | Aucune photo : validation humaine (`TREASURY_UNAVAILABLE`) |
| Chaque poste de la photo (soldes, dettes et créances, stock au coût historique, activité publicitaire, factures) déposé par un **autre** rôle que celui qui demande (matrice `docs/08-agents/MATRICE_API.md`) ; le jeton commun ne dépose rien (403) ; relais `n8n-08-mandat` : demandeur parmi les agents qui dépensent (jamais `qa-conformite` ni `catalogue` : 403), imposé par le webhook de l'agent (un secret par agent), trésorerie non vérifiée ; photo **construite par le moteur** (une photo déposée est un acte de la propriétaire, cash recoupé avec les relevés) ; créances : relevé de la propriétaire seule ; dépense pub sans relevé du connecteur publicitaire de moins de 24 h : non vérifiable | — | Un jeton par rôle (`POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>`) | Poste déposé par le demandeur ou relais : validation humaine (`TREASURY_UNVERIFIED`, postes listés dans `unverified`) |
| Taux de change de **référence** (registre des taux, saisi par vous ou source officielle datée, `POST /fx/rates`) ; le montant CHF est calculé à ce taux | — | Taux du jour ou du jour ouvré précédent | Aucun taux frais : validation humaine (`FX_RATE_UNVERIFIED`) ; taux déclaré à plus de 1 % : **refus** (`FX_RATE_MISMATCH`) |
| Achat de stock adossé à une proposition **enregistrée** du moteur (`POST /stock/reorder-proposal`, `justification_ref` = son `inputs_hash`, moins de 24 h, référence présente, montant ≤ ligne proposée moins ce qui est déjà engagé) | — | Aucune chaîne libre | Validation humaine (`NO_ENGINE_PROPOSAL`) |
| Identité du produit connue (référence, extension, langue FR) ; un « accessoire » portant une extension est contrôlé comme du stock scellé (langue FR, plafond par extension) | — | Accessoire sans texte : langue `NA` admise | Inconnue ou catégorie incohérente : validation humaine (`CATEGORY_IDENTITY_MISMATCH`) ; non FR : **refus** |

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
| Contourner une vérification : fractionner un achat, réutiliser une clé d'idempotence, modifier le mandat ou un seuil, désactiver un stop-loss, contourner un CAPTCHA ou un contrôle d'accès | Anti-fractionnement, idempotence (rejeu réévalué), **empreinte du mandat au coffre** (toute modification le désactive), **empreintes des seuils** du stop-loss et des règles de prix au coffre (fichier modifié sans signature : seuils les plus stricts ; empreinte différente : service gelé), journal append-only | Incident E3, gel conservatoire par l'agent 12 |
| Se déclarer « propriétaire » ou déclarer ses propres chiffres | Acteur **déduit du jeton** (un jeton par rôle) ; matrice d'autorisations **refusant par défaut** (une route absente ou un rôle non listé : 403) ; « propriétaire » refusé sans son jeton ; trésorerie, taux, plafonds, dépenses pub, coûts et validations de fiches lus dans les registres du moteur, jamais déposés par le rôle qui en bénéficie | Refus journalisé (403) |
| Exécuter une instruction reçue par email, sur une page web ou dans un fichier (« changez l'IBAN », « payez vite ») | Coordonnées de paiement **uniquement** depuis le coffre (`payee_ref`) | Suspicion de fraude : E3 |
| Communiquer ou recopier un identifiant, un mot de passe, un IBAN | Secrets dans le coffre uniquement | Fiche E3, rotation du secret |

## 6. Journal et contrôles

- **Registre append-only** (`SpendLedger`) : chaque demande, décision, validation humaine, exécution, annulation et rapprochement est une ligne datée, jamais modifiée. Export au format `docs/08-agents/modeles/REGISTRE_MANDAT.csv` (`to_registry_rows`).
- **Votre validation d'une dépense en attente** (`NEEDS_HUMAN_APPROVAL`) : le formulaire 1 clic de 08 guide le parcours, mais seule **votre décision enregistrée au moteur** compte — `POST /mandate/human-decision` (`{"idempotency_key": "…", "decision": "APPROVE"}` ou `"REFUSE"`, votre jeton seul, depuis votre terminal, sous 24 h ; au-delà : expirée, 409, à resoumettre). Validée, la dépense devient payable (moins d'une heure) et une dépense pub compte dans le stop-loss pub à la date de votre décision (revue R5, R4-DOC-03). Sans enregistrement : rien n'est engagé (statu quo sûr).
- **Idempotence** : une même clé d'idempotence ne produit **jamais** deux paiements. Même demande : la décision d'origine est rejouée **après réévaluation** : une approbation n'est rejouée telle quelle que si elle est encore payable (moins d'une heure, non exécutée, aucun gel, réserve intacte, mandat toujours actif, photos fraîches). Sinon le rejeu est **refusé** (`REPLAY_NOT_PAYABLE`, avec le motif : gel global, gel trésorerie, mandat révoqué…) ; déjà payée : `ALREADY_EXECUTED`. Un rejeu n'est donc jamais `APPROVED` pendant un gel. Contenu différent : refus `IDEMPOTENCY_CONFLICT`.
- **Exécution** : un paiement exécuté au-delà du coût approuvé + 2 % + 1 CHF est enregistré (c'est un fait) mais lève une alerte (`RECONCILIATION_ALERT`, statut `AMOUNT_ABOVE_APPROVAL` au rapprochement).
- **Rapprochement quotidien** (agent 12) des paiements avec le relevé PayPal et le relevé bancaire (`reconcile`) :

| Résultat | Sens | Action |
|---|---|---|
| `OK` | Paiement retrouvé, montant à 0,05 CHF près | — |
| `AMOUNT_MISMATCH` | Montant différent | Fiche E2 |
| `AMOUNT_ABOVE_APPROVAL` | Payé (ou débité) au-delà du montant approuvé + 2 % + 1 CHF | Fiche E3 + vous prévenir |
| `UNKNOWN_DEBIT` | Débit sans demande au registre : **dépense non autorisée possible** | **Gel global manuel immédiat** + fiche E3 + vous prévenir |
| `MISSING_ON_STATEMENT` | Paiement annoncé, absent du relevé après 3 jours | Fiche E2 |

## 7. Sécurité des accès

| Élément | Où il vit | Qui le détient | Règle |
|---|---|---|---|
| Mots de passe et 2FA de la boîte dédiée, de PayPal, de la banque | Coffre de secrets (B03) et votre téléphone | **Vous** | Le second facteur reste sur votre appareil ; les agents passent par les connecteurs, jamais par votre session |
| Identifiants API PayPal | Credentials n8n, alimentés par le coffre | Passerelle n8n | Jamais dans le chat, le dépôt, un prompt ou un rapport |
| Coordonnées des bénéficiaires (IBAN, adresse PayPal) | Coffre, référencées par `payee_ref` | Vous (saisie), passerelle (lecture) | Jamais tirées d'un email ; tout changement reçu = fraude présumée |
| Empreinte du mandat signé | Variable `POKESHOP_MANDATE_FINGERPRINT` du coffre (**obligatoire**) et `approval.fingerprint_sha256` du YAML | Vous | C'est le report au coffre qui vaut signature : sans lui le mandat est inactif ; un YAML modifié ne correspond plus à l'empreinte du coffre, le mandat devient inactif |
| Empreintes des seuils (stop-loss, règles de prix) | `POKESHOP_STOPLOSS_FINGERPRINT`, `POKESHOP_RULES_FINGERPRINT` (coffre) | Vous | Absentes : chaque seuil vaut le plus strict entre le fichier et la référence du code ; différentes du fichier : service gelé jusqu'à nouvelle signature |
| Jetons des rôles | **Un jeton par rôle** de la matrice d'autorisations versionnée (`engine/pokeshop/authz.py`, table `docs/08-agents/MATRICE_API.md`) : agents de `.claude/agents/` et connecteurs n8n ; empreintes dans `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` (coffre ; un nom inconnu de la matrice fait échouer le démarrage) ; credentials n8n nommés par rôle (références seulement dans les exports) | Vous (génération), chaque agent ou credential n8n (le sien) | **Refus par défaut** : chaque écriture n'est admise que pour les rôles listés ; l'acteur journalisé est déduit du jeton ; le jeton commun (facultatif, `POKESHOP_API_TOKEN_SHA256`) ne fait que lire et simuler (toute écriture : 403) ; séparation des rôles : `acquisition` ne déclare pas sa dépense pub (`connecteur-publicite`, MAX avec les paiements pub **engagés** du mandat : approuvés ou exécutés ; sans connecteur, aucune campagne), `catalogue` ne valide pas ses fiches (vous, `POST /catalog/approvals`), `finance-pricing` n'enregistre un coût qu'adossé à une réception d'`operations-sav` et à ± 2 % d'une référence du moteur (facture enregistrée par `n8n-03-factures` après votre validation, ou offre évaluée ; sinon vous) ; secrets de passerelle n8n : un par agent, jamais partagé |
| Taux de change de référence | Registre des taux (`POST /fx/rates`, votre jeton) | Vous | **Seule source de taux** du moteur : aucun `fx_*` n'est accepté d'un appelant sur `/sync/run` ni `/catalog/cost-inputs` (422) ; sans taux frais, coût incomplet (fiche en brouillon) et dépense en devise en validation humaine. Source officielle datée (ex. cours de la BNS) ; valable le jour même et le jour ouvré suivant |
| Apports et retraits de capital | Registre du capital (`POST /capital/movements`, votre jeton, ajout seul) | Vous | **Seule source** des mouvements de capital du stop-loss global : une photo qui en déclare est refusée (422) |
| Test de correction d'un incident (préalable à la reprise) | Journal des incidents (`POST /incidents/{id}/test`) | Agent 12 QA (`qa-conformite`, différent de l'ouvreur) ou vous (votre jeton) | Un test réussi cite un cycle `/sync/run` réel (non FICTIF) PROPRE en simulation, catalogue lu au registre, postérieur à l'ouverture, **lancé par un autre principal** que l'attestant, sur le fournisseur et la référence de l'incident — **sauf** incident portant sur des données FICTIVES (déduit par le moteur), ou déclaré `simulation: true` et ouvert alors que le moteur est en simulation (`POKESHOP_DRY_RUN=true`) : un cycle FICTIF suffit alors (un incident sur données réelles ouvert sans ce drapeau exige un cycle réel, revue R5) ; écritures réelles activées, un incident déclaré « simulation » est traité comme réel (revue R4, R3-DOC-04) ; tout autre rôle, l'ouvreur ou le jeton commun : 403 |
| Jeton de réarmement du stop-loss global | Votre gestionnaire de mots de passe ; seule son empreinte `POKESHOP_OWNER_TOKEN_SHA256` est dans le coffre | **Vous seule** | Ne jamais le coller dans le chat d'un agent |

**Compte PayPal dédié = plafond physique naturel.** Il est séparé de vos comptes personnels et n'est approvisionné **que** du budget délégué, par virement depuis le compte professionnel. Ce que les agents peuvent perdre au pire, c'est le solde chargé. À faire à l'ouverture (B05) :

- [ ] Ne charger que l'enveloppe du mois (proposé : le plafond mensuel, 3 000 CHF au maximum).
- [ ] Vérifier dans les paramètres PayPal qu'**aucune source de financement de secours** (carte, prélèvement) ne peut compléter un paiement au-delà du solde ; si ce n'est pas garanti, ne lier aucune carte.
- [ ] Activer, si l'offre PayPal le permet, des **limites de paiement côté compte** : c'est une deuxième barrière, indépendante du logiciel. Fonctionnalité **à vérifier** avec PayPal.
- [ ] Activer la 2FA sur votre appareil.

**Révocation de la dépense en une action.** Révoquer l'application API PayPal utilisée par n8n (tableau de bord développeur PayPal) : tout paiement s'arrête aussitôt, quel que soit l'état du logiciel. Ensuite, à votre rythme : **vider `POKESHOP_MANDATE_FINGERPRINT` dans le coffre** (le mandat devient inactif au redémarrage), ou révoquer par `POST /mandate/revoke` (acte protecteur : tout rôle nommé ou vous ; jamais le jeton commun) ou par `approval.revoked_at` dans le mandat. Une révocation est inscrite dans un **registre en ajout seul** (journal d'état `mandate_revocations`) : effacer ensuite `revoked_at` du YAML ne réactive jamais le mandat révoqué ; seule une nouvelle signature (nouvelle empreinte) le remplace. Puis geler le stop-loss global et changer le mot de passe de la boîte dédiée si besoin.

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
| Budget stock de référence (base des 25 %, accessoires compris) | `limits.stock_budget_chf` | 3 000 CHF (= `stock.stock_budget_chf` des règles de prix : une valeur différente gèle le service tant que les deux ne sont pas alignées et signées) | ________ |
| Plafond jour publicité | `limits.ads_daily_cap_chf` | 33 CHF | ________ |
| Quota d'envois de la boîte dédiée | `limits.email_daily_send_quota` | 20 / jour | ________ |
| Part maximale par extension | `limits.extension_max_share` | 25 % (= stop-loss) | 25 % (fixe) |
| Réserve de trésorerie | `limits.cash_reserve_chf` | 1 600 CHF (= stop-loss) | 1 600 CHF (fixe) |

**Catégories déléguées** (supprimer une ligne = ne pas déléguer). Les accessoires font partie du budget stock (BP §1 : 10 % du stock) : le moteur refuse un mandat où `STOCK` + `ACCESSORIES` dépasse `limits.stock_budget_chf`.

| Catégorie | Clé | Enveloppe proposée (BP §3) | Niveau min. | Votre enveloppe |
|---|---|---:|---:|---|
| Stock scellé FR (90 % du budget stock) | `STOCK` | 2 700 CHF | 4 | ________ |
| Accessoires (10 % du budget stock, BP §1) | `ACCESSORIES` | 300 CHF (stock + accessoires = 3 000 CHF) | 4 | ________ |
| Site et outils | `SITE_TOOLS` | 1 500 CHF (180 CHF/mois) | 1 | ________ |
| DA et contenus | `DA_CONTENT` | 400 CHF | 1 | ________ |
| Emballages et matériel | `PACKAGING` | 300 CHF | 1 | ________ |
| Test publicitaire | `ADVERTISING` | 500 CHF | 3 | ________ |
| Fiduciaire, juriste, assurances, contrats | `ADMIN` | **Non délégable** (700 CHF au BP §3) | — | — |

Total délégable au BP §3 : 2 700 + 300 + 1 500 + 400 + 300 + 500 = **5 700 CHF** ; avec l'administration (700) et la réserve (1 600), 8 000 CHF.

**Hors BP §3** (pas de ligne au budget initial : à financer explicitement, sinon supprimer la ligne du YAML)

| Catégorie | Clé | Proposé | Niveau min. | Financement | Votre enveloppe |
|---|---|---:|---:|---|---|
| Échantillons payants | `SAMPLES` | 100 CHF | 1 | Pris sur l'enveloppe stock (réduire `STOCK` d'autant) ou décision de votre part | ________ |
| Étiquettes et port des commandes payées | `SHIPPING` | 600 CHF | 2 | Couvert par le port facturé aux clients (dépense adossée à des commandes payées) | ________ |

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
3. Recopier l'empreinte dans `approval.fingerprint_sha256` **et** dans le coffre (`POKESHOP_MANDATE_FINGERPRINT`). C'est ce second report, fait par vous seule, qui vaut signature : **sans lui, le mandat reste inactif** même si le YAML porte une empreinte correcte (un agent sait la calculer, pas écrire dans le coffre).
4. Relancer la commande avec la variable du coffre chargée : la ligne « coffre » doit afficher `conforme` et l'état `ACTIF`.
5. Signer de la même façon les **seuils** : `python -m pokeshop.stoploss fingerprint ../config/stoploss.v1.yaml` → `POKESHOP_STOPLOSS_FINGERPRINT` ; `python -m pokeshop.stoploss rules-fingerprint ../config/pricing_rules.v1.yaml` → `POKESHOP_RULES_FINGERPRINT`. Sans ces empreintes, le moteur applique, seuil par seuil, la valeur la plus stricte entre le fichier et sa référence (BP) ; avec une empreinte différente du fichier, le service démarre gelé.
6. Générer **un jeton par rôle utilisé** de la matrice (`docs/08-agents/MATRICE_API.md`, intervention B22, J2) : les 10 connecteurs n8n et les 7 agents qui ont `CONN-API-MOTEUR` (03, 04, 05, 07, 10, 11, 12). Les agents 01, 02, 06, 08 et 09 n'ont pas d'accès à l'API : aucun jeton tant que leur connecteur n'est pas ouvert ; 01, 02, 06 et 09 demandent leurs dépenses par le workflow 08 (webhook à leur nom, secret de passerelle ci-dessous), l'agent 08 ne dépense pas. Trois temps, toujours dans cet ordre.

   **a. Sur votre ordinateur, à J2 : générer** (dossier privé, rien sur le serveur ni dans le dépôt ; vérifié le 5.10.2026 : 17, 17 et 10 lignes, et l'API lancée avec ces empreintes accepte chaque jeton sous son rôle) :
   ```bash
   mkdir -m 700 -p ~/pokeshop-jetons && cd ~/pokeshop-jetons && umask 077
   for role in n8n-01-sync n8n-02-commandes n8n-03-factures n8n-04-incidents n8n-05-digest n8n-06-marketing \
               n8n-07-stoploss n8n-08-mandat connecteur-tresorerie connecteur-publicite \
               donnees-fournisseurs catalogue finance-pricing site-integrations acquisition operations-sav qa-conformite; do
     jeton="$(openssl rand -hex 32)"
     var="POKESHOP_ROLE_TOKEN_SHA256_$(printf '%s' "$role" | tr 'a-z-' 'A-Z_')"
     printf '%s\t%s\n' "$role" "$jeton" >> jetons-roles.txt
     printf '%s=%s\n' "$var" "$(printf '%s' "$jeton" | sha256sum | cut -d' ' -f1)" >> empreintes-roles.env
   done
   # un secret par credential « Passerelle … » de orchestration/README.md §4, jamais commun à deux agents :
   for passerelle in 03-agent-05-finance-pricing 04-agent-12-qa-conformite 06-agent-11-operations-sav \
                     08-agent-01-chef-de-projet 08-agent-02-sourcing 08-agent-06-direction-artistique \
                     08-agent-07-site-integrations 08-agent-09-communication 08-agent-10-acquisition 08-agent-11-operations-sav; do
     printf '%s\t%s\n' "$passerelle" "$(openssl rand -hex 32)" >> secrets-passerelles.txt
   done
   wc -l jetons-roles.txt empreintes-roles.env secrets-passerelles.txt   # 17, 17 et 10 ; sinon : shred -u *, recommencer
   ```

   **b. Ranger, sur votre ordinateur** : recopier chaque ligne de `jetons-roles.txt` (jetons **en clair**) et de `secrets-passerelles.txt` dans le coffre (B03), une entrée par rôle ou par passerelle, ainsi que le fichier `empreintes-roles.env` (empreintes seulement), puis `shred -u jetons-roles.txt secrets-passerelles.txt`. Chaque jeton n'est ensuite remis, depuis le coffre, qu'à **un** destinataire : le credential n8n « Pokeshop API — jeton nommé <rôle> » (`orchestration/README.md` §4, créé par vous : à J8 pour 04 et 06, à J26 pour les autres) ou l'agent de ce rôle (référence `POKESHOP_AGENT_TOKEN_REF`). Chaque secret de passerelle va dans **deux** endroits seulement : la valeur du credential n8n « Passerelle … » correspondant et l'agent nommé (référence au coffre) ; le secret de 06 n'appartient qu'à l'agent 11, si bien qu'aucun autre agent ne déclare une réception au nom d'`operations-sav`.

   **c. Sur le serveur, à J8 (B27) : transférer, contrôler, ajouter** au fichier de variables créé par `sudo install -D -m 600 -o "$USER" .env.example /etc/pokeshop/api.env` (README « Démarrage ») :
   ```bash
   # sur votre ordinateur (remplacer « serveur » par l'adresse SSH du serveur de B27) : empreintes seulement, aucun jeton
   scp ~/pokeshop-jetons/empreintes-roles.env serveur:~/empreintes-roles.env
   # sur le serveur : 17 lignes, toutes « POKESHOP_ROLE_TOKEN_SHA256_…=<64 hexadécimaux> », sinon rien n'est ajouté
   test "$(grep -cE '^POKESHOP_ROLE_TOKEN_SHA256_[A-Z0-9_]+=[0-9a-f]{64}$' ~/empreintes-roles.env)" -eq 17 \
     && test "$(wc -l < ~/empreintes-roles.env)" -eq 17 \
     && cat ~/empreintes-roles.env >> /etc/pokeshop/api.env && shred -u ~/empreintes-roles.env
   scripts/compose.sh config --quiet   # depuis le dépôt, sur le serveur : aucune variable manquante
   # sur votre ordinateur, une fois le contrôle passé (la copie du coffre reste) :
   shred -u ~/pokeshop-jetons/empreintes-roles.env
   ```
   Un contrôle qui échoue n'ajoute rien (fichier tronqué, doublé ou modifié) : recopier le fichier depuis le coffre et recommencer. Les empreintes `POKESHOP_ROLE_TOKEN_SHA256_N8N_07_STOPLOSS`, `…_CONNECTEUR_TRESORERIE` et `…_FINANCE_PRICING` sont **obligatoires** pour lancer la pile. Pile sur votre ordinateur (essai local) : mêmes commandes sans `scp`, avec `~/pokeshop-jetons/empreintes-roles.env` à la place de `~/empreintes-roles.env`. Les secrets de passerelle ne vont **jamais** dans `/etc/pokeshop/api.env` (le moteur ne les connaît pas, n8n les vérifie). Le jeton commun (`POKESHOP_API_TOKEN_SHA256`, facultatif) ne fait que lire et simuler (toute écriture : 403) et ne sert qu'au tableau de bord (`dashboard/build.py`) ; ni lui ni votre jeton ne vont dans n8n ou chez un agent. **Votre jeton suffit seul** pour tous vos actes et vos lectures (en-tête `X-Pokeshop-Owner-Token`, aucun `X-Pokeshop-Token` requis en plus, revue R4).
7. Enregistrer vos apports (et tout retrait) : `POST /capital/movements` avec votre jeton (`X-Pokeshop-Owner-Token`, seul en-tête nécessaire), corps `{"movement_id": "APPORT-1", "at": "AAAA-MM-JJTHH:MM:SS+01:00", "kind": "CONTRIBUTION", "amount": "8000", "ref": "virement …"}`. Sans apport enregistré, aucune photo du stop-loss n'est acceptée et toute dépense reste refusée. Commande prête, sur le serveur (même fonction `api` que `STOP_LOSS.md` §5 : jeton saisi sans écho, jamais en argument ni dans l'historique) :
   ```bash
   read -rs OWNER_TOKEN
   api() { curl -sS --fail-with-body -X "$1" "http://127.0.0.1:8000$2" -H 'Content-Type: application/json' \
             -H @<(printf 'X-Pokeshop-Owner-Token: %s\n' "$OWNER_TOKEN") ${3:+-d "$3"}; echo; }
   api POST /capital/movements '{"movement_id": "APPORT-1", "at": "AAAA-MM-JJT10:00:00+01:00", "kind": "CONTRIBUTION", "amount": "8000", "ref": "virement du AAAA-MM-JJ"}'
   api GET  /capital/movements
   unset OWNER_TOKEN
   ```

**Modifier** : toute modification (plafond, bénéficiaire, date, signataire) change l'empreinte, donc **désactive le mandat** jusqu'à ce que vous recalculiez l'empreinte et la reportiez dans le coffre. Changer `mandate_version` à chaque modification de valeur.

**Révoquer** : voir §7 (une action : révoquer l'application API PayPal ; puis vider l'empreinte du coffre ou `POST /mandate/revoke`, révocation définitive pour cette empreinte).

**Saisir un taux de change** (achat en devise) : `POST /fx/rates` avec votre jeton (`X-Pokeshop-Owner-Token`, seul en-tête nécessaire), corps `{"currency": "EUR", "rate_to_chf": "0.9375", "rate_date": "AAAA-MM-JJ", "source": "BNS, cours du jour"}`. Valable le jour même et le jour ouvré suivant ; sans taux frais, toute demande en devise attend votre validation.

## Validation humaine requise

- [ ] Fixer et signer les plafonds du §9 (B01) **et reporter l'empreinte dans le coffre** ; à défaut, les agents restent à 0 CHF de dépense autonome.
- [ ] Signer les seuils du stop-loss et les règles de prix (empreintes au coffre, §10 étapes 5) ou accepter que les valeurs les plus strictes s'appliquent.
- [ ] Générer un jeton par rôle de la matrice d'autorisations (§10 étape 6) : sans eux, aucune écriture n'est possible, aucune dépense n'est approuvée seule, aucune photo du stop-loss n'est déposée et seul votre jeton peut attester un test de correction.
- [ ] Enregistrer vos apports de capital (§10 étape 7) avant le point zéro du stop-loss (C19).
- [ ] Confirmer la ventilation du budget stock (stock 2 700 + accessoires 300 = 3 000 CHF) et décider du financement de `SAMPLES` et `SHIPPING` (hors BP §3).
- [ ] Valider la liste des bénéficiaires (C08), un par un, avec la checklist de due diligence.
- [ ] Ouvrir le compte PayPal dédié (B05) et appliquer la checklist du §7 (aucune source de secours, limites côté compte si disponibles, 2FA).
- [ ] Générer votre jeton de réarmement et placer son empreinte dans le coffre (`docs/00-pilotage/STOP_LOSS.md` §5).
- [ ] Confirmer la recommandation du §8 : stock par virement validé par vous, PayPal pour les petits achats.
- [ ] Vérifier les frais PayPal sur la grille officielle et corriger `paypal` si besoin.
- [ ] Trancher le paiement de la publicité : le brief commun (`docs/08-agents/BRIEF_COMMUN.md` §8) prévoit le moyen de paiement de l'entité au niveau du compte publicitaire (B20) ; ce mandat n'admet que PayPal ou un virement. Proposition : recharge publicitaire par PayPal si la plateforme l'accepte, sinon validation humaine.
- [ ] Valider les niveaux minimaux par catégorie (stock 4, pub 3, étiquettes 2, autres 1).
