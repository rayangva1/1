# Ton éditorial — {{NOM_BOUTIQUE}}

> Propriétaire (build) : agent « site-contenu ». Utilisateurs : agents 08 SEO et rédaction, 09 Communication, 10 Acquisition, 11 SAV (réponses), propriétaire (vidéos).
> Source : BP §8 « Définir le ton : précis, accessible, sans jargon inutile, sans fausse urgence. La communication montre les stocks et délais effectivement proposés. Les coûts et marges restent des informations internes. » ; BP §7 (aucune promesse de carte rare ou de valeur) ; BP §9 (pas de message non sollicité) ; `docs/04-legal/USAGE_MARQUES.md`.
> Nom de travail : « Quai des Cartes » (provisoire, non validé). Pourquoi ce ton sert l'étoile polaire : un texte exact évite les mauvais achats, donc les retours et le SAV ; une promesse tenue fait revenir sans payer de publicité.

## 1. Le ton en 4 règles

| Règle | Ce que ça veut dire | Test rapide |
|---|---|---|
| **Précis** | Format, extension, langue, contenu, délai : des faits vérifiables, jamais d'à-peu-près | Chaque phrase factuelle a une source (fiche validée, page publique, SOP) |
| **Accessible** | Un parent qui n'y connaît rien comprend ; un collectionneur ne s'ennuie pas | Un terme de jargon (ETB, display, booster) est expliqué la première fois |
| **Calme** | Aucune fausse urgence, aucune pression, aucune comparaison agressive | On peut lire le message demain sans qu'il soit devenu faux |
| **Honnête** | On dit ce qu'on a, ce qu'on n'a pas, et ce qu'on ne sait pas encore | « Date non confirmée » plutôt qu'une date supposée |

Voix : on vouvoie, on parle au nom de la boutique (« nous »), phrases courtes (20 mots en moyenne), une idée par phrase, verbes actifs. Français de Suisse romande : « septante », « nonante » à l'oral si naturel ; à l'écrit, chiffres. Montants en CHF, devise devant et point décimal comme sur le site et dans les emails de la DA (« CHF 49.90 »), dates au format « 6.11.2026 » ou « 6 novembre 2026 ». Espaces insécables avant « : ; ? ! » et dans « » (contrôlé automatiquement sur les pages).

## 2. Mots et formulations à éviter

| À éviter | Pourquoi | Écrire plutôt |
|---|---|---|
| « Dernières pièces », « bientôt épuisé », « vite ! », « ne ratez pas », compte à rebours, « plus que 2 » | Fausse urgence (BP §8) ; quantité non affichée (SPEC) | « Stock local » ; « Rupture – alerte » ; ou rien |
| « Carte rare garantie », « gros hits », « pépite », « jackpot » | Contenu aléatoire (BP §7, CGV) | « Le contenu des boosters est aléatoire » |
| « Investissement », « prendra de la valeur », « à revendre », « cote » | Promesse de valeur financière (BP §7) | « Pour collectionner ou jouer » |
| « Officiel », « revendeur agréé », « partenaire Pokémon », « boutique Pokémon » | Statut non obtenu (BP §8, `USAGE_MARQUES.md`) | « Produits authentiques, neufs et scellés » ; « boutique indépendante » |
| « Disponible » pour un produit qui n'est pas chez nous | Stock fournisseur ≠ stock boutique (BP §5) | « Pas encore reçu : inscrivez-vous à l'alerte » |
| « Livré le jour de la sortie », « garanti avant Noël » | Non maîtrisé (PRECOMMANDES, transporteur) | « Expédié dès réception » ; « date limite d'expédition conseillée : … (transporteur) » |
| « Meilleur prix de Suisse », « moins cher que… » | Comparaison non prouvée (LCD) | Rien, ou le fait : « prix en CHF, livraison affichée avant paiement » |
| « Promo exceptionnelle », prix barré sans prix antérieur réel | OIP, fausse urgence | Une promotion validée par le moteur, avec ses dates, ou rien |
| Jargon non expliqué : « ETB », « display », « pull », « hit », « rip », « godpack » | Exclut les parents (public BP §1) | « Coffret Dresseur d'élite (ETB) », « boîte de boosters (display) » |
| Toute mention de coût, marge, fournisseur, remise obtenue, quantité allouée | Données internes (SPEC §0.2) | — (jamais) |
| « Dépêchez-vous de vous inscrire » | Pression | « Inscrivez-vous si vous voulez être prévenu » |
| « Une personne vous répond », « un humain lit chaque message » | Faux : les réponses courantes partent sans relecture humaine (LCD art. 3 al. 1 let. b) | « Nous vous répondons ; une personne reprend votre demande si vous le souhaitez » |
| « Le contenu de chaque boîte est vérifié » | Faux : les produits scellés ne sont jamais ouverts | « Langue, scellé et contenu annoncé sur l'emballage vérifiés à réception, sans ouvrir » |
| « Limite par commande » | Les CGV fixent une limite par référence et par foyer, toutes commandes confondues | « Limite : {{LIMITE_PAR_CLIENT}} » |
| Pré-drop : « plus que N réservations », « fermeture dans 2 h », « dernier jour pour réserver », « X % déjà réservés », « économisez en réservant » | Fausse urgence, quantité interne, promotion déguisée (le supplément paie une garantie) | « Réservations ouvertes » / « Réservations fermées » ; « Drop le {{DATE_DROP}} » ; les deux phrases de garantie (`PLAN_JOUR_DE_DROP.md` §1) |

## 3. Exemples avant / après

