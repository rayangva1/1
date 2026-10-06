# Précommandes — conditions client et règles internes — {{NOM_BOUTIQUE}}

> **À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION**
> Brouillon v0.2 du 6.10.2026 (v0.1 du 4.10.2026 + pré-drop), rédigé par l'agent legal-ops. Ce texte n'est pas un avis juridique.
> Sources : BP §1 (« aucune précommande encaissée sans allocation »), §3 (« les précommandes ne portent que sur des quantités fermement allouées » ; réserve de trésorerie), §5 (quota), §7 (date confirmée ou statut incertain, commandes mixtes). CGV ch. 7. **Pré-drop** : décision de la propriétaire du 6.10.2026 (réservation garantie avant réception), `docs/SPEC.md` §2.11, `engine/pokeshop/predrop.py` (textes de garantie `GUARANTEE_TEXT_FR` et `NO_DIFFERENCE_REFUND_FR`, repris mot pour mot ci-dessous), paramètres signés `config/predrop.v1.yaml`.
> Partie 1 : texte public (page {{URL_PRECOMMANDES}}), dont la partie « Pré-drop : la réservation garantie ». Partie 2 : règles internes appliquées par les agents et le moteur (`engine/pokeshop/stock.py`, `engine/pokeshop/predrop.py`). Notes pour le juriste sur le pré-drop : P1 à P10.

<!-- TEXTE_PUBLIC:DEBUT -->
## Précommandes : comment ça marche

Une précommande vous permet de réserver un produit avant sa réception chez nous. Ces conditions complètent nos conditions générales de vente ({{URL_CGV}}).

### Uniquement sur quantité confirmée

- Nous ouvrons une précommande **uniquement** lorsque notre fournisseur nous a confirmé par écrit la quantité qui nous est attribuée.
- Le nombre de précommandes ouvertes ne dépasse jamais cette quantité. Quand le badge « Précommande » disparaît, la quantité est épuisée.
- Nous n'ouvrons jamais de précommande sur une simple annonce de sortie.

### Date de sortie

- La date affichée est une **date estimée**, communiquée par le fournisseur. Lorsque la date n'est pas encore confirmée, la fiche l'indique.
- Nous expédions votre précommande dès que nous l'avons reçue et contrôlée, en principe dans un délai de {{DELAI_EXPEDITION}} après sa réception. Nous ne garantissons pas une livraison le jour de la sortie.

### Prix et paiement

- Le prix est fixé au moment de votre commande et ne change plus.
- Le montant est débité au moment de la commande.
- La limite de quantité s'applique aussi aux précommandes : {{LIMITE_PAR_CLIENT}} pour les nouveautés.

### Si la date change

- Nous vous informons de tout report dans un délai de {{DELAI_INFORMATION_REPORT}}.
- Si le report dépasse {{SEUIL_REPORT_PRECOMMANDE}} par rapport à la date annoncée lors de votre commande, vous pouvez annuler votre précommande et être remboursé intégralement.

### Si nous recevons moins que prévu

- Il arrive qu'un fournisseur réduise la quantité attribuée. Dans ce cas, les précommandes sont servies **dans l'ordre de leur paiement**.
- Les précommandes qui ne peuvent pas être servies sont annulées et remboursées intégralement dans un délai de {{DELAI_REMBOURSEMENT}}. Nous vous prévenons par email.

### Si le produit change

Si le contenu du produit livré par le fabricant diffère de manière importante de celui annoncé lors de votre commande, nous vous en informons avant l'expédition et vous pouvez annuler avec remboursement intégral.

### Annuler votre précommande

- Vous pouvez annuler gratuitement {{DELAI_ANNULATION_PRECOMMANDE}} : écrivez-nous à {{EMAIL_SUPPORT}} avec votre numéro de commande. Le remboursement intervient dans un délai de {{DELAI_REMBOURSEMENT}}.
- Passé ce délai, la politique de retour volontaire s'applique après réception (article scellé, non ouvert, dans un délai de {{DELAI_RETOUR_VOLONTAIRE}}).

