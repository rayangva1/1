# Plan de contenu — pré-drop et jour de drop — {{NOM_BOUTIQUE}}

> Propriétaire (build) : agent « site-contenu ». Exploitation : agent 09 Communication (stories, publications, réponses courantes), agent 08 SEO et rédaction (textes de fiche), agent 11 Opérations et SAV (messages privés, réclamations) ; tournage et live : **la propriétaire** (intervention A06 ; le live est facultatif).
> Sources : décision de la propriétaire du 6.10.2026 (pré-drop = réservation **garantie** avant réception) ; `docs/SPEC.md` §2.11 ; `docs/04-legal/PRECOMMANDES.md`, partie « Pré-drop » et CGV ch. 7.7 à 7.12 ; emails 15 à 19 (`EMAILS/source/emails.yaml`) ; `TON_EDITORIAL.md` ; `docs/07-ops/SOP_RECEPTION_STOCK.md` ; snippets `site/shopify/snippets/da-reservation-garantie.liquid` et `da-badges.liquid`.
> Le calendrier 90 jours (`CALENDRIER_90J.csv`) ne contient **aucun** pré-drop : chaque pré-drop est un événement, déclenché par son ouverture au moteur (`POST /predrop/open`), et planifié avec ce plan. Variables propres à un pré-drop : `{{PRODUIT}}` (titre exact de la fiche normale), `{{DATE_DROP}}` (date du drop du moteur, format 20.10.2026).

## 1. Principes (non négociables)

1. **Un statut et une date, rien d'autre.** On dit « Réservations ouvertes » ou « Réservations fermées » et « Drop le {{DATE_DROP}} ». Jamais de minuteur, d'heure de fermeture, de compte à rebours, de « plus que N », de « dernières réservations », de nombre d'unités reçues, vendues, réservées ou restantes : ce sont des données internes, et une fausse urgence (BP §8, `TON_EDITORIAL.md` §2).
2. **La garantie, expliquée à chaque fois.** Chaque mention du pré-drop reprend, mot pour mot, les deux phrases du moteur (`engine/pokeshop/predrop.py`), affichées aussi sur la fiche :
   - « Le supplément pré-drop paie la garantie d'être servi en premier et expédié dès réception du stock, pas le produit. »
   - « Aucun remboursement de la différence avec le prix du drop, même s'il reste des unités au drop. »
3. **Aucun prix en dur.** « Les deux prix sont sur la fiche » : le prix de la réservation garantie et le prix du drop, lus sur la page publique moins d'une heure avant diffusion (règle 2 du dossier). Aucun coût, aucune marge, aucun nom de fournisseur, aucun écart de prix commenté.
4. **Pas de stock avant la réception réelle.** « En stock local » seulement après la réception contrôlée (SOP réception) ; avant, « Réservation garantie » ou « Drop le … ».
5. **Servis en premier, dans les faits.** Le jour de la réception, les réservations garanties sont préparées **avant** toute vente au prix du drop (SOP réception, étape pré-drop) ; la publication « C'est le drop » attend que la fiche normale soit réellement en stock local.
6. **Aucun produit scellé ouvert.** Le live montre l'ouverture des **cartons de livraison** et le contrôle à l'œil des produits scellés (film, langue, extension) ; jamais l'ouverture d'un booster, d'un display ou d'un coffret vendu (CGV ch. 2.3).
7. **Garde-fous du moteur respectés.** Rien n'est publié sur une référence en gel, sous stop-loss ou en quarantaine, ni quand le pré-drop est désactivé (paramètres non signés) : la fiche affiche alors « Réservations fermées » et la communication s'arrête. Une réduction d'allocation n'est jamais chiffrée en public.
8. **Consentement.** Les annonces par email partent seulement aux inscrits confirmés qui suivent le produit (emails 16 et 17, une fois par pré-drop et par personne) ; jamais de message privé non sollicité.

## 2. Chronologie d'un pré-drop

J = jour du drop (date du moteur). R = jour de la réception réelle du stock (date non garantie : souvent avant J, parfois après).