| Contexte | Avant (à ne pas faire) | Après |
|---|---|---|
| Publication nouveauté | « [émoji flamme] LES DERNIERS DISPLAYS SONT LÀ ! Plus que quelques pièces, foncez avant qu'il soit trop tard !!! » | « Display de l'extension {{EXTENSION}}, en français : en stock local à Genève, expédié sous {{DELAI_EXPEDITION}}. Limite : {{LIMITE_PAR_CLIENT}}. » |
| Précommande | « Précommandez maintenant, livraison garantie le jour J ! » | « Précommande ouverte : quantité confirmée par écrit. Sortie annoncée le {{DATE_SORTIE}} ; nous expédions dès réception. Si la date change, nous vous écrivons. » |
| Contenu d'un booster | « Énormes chances de choper une carte rare [émoji diamant] » | « Chaque booster contient des cartes tirées au hasard par le fabricant : personne ne peut garantir une carte précise. » |
| Valeur | « Un display scellé, c'est le meilleur placement de 2026 » | « Nous vendons des produits pour collectionner et jouer, pas des placements. » |
| Rupture | « Victime de son succès ! » | « Rupture : plus d'unité disponible. Recevez une alerte au retour en stock, sans date promise. » |
| Report | « Petit contretemps [émoji gêné] » | « La sortie de {{PRODUIT}} est reportée au {{NOUVELLE_DATE}} (annonce reçue le {{DATE_ANNONCE}}). Vous pouvez garder votre précommande ou l'annuler sans frais. » |
| Parent | « Le must-have pour tout dresseur qui se respecte ! » | « Pour un premier cadeau : un coffret avec quelques boosters et des accessoires, prêt à offrir. Voici comment choisir selon l'âge et le budget. » |
| Réponse SAV | « Désolé pour le désagrément, nous faisons le maximum. » | « Votre colis est bloqué depuis 5 jours : nous ouvrons une recherche auprès du transporteur aujourd'hui et vous écrivons d'ici {{DELAI_REPONSE_SUPPORT}}. » |
| Publicité | « Le seul vrai shop Pokémon suisse » | « Pokémon JCC en français, expédié depuis Genève. Stock réel, livraison en Suisse. » |

## 4. Règles de contenu (toujours)

1. **Prix et stock** : seulement ceux de la page publique, contrôlés moins d'une heure avant diffusion (**hypothèse**, brief A-09) ; la publication est annulée si la page a changé (escalade E1).
2. **Photos et vidéos** : réelles (session A06) ; jamais d'emballage, de carte ou de personnage généré ; pas d'extrait de dessin animé ni de musique sous droits.
3. **Marque** : « Pokémon » désigne le produit (« display du JCC Pokémon »), jamais la boutique ; aucun logo ni personnage hors de la photo du produit vendu.
4. **Emojis** : au plus un par publication, jamais dans un titre de fiche ni dans un email transactionnel ; jamais flamme, diamant, gyrophare, réveil ou sablier (codes d'urgence ou de rareté).
5. **Majuscules** : pas de mots en capitales pour crier (les titres DA en capitales sont un style graphique, pas un message).
6. **Enfants** : contenus lisibles par des enfants, mais adressés aux adultes pour l'achat ; aucune incitation directe d'enfants à acheter ; publicité ciblée sur les adultes.
7. **Commentaires** : réponse factuelle, courte, sans débat ; litige, accusation de contrefaçon ou donnée personnelle ⇒ aucune réponse publique, escalade A-11 (E2).
8. **Sources** : un fait produit (contenu, date) cite sa source interne (fiche validée) ; une date de sortie reprend l'annonce officielle datée, sans la présenter comme une date d'arrivée chez nous.

## 5. Gabarits de phrases réutilisables

- Statut : « En stock local à Genève · expédié sous {{DELAI_EXPEDITION}} » / « Précommande : quantité confirmée, sortie annoncée le {{DATE_SORTIE}} » / « Rupture : alerte de retour en stock disponible ».
- Limite : « Limite : {{LIMITE_PAR_CLIENT}}, toutes commandes confondues, pour que chacun puisse en profiter. » (la valeur validée dit déjà « par référence et par foyer » : CGV ch. 4.4 ; jamais « par commande »)
- Contenu : « Contenu : {{CONTENU_VALIDE}}. Le contenu des boosters est aléatoire. »
- Livraison : « Livraison en Suisse uniquement ; frais affichés avant le paiement. »
- Pré-drop : « Réservation garantie : le prix du drop plus un supplément. Le supplément pré-drop paie la garantie d'être servi en premier et expédié dès réception du stock, pas le produit. Aucun remboursement de la différence avec le prix du drop, même s'il reste des unités au drop. » Statut : « Réservations ouvertes » ou « Réservations fermées », et « Drop le {{DATE_DROP}} » ; jamais d'heure de fermeture ni de nombre d'unités (`PLAN_JOUR_DE_DROP.md`).
- Clôture d'un guide : « Une question ? Répondez à ce message ou écrivez-nous : nous vous répondons. »
- Service client : « Les réponses courantes sont préparées et envoyées par des outils automatisés, à partir de modèles que nous validons ; une personne reprend votre demande si vous le souhaitez. » Ne jamais affirmer qu'un humain lit et traite chaque message : c'est faux dans notre modèle d'opération (SOP SAV, principe 4 bis).

## Validation humaine requise

- [ ] Valider les 4 règles du ton et la liste des formulations interdites (BL-100, RACI L42).
- [ ] Valider la règle sur les emojis (au plus un, liste noire) et le tutoiement exclu (vouvoiement partout).
- [ ] Confirmer le délai de contrôle prix/stock avant diffusion (hypothèse : moins d'une heure).