### Commande avec des articles en stock et en précommande

Les articles en stock local partent dès qu'ils sont prêts. La précommande est expédiée séparément, dès sa réception. Les frais de livraison ne sont facturés qu'une fois.

### Contenu aléatoire

Comme pour tout produit scellé, le contenu des boosters est aléatoire : aucune carte précise, aucune rareté et aucune valeur de revente ne sont garanties.

## Pré-drop : la réservation garantie

Pour certains produits, nous ouvrons avant leur réception une **réservation garantie** (« pré-drop »). C'est une précommande : les règles ci-dessus s'appliquent (quantité confirmée par écrit, débit à la commande, date estimée), avec les règles suivantes, qui priment pour les réservations garanties.

### Deux prix, affichés côte à côte

- Avant votre commande, la fiche affiche deux prix : le **prix de la réservation garantie** et le **prix du drop**, c'est-à-dire le prix de vente du produit à partir de la date du drop, s'il en reste.
- Le prix de la réservation garantie est le prix du drop augmenté d'un supplément. Il ne dépasse jamais le prix du drop de plus de 10 %.
- Le supplément pré-drop paie la garantie d'être servi en premier et expédié dès réception du stock, pas le produit.
- Aucun remboursement de la différence avec le prix du drop, même s'il reste des unités au drop.
- Le prix payé est fixé à la commande et débité immédiatement. Il ne change plus, ni à la hausse ni à la baisse.

### Ce que garantit le supplément

- **Servi en premier** : les réservations garanties sont servies avant toute vente au prix du drop, dans l'ordre de leur paiement.
- **Expédié dès réception** : votre commande est préparée dès la réception et le contrôle du produit, avant les commandes passées au prix du drop, et remise au transporteur en principe dans un délai de {{DELAI_EXPEDITION}} après la réception.
- **Remboursé intégralement si nous ne pouvons pas vous servir**, supplément compris (voir « Si nous recevons moins que prévu »).

Le supplément ne garantit pas une livraison à une date précise (la date du drop est une date estimée), ni un contenu, une carte ou une rareté. Il ne garantit pas non plus qu'il ne restera aucune unité au drop.

### Statut des réservations

- La fiche indique seulement « Réservations ouvertes » ou « Réservations fermées », et la date du drop. Nous n'affichons ni minuteur ni nombre d'unités restantes.
- Une partie seulement de la quantité confirmée par écrit est ouverte en réservation garantie ; une réserve de sécurité est conservée ; le reste est vendu au prix du drop.
- Les réservations ferment quand la quantité ouverte en réservation est atteinte, au plus tard à la date du drop, ou si nous les suspendons par précaution.
- **Accès prioritaire** : pendant les {{FENETRE_PRIORITAIRE_PREDROP}} qui suivent l'ouverture, seules les personnes inscrites aux alertes de ce produit (inscription confirmée), connectées à leur compte client avec la même adresse email, peuvent réserver. Les réservations s'ouvrent ensuite à tous.

### Limite par client

- La limite est de {{LIMITE_RESERVATION_PREDROP}}, toutes commandes confondues. Le foyer est défini comme pour les quantités limitées (CGV ch. 4.4).

### Une réservation payée en dehors de ces règles

Si votre paiement arrive alors que les réservations sont fermées ou suspendues, pendant l'accès prioritaire sans en remplir les conditions, au-delà de la limite par client, ou pour un autre montant que le prix affiché, la réservation n'est pas servie : nous la remboursons intégralement, supplément compris, dans un délai de {{DELAI_REMBOURSEMENT}}, et nous vous prévenons par email.

### Si nous recevons moins que prévu (réservations)

- Les réservations garanties sont servies **en premier**, dans l'ordre de leur paiement : la quantité prévue pour la vente au prix du drop est réduite d'abord.
- S'il manque encore des unités, les dernières réservations payées sont annulées et remboursées intégralement, supplément compris, dans un délai de {{DELAI_REMBOURSEMENT}}. Nous vous prévenons par email.

### Si la date du drop change

