# Précommandes — conditions client et règles internes — {{NOM_BOUTIQUE}}

> **À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION**
> Brouillon v0.1 du 4.10.2026, rédigé par l'agent legal-ops. Ce texte n'est pas un avis juridique.
> Sources : BP §1 (« aucune précommande encaissée sans allocation »), §3 (« les précommandes ne portent que sur des quantités fermement allouées » ; réserve de trésorerie), §5 (quota), §7 (date confirmée ou statut incertain, commandes mixtes). CGV ch. 7.
> Partie 1 : texte public (page {{URL_PRECOMMANDES}}). Partie 2 : règles internes appliquées par les agents et le moteur (`engine/pokeshop/stock.py`).

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

## Validation humaine requise

- [ ] Juriste : relire la page publique, notamment le débit immédiat, le délai d'annulation et le seuil de report.
- [ ] Propriétaire : valider la définition de l'allocation ferme (§2.1) et la réserve de sécurité de 10 % (hypothèse).
- [ ] Propriétaire : choisir le moment du débit (à la commande, proposé ici) ; un débit à l'expédition supposerait une autorisation de paiement qui expire avant la plupart des sorties (à vérifier auprès du PSP).
- [ ] Propriétaire : valider les champs « à valider » des précommandes dans `champs_a_remplir.yaml`.