| Moment | Canal | Contenu | Condition de publication | Responsable |
|---|---|---|---|---|
| Ouverture (fenêtre prioritaire) | Email 16 ; story S-PD1 | Accès prioritaire des inscrits aux alertes du produit | Phase `prioritaire` dans `GET /predrop/offers` ; fiche de réservation publiée et vérifiée | Workflow 06 (email) ; agent 09 (story) |
| Fin de la fenêtre prioritaire | Email 17 (annonce du drop) ; publication S-PD2 | « Drop le {{DATE_DROP}} » : réserver avec garantie ou attendre le drop | Phase `ouvertes` | Workflow 06 ; agent 09 |
| Pendant les réservations | Story S-PD3 (au plus une par semaine) | Rappel de la différence entre les deux prix, réponse aux questions | Phase `ouvertes` ; aucune relance quotidienne | Agent 09 |
| Réservations fermées | Story S-PD4 | « Réservations fermées. Drop le {{DATE_DROP}} » | Phase `fermees` ou fiche de réservation retirée | Agent 09 |
| Réception (R) | Live « ouverture des cartons » (facultatif) ; story S-PD5 | Contrôle à réception, sans chiffre | Réception réelle (`POST /stock/receive`), propriétaire présente | Propriétaire ; agent 09 (légendes) |
| R, préparation | Story S-PD6 | « Les réservations garanties partent en premier » (colis emballés, étiquettes masquées) | Réservations préparées ; aucune donnée client à l'image | Propriétaire (photo) ; agent 09 |
| Expédition des réservations | Email 19 (en plus de l'email 07) | Réservation expédiée en priorité | Envoi Shopify contenant une ligne de réservation | Workflow 06 |
| Jour du drop (J, ou R si plus tard) | Email 04 (alerte stock local) ; publication S-PD7 | « C'est le drop : en stock local au prix du drop » | Fiche normale en stock local réel **après** la préparation des réservations ; aucun gel ni stop-loss | Workflow 06 ; agent 09 |
| J+1 à J+7 | Publication « preuve de service » | Colis partis, délais tenus, questions fréquentes | Faits vérifiés (expéditions enregistrées) | Agent 09 |
| Réduction d'allocation (si elle survient) | Email 18 aux seuls clients remboursés ; story S-PD8 facultative | Ordre de service et remboursement intégral, sans chiffre | Réduction enregistrée au moteur ; remboursements préparés ; validation de la propriétaire pour la story | Workflow 02 (email) ; propriétaire (GO story) |
| Report de la date | Email au client (modèle SAV) ; mise à jour de la fiche | Nouvelle date estimée et options du client | Information reçue et vérifiée | Agent 11 ; agent 09 |

## 3. Textes prêts à publier

Les textes publics sont les lignes citées (`>`). Ils sont contrôlés automatiquement (`outils/verifier_contenu.py`) : aucune urgence, aucun prix en dur, aucune promesse de contenu, aucun terme interne, aucun chiffre de stock.

**S-PD1 — Ouverture prioritaire (story)**

> Réservations garanties ouvertes pour {{PRODUIT}}, d'abord pour les personnes inscrites aux alertes de ce produit. Drop le {{DATE_DROP}}. Les deux prix sont sur la fiche.
> Le supplément pré-drop paie la garantie d'être servi en premier et expédié dès réception du stock, pas le produit.

**S-PD2 — Annonce du drop, ouverture à tous (publication)**

> Drop le {{DATE_DROP}} : {{PRODUIT}}. Deux façons d'acheter, à vous de choisir.
> Réservation garantie : le prix du drop plus un supplément. Vous êtes servi en premier et votre commande est expédiée dès réception.
> Au drop : le prix du drop, s'il reste des unités.
> Aucun remboursement de la différence avec le prix du drop, même s'il reste des unités au drop.

**S-PD3 — Questions sur les deux prix (story)**

> Pourquoi deux prix ? Le supplément pré-drop paie la garantie d'être servi en premier et expédié dès réception du stock, pas le produit.
> Pas besoin de garantie ? Attendez le drop : même produit, au prix du drop, s'il en reste.

**S-PD4 — Réservations fermées (story)**

> Réservations fermées pour {{PRODUIT}}. Drop le {{DATE_DROP}} : au prix du drop, s'il reste des unités. Activez l'alerte sur la fiche pour être prévenu.

**S-PD5 — Réception (story ou live)**

> Les cartons de {{PRODUIT}} sont arrivés à Genève. Nous contrôlons chaque produit sans l'ouvrir : film, langue, extension.

**S-PD6 — Les réservations d'abord (story)**

> Comme promis, les réservations garanties partent en premier : préparées dès réception, avant toute vente au prix du drop.

**S-PD7 — C'est le drop (publication)**

> C'est le drop : {{PRODUIT}} est en stock local à Genève, au prix du drop, expédié sous {{DELAI_EXPEDITION}}. Limite : {{LIMITE_PAR_CLIENT}}.
> Le contenu des boosters est aléatoire : aucune carte précise n'est garantie.

**S-PD8 — Si nous recevons moins que prévu (story facultative, GO de la propriétaire)**

> Nous avons reçu moins d'unités que prévu pour {{PRODUIT}}. Les réservations garanties sont servies en premier, dans l'ordre de leur paiement ; les personnes que nous ne pouvons pas servir sont remboursées intégralement, supplément compris, et prévenues par email.

## 4. Live « ouverture des cartons » (facultatif, propriétaire)

**Avant** : vérifier le cadre — aucune étiquette d'expédition lisible (nom, adresse), aucun bon de livraison ni facture à l'image (prix, quantités, nom du distributeur), aucun écran d'outil interne ; décider à l'avance de ne citer aucun chiffre (cartons, unités, réservations).

**Pendant** (10 à 20 minutes) :

1. Ouvrir les **cartons de livraison**, jamais un produit scellé.
2. Montrer le contrôle à réception : film intact, langue française, extension, contenu annoncé sur l'emballage.
3. Expliquer l'ordre de service : réservations garanties préparées en premier, puis vente au prix du drop à la date annoncée.
4. Répondre aux questions avec les réponses types du §5 ; renvoyer vers la fiche et la page des conditions pour le reste.
5. Ne jamais lancer de minuteur, d'annonce « en direct » d'unités restantes, de tirage au sort ni de code promo improvisé.

**Après** : rediffusion seulement si le cadre est conforme ; aucune donnée personnelle du chat reprise dans une publication.

## 5. Réponses types (commentaires et messages)

**« Pourquoi deux prix ? »**

> Le supplément pré-drop paie la garantie d'être servi en premier et expédié dès réception du stock, pas le produit. Sans garantie, vous pouvez acheter au prix du drop, s'il reste des unités.

**« Il en reste combien ? »**

> Nous n'affichons pas de nombre d'unités : la fiche indique « Réservations ouvertes » ou « Réservations fermées ».

**« S'il en reste au drop, vous me remboursez la différence ? »**

> Non. Aucun remboursement de la différence avec le prix du drop, même s'il reste des unités au drop. C'est indiqué sur la fiche et dans nos conditions.

**« Et si vous recevez moins que prévu ? »**

> Les réservations garanties sont servies en premier, dans l'ordre de leur paiement. Si nous ne pouvons pas vous servir, nous vous remboursons intégralement, supplément compris, et nous vous prévenons par email.

**« Je peux annuler ma réservation ? »**

> Oui, gratuitement {{DELAI_ANNULATION_PRECOMMANDE}} : écrivez-nous avec votre numéro de commande. Remboursement intégral, supplément compris. Conditions : {{URL_PRECOMMANDES}}.

**« Pourquoi je ne peux pas réserver maintenant ? »** (fenêtre prioritaire)

> Pendant les premières heures, les réservations sont réservées aux personnes inscrites aux alertes de ce produit, connectées à leur compte client. Elles s'ouvrent ensuite à tous.

Litige, accusation, donnée personnelle ou demande de remboursement : aucune réponse publique, passage au service client (agent 11, `docs/07-ops/SOP_SAV_RETOURS.md`).

## 6. Interdits (rappel)

| Interdit | Pourquoi | À la place |
|---|---|---|
| Minuteur, heure de fermeture, « dernier jour pour réserver » | Fausse urgence | « Réservations ouvertes » ; « Drop le … » |
| « Plus que N », « X % déjà réservés », « complet en N minutes » | Quantité interne et pression | « Réservations fermées » |
| Prix en dur, comparaison des deux prix en pourcentage d'économie | Prix relus sur la fiche ; pas de promotion déguisée | « Les deux prix sont sur la fiche » |
| « Garanti avant tout le monde », « livré le jour du drop » | Promesse non maîtrisée (date estimée, transporteur) | « Servi en premier, expédié dès réception » |
| Ouvrir un produit scellé pendant le live, montrer des cartes | Contenu aléatoire ; aucun produit ouvert (CGV) | Ouvrir les cartons de livraison seulement |
| Montrer une étiquette, une facture, un bon de livraison | Données personnelles ou internes | Cadre vérifié avant le live |
| Annoncer une réduction d'allocation chiffrée | Donnée interne | Story S-PD8, sans chiffre, avec GO |

## Validation humaine requise

- [ ] Propriétaire : valider les principes (§1), la chronologie (§2) et les textes S-PD1 à S-PD8 ; décider si le live « ouverture des cartons » a lieu (A06).
- [ ] Propriétaire : donner ou refuser le GO de la story S-PD8 à chaque réduction d'allocation.
- [ ] Juriste : relire les textes publics avec les conditions du pré-drop (`docs/04-legal/PRECOMMANDES.md`, partie « Pré-drop »).
- [ ] Agent 09 : brancher chaque publication sur sa condition (phase lue sur `GET /predrop/offers`, stock local réel) et ne rien publier sans elle.