- Nous vous informons de tout report dans un délai de {{DELAI_INFORMATION_REPORT}}. Votre réservation reste servie en premier et expédiée dès réception.
- Si le report dépasse {{SEUIL_REPORT_PRECOMMANDE}} par rapport à la date annoncée lors de votre réservation, vous pouvez annuler et être remboursé intégralement, supplément compris.

### Annuler votre réservation garantie

- Vous pouvez annuler gratuitement {{DELAI_ANNULATION_PRECOMMANDE}} : écrivez-nous à {{EMAIL_SUPPORT}} avec votre numéro de commande. Le remboursement est intégral, supplément compris, dans un délai de {{DELAI_REMBOURSEMENT}}.
- Si le contenu du produit livré par le fabricant diffère de manière importante de celui annoncé lors de votre réservation, nous vous en informons avant l'expédition et vous pouvez annuler avec remboursement intégral, supplément compris.
- Après l'expédition, la politique de retour volontaire s'applique (article scellé, non ouvert, dans un délai de {{DELAI_RETOUR_VOLONTAIRE}}).
<!-- TEXTE_PUBLIC:FIN -->

## Partie 2 — Règles internes (ne pas publier)

### 2.1 Définition de l'« allocation ferme »

Le BP ne définit pas ce qu'est une allocation ferme (voir le rapport de l'agent legal-ops, écarts BP). Définition appliquée :

| Une allocation est **ferme** si… | Elle n'est **pas** ferme si… |
|---|---|
| le fournisseur l'a confirmée **par écrit** (email, confirmation de commande, portail avec export daté) | elle est orale, « prévisionnelle », « sous réserve », « estimée » |
| elle indique la référence exacte (GTIN, langue FR, extension, format, contenu) | la langue ou le contenu sont inconnus (fiche en brouillon, BP §5) |
| elle indique une **quantité** et un **prix d'achat** | le prix ou les frais sont inconnus (aucun prix public, BP §5) |
| la commande fournisseur correspondante est passée et validée selon le mandat | aucun bon de commande n'est passé |
| la donnée a moins de 24 h ou n'a pas été démentie depuis | la donnée amont a plus de 24 h sans confirmation (BP §5 : bloque les nouvelles promesses) |

### 2.2 Ouverture d'une précommande — checklist (agent catalogue + agent opérations)

- [ ] Preuve écrite de l'allocation archivée (chemin ou lien, date, quantité, prix) et liée à la référence dans `preorder_allocations`.
- [ ] Décision de prix du moteur au statut `OK` (contribution ≥ cible) ou `REVIEW` validée ; jamais `BLOCKED` ni `DRAFT`.
- [ ] Quota calculé par le moteur : `preorder_quota(allocation ferme, précommandes engagées, réserve)` (`engine/pokeshop/stock.py`). Réserve de sécurité proposée : 10 % de l'allocation arrondis au supérieur, au moins 1 unité (hypothèse à valider).
- [ ] Exposition de l'extension ≤ 25 % du budget stock **en comptant** la commande fournisseur (stop-loss extension, BP §1).
- [ ] Stop-loss cash : l'achat de l'allocation ne fait pas passer le cash disponible prévu sous 1 600 CHF sur 13 semaines. Les encaissements de précommandes sont **réservés** (non disponibles pour un autre achat) jusqu'à l'expédition (BP §3).
- [ ] Fiche : badge « Précommande », date estimée ou mention « date non confirmée », quantité autorisée, lien vers cette page.
- [ ] Le texte de la fiche ne promet ni livraison le jour de la sortie, ni contenu, ni rareté.
- [ ] Niveau d'autonomie ≥ 3 pour une ouverture automatique ; sinon validation de la propriétaire (BP §13).

### 2.3 Événements et actions

| Événement | Délai d'action | Action automatique | Escalade |
|---|---|---|---|
| Report annoncé par le fournisseur | {{DELAI_INFORMATION_REPORT}} | Email aux clients concernés (modèle SAV-M06) ; mise à jour de la date sur la fiche | Report > {{SEUIL_REPORT_PRECOMMANDE}} : annulations proposées au client |
| Allocation réduite | même jour | Quota recalculé ; vente fermée si quota = 0 ; liste des commandes servies par ordre de paiement ; remboursement des non servies | Si plus de 5 commandes annulées : information à la propriétaire |
| Allocation annulée | même jour | Précommandes fermées ; remboursement intégral de toutes les commandes | Propriétaire informée (incident INC-12) |
| Contenu modifié par le fabricant | avant expédition | Information du client, option d'annulation | — |
| Prix d'achat facturé plus élevé que prévu | à réception de la facture | **Aucune** modification du prix des commandes conclues (BP §5) ; contribution réalisée recalculée (workflow facture → marge) | Si contribution < 12 % ou < 8 CHF par commande : stop-loss produit pour les **nouvelles** ventes |
| Annulation client dans le délai | {{DELAI_REMBOURSEMENT}} | Remboursement ; unité remise dans le quota | — |
| Réception de l'allocation | jour de réception | SOP réception, puis passage en stock local et expédition des précommandes avant toute nouvelle vente | — |

### 2.4 Comptabilité et trésorerie

- Un encaissement de précommande est une **avance client** tant que le produit n'est pas expédié : il n'entre pas dans le cash disponible pour de nouveaux achats ou de la publicité (BP §3, « ne pas traiter tout encaissement comme disponible »).
- Le prévisionnel 13 semaines (`engine/pokeshop/treasury.py`) inclut les remboursements possibles de précommandes.

### 2.5 Pré-drop (réservation garantie) — règles internes

Décision de la propriétaire du 6.10.2026. Le moteur applique ces règles (`engine/pokeshop/predrop.py`, routes `/predrop/*` de `docs/08-agents/MATRICE_API.md`) ; aucune valeur décisive n'est fournie par l'agent qui en bénéficie.

| Règle | Application | Qui |
|---|---|---|
| Paramètres signés (`config/predrop.v1.yaml` : supplément 8 %, plafond du code 10 % ; part ouverte en pré-drop 50 % ; réserve d'au moins 1 unité et 10 % ; limite 1 par client, 2 au plus ; fenêtre prioritaire 24 h ; seuil de demande 0,5) | Sans empreinte au coffre (`POKESHOP_PREDROP_FINGERPRINT`) ou fichier modifié : pré-drop **désactivé**, réservations fermées, toute réservation payée remboursée | Propriétaire (signature, C32) |
| Allocation **ferme** | Même définition qu'au §2.1 ; enregistrée par la propriétaire, ou par le workflow 03 après sa validation de la confirmation écrite (`POST /predrop/allocations`) ; jamais par l'agent qui ouvre le pré-drop | Propriétaire (C33) ; agent 02 (extraction), workflow 03 |
| Éligibilité (toutes requises) | Allocation ferme ; quota ≥ 1 ; score de demande (inscrits consentants intéressés, compte **agrégé**, / allocation) ≥ seuil ; fiche validée (C30) ; coût connu du moteur ; prix drop sans blocage et au-dessus des planchers ; marge du prix pré-drop revérifiée ; prix pré-drop ≤ référence marché (inconnue : validation de la propriétaire) ; aucun gel du stop-loss ni quarantaine | Moteur (`GET /predrop/eligibility`) ; ouverture : agents 01 et 05 ou propriétaire |
| Deux prix | Prix drop = `decide_price` (inchangé) ; prix pré-drop = prix drop × (1 + supplément), arrondi de la grille, ≤ prix drop × 1,10 et ≤ référence marché ; figés à l'ouverture | Moteur |
| Réservations payées | Enregistrées par le workflow 02 (identifiant client **haché**) ; idempotentes ; hors quota, limite, fenêtre, montant ou pré-drop fermé : non servies et remboursement intégral préparé | Workflow 02 |
| Réduction d'allocation | Plan de service : réservations servies en premier (ordre de paiement), quota drop réduit d'abord, puis remboursement intégral des dernières réservations, avec email (18) ; réservations fermées dès l'annonce (workflow 03) | Workflow 03 (validation de la propriétaire, 72 h) ; agent 11 (réduction constatée à la réception) |
| Annulation demandée par le client | Sur demande **écrite** : annulation libre (refusée par le moteur à partir de la date du drop), report au-delà de `SEUIL_REPORT_PRECOMMANDE`, contenu modifié : `POST /predrop/reservations/{order_id}/cancel` avec la référence de la demande ; remboursement intégral préparé ; l'unité revient au quota | Agent 11 ; propriétaire (validation du remboursement) |
| Remboursements | Préparés par le moteur, validés par la propriétaire en un clic aux niveaux d'autonomie 1 et 2 (`POST /predrop/refunds/{refund_id}/approve`), approuvés par le moteur dès le niveau 3, exécutés et relevés par le workflow 02 | Propriétaire (C34) ; workflow 02 |
| Réception | Les réservations confirmées sont préparées **avant** toute mise en vente au prix du drop ; seul le reste entre dans le stock vendable de la fiche normale (`docs/07-ops/SOP_RECEPTION_STOCK.md`, étape pré-drop) | Propriétaire (A03) ; agent 11 |
| Dette jusqu'à livraison | L'argent encaissé est une **dette** dérivée du registre des réservations (photo du stop-loss) jusqu'à l'expédition ou au remboursement exécuté ; chiffre d'affaires reconnu à l'expédition (`docs/00-pilotage/STOP_LOSS.md`, `ETOILE_POLAIRE.md`) | Moteur |
| Communication | Statut « Réservations ouvertes / fermées » et date du drop seulement ; aucun minuteur, aucun nombre d'unités, aucun coût ni marge (`docs/06-contenu/PLAN_JOUR_DE_DROP.md`, emails 15 à 19) | Agent 09 ; workflow 06 |

| Événement (pré-drop) | Délai d'action | Action automatique | Escalade |
|---|---|---|---|
| Paramètres non signés ou modifiés | immédiat | Pré-drop désactivé ; fiche de réservation retirée ; réservations payées non servies, remboursement préparé | Propriétaire : signer (C32) |
| Réduction d'allocation annoncée | même jour | Réservations fermées (acte protecteur) ; plan de service après la validation de la propriétaire ; remboursements préparés, email 18 après exécution | Propriétaire : valider le formulaire 03 et les remboursements |
| Report de la date | {{DELAI_INFORMATION_REPORT}} | Email au client (modèle SAV-M06) ; date de la fiche mise à jour | Report > {{SEUIL_REPORT_PRECOMMANDE}} : annulation proposée (motif `DATE_POSTPONED`) |
| Demande d'annulation écrite | {{DELAI_REMBOURSEMENT}} | Remboursement intégral préparé (motif `CUSTOMER_CANCELLATION` ou `PRODUCT_CHANGED`) | Propriétaire : validation en un clic (niveaux 1-2) |
| Réception du stock | jour de réception | Réservations préparées en premier ; email 19 à l'expédition | Écart de quantité : réduction (`POST /predrop/allocations/{product_key}/reduce`) |

## Notes pour le juriste — pré-drop (ne pas publier)

| # | Point | Choix fait dans le brouillon | Question | Base |
|---|---|---|---|---|
| P1 | Nom « réservation garantie » | La garantie porte sur l'ordre de service (servi avant la vente au prix du drop) et l'expédition dès réception, pas sur la livraison en toutes circonstances : les dernières réservations peuvent être remboursées si le fournisseur réduit la quantité | Le terme « garantie » est-il trompeur au regard de cette limite (indication inexacte) ? Alternative : « réservation prioritaire ». La limite est-elle assez visible (fiche, page, CGV ch. 7.9, email 15) ? | LCD art. 3 al. 1 let. b [L3] |
| P2 | Clause « aucun remboursement de la différence » | Affichée sur la fiche (encart), la page, les CGV, la FAQ et les emails, avant et après la commande | Validité et caractère insolite d'une clause qui laisse au client le risque d'un prix du drop plus bas ; information suffisante ? | Règle de l'insolite (jurisprudence, p. ex. ATF 135 III 1) ; LCD art. 8 [L3] |
| P3 | Deux prix affichés | Le prix du drop est présenté comme un prix futur, jamais comme un prix barré ni une « économie » ; le supplément est au plus de 10 % | L'affichage simultané d'un prix futur est-il conforme à l'indication des prix (auto-comparaison, prix de référence) ? Faut-il afficher le supplément en francs ? | OIP [L9] ; LCD art. 3 al. 1 let. b |
| P4 | Accès prioritaire des inscrits | Réservé pendant {{FENETRE_PRIORITAIRE_PREDROP}} aux inscrits confirmés aux alertes du produit, connectés à leur compte client ; attesté par une étiquette du compte client et le consentement | Information LPD suffisante (nouvelle ligne « Réservation garantie » de `CONFIDENTIALITE.md`, note C10) ? Un paiement hors critère pendant la fenêtre est remboursé intégralement : suffisant ? | LPD art. 19 [L5] |
| P5 | Annulation libre | Même délai que les précommandes ({{DELAI_ANNULATION_PRECOMMANDE}}), remboursement intégral **supplément compris** ; refusée par le moteur à partir de la date du drop | Option de la propriétaire : supplément non remboursé en cas d'annulation libre (il a payé une priorité). Équilibre de la clause ? | LCD art. 8 ; CO art. 1 ss |
| P6 | Réduction d'allocation | Réservations servies dans l'ordre de paiement ; remboursement intégral des dernières, sans autre indemnité | La restitution intégrale suffit-elle (impossibilité non fautive) ? Formulation de l'indisponibilité exceptionnelle (CGV ch. 4.5) adaptée au pré-drop ? | CO art. 97, 119 [L4] |
| P7 | Limite par client | {{LIMITE_RESERVATION_PREDROP}} ; contrôle automatique sur un identifiant client haché, foyer au sens du ch. 4.4 ; excédent non servi et remboursé intégralement | Même analyse que J3 des CGV (clause insolite ou abusive) | Jurisprudence de l'insolite ; LCD art. 8 |
| P8 | Débit immédiat d'une livraison future | Débit à la commande ; l'argent encaissé est traité comme une dette jusqu'à l'expédition (photo du stop-loss), sans compte séparé | Information du client sur le risque en cas de défaillance de la boutique ? Faut-il un compte séparé ? | CO ; BP §3 |
| P9 | Retour volontaire après expédition | La politique volontaire s'applique (CGV ch. 10) ; remboursement du prix payé (supplément compris, lecture littérale du ch. 10.4) | Le supplément (service rendu : priorité) doit-il être remboursé lors d'un retour volontaire ? | CGV ch. 10 ; CO art. 197 ss (garantie inchangée) |
| P10 | TVA du supplément | Le supplément fait partie du prix de vente (même prestation, même taux) | À confirmer par la fiduciaire (B13) selon le statut TVA (B10) | LTVA |

## Validation humaine requise

- [ ] Juriste : relire la partie publique « Pré-drop : la réservation garantie » et trancher P1 à P10 (en particulier P1, le terme « garantie », et P2, l'absence de remboursement de la différence).
- [ ] Propriétaire : valider les choix du pré-drop (annulation libre supplément compris, P5 ; retour volontaire, P9), les champs `LIMITE_RESERVATION_PREDROP` et `FENETRE_PRIORITAIRE_PREDROP` (alignés sur `config/predrop.v1.yaml`, contrôlé par `check_predrop_alignment`), puis signer les paramètres (C32).
- [ ] Juriste : relire la page publique, notamment le débit immédiat, le délai d'annulation et le seuil de report.
- [ ] Propriétaire : valider la définition de l'allocation ferme (§2.1) et la réserve de sécurité de 10 % (hypothèse).
- [ ] Propriétaire : choisir le moment du débit (à la commande, proposé ici) ; un débit à l'expédition supposerait une autorisation de paiement qui expire avant la plupart des sorties (à vérifier auprès du PSP).
- [ ] Propriétaire : valider les champs « à valider » des précommandes dans `champs_a_remplir.yaml`.
