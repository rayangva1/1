# 15 sujets éducatifs — base de contenus réutilisables

> Propriétaire (build) : agent « site-contenu ». Utilisateurs : agent 08 (articles SEO, guides des fiches), agent 09 (réseaux, emails), propriétaire (tournage, session A06).
> Source : BP §8 « Créer une base de 15 sujets : différence ETB/display, choisir un premier coffret, comprendre une extension, acheter pour offrir, protéger ses cartes, repérer la langue, fonctionnement des précommandes et coulisses d'expédition. Produire les démonstrations et photos réelles lors d'une session groupée ; l'IA décline les légendes, monte les briefs et adapte les formats. » ; BP §9 (1 guide, 1 nouveauté réellement accessible, 1 preuve de service par semaine) ; BP §1 (publics : collectionneurs, parents, joueurs).
> Les sujets 1 à 8 sont ceux du BP ; les sujets 9 à 15 sont proposés par l'agent pour réduire les erreurs d'achat et le SAV. Ton : `TON_EDITORIAL.md`. Calendrier : `CALENDRIER_90J.csv`. Scripts : `SCRIPTS_VIDEO.md`.

## Règles communes à tous les sujets

- **Faits produits** (contenu d'une boîte, nombre de boosters, date) : uniquement depuis une fiche validée (`boutique.contenu_valide`) ou une annonce officielle datée. Un contenu « type » s'énonce comme tel (« souvent », « vérifiez sur la fiche »), jamais comme un fait sur un produit précis.
- **Visuels** : photos et vidéos **réelles** (session A06), gabarits DA `docs/05-da/social/` ; jamais d'emballage, de carte ou de personnage généré ; aucune adresse ni étiquette lisible.
- **Prix** : aucun prix dans un sujet éducatif ; un prix n'apparaît que dans une publication « nouveauté », contrôlé sur la page publique avant diffusion.
- **CTA** : vers un guide, une collection ou l'alerte, jamais « achetez vite ».
- **Mesure** : chaque lien porte un `utm_source` (canal) et un `utm_campaign` = identifiant du sujet (ex. `s01-etb-display`).

## Vue d'ensemble

| N° | Sujet | Pilier | Public principal | Format principal | Déclinaisons | Dépend du stock reçu ? |
|---|---|---|---|---|---|---|
| S01 | ETB ou display : lequel choisir ? | Guide | Collectionneurs, parents | Carrousel 4:5 | Reel 30 s, article SEO | Non (carrousel) / oui (Reel avec produits) |
| S02 | Choisir un premier coffret | Guide | Parents, débutants | Article SEO | Carrousel, email | Non |
| S03 | Comprendre une extension | Guide | Tous | Article SEO (modèle de page d'extension) | Carrousel par extension | Non |
| S04 | Acheter pour offrir : 3 questions | Guide | Parents | Carrousel 4:5 | Article, email de fin d'année | Non |
| S05 | Protéger ses cartes | Guide | Collectionneurs, joueurs | Reel 30 s | Carrousel, fiche accessoire | Oui (accessoires reçus) |
| S06 | Repérer la langue d'un produit | Guide / confiance | Tous | Reel 25 s | Carrousel, FAQ | Oui (un produit FR en main) |
| S07 | Comment marchent nos précommandes | Preuve de service | Collectionneurs | Carrousel 4:5 | Page Précommandes, email | Non |
| S08 | Coulisses d'expédition | Preuve de service | Tous | Reel 40 s | Story, email récapitulatif | Oui (colis réel ou test) |
| S09 | Lire une fiche : les 3 statuts | Preuve de service | Tous | Carrousel 4:5 | Story, landing | Non |
| S10 | Que contient vraiment la boîte ? | Guide | Parents, débutants | Carrousel 1:1 | Article, description de fiches | Oui (produits reçus) |
| S11 | Carte rare garantie ? Non. | Guide / confiance | Parents, nouveaux collectionneurs | Reel 25 s | Carrousel, FAQ | Non |
| S12 | Ranger et classer sa collection | Guide | Collectionneurs | Article SEO | Reel, fiche accessoire | Oui (accessoires) |
| S13 | Scellé et authentique : ce que nous contrôlons | Preuve de service | Tous | Reel 35 s | Carrousel, page À propos | Oui (réception réelle) |
| S14 | Date de sortie, avant-première, réassort : le vocabulaire | Guide | Collectionneurs | Carrousel 4:5 | Article, email | Non |
| S15 | Votre colis : délais, suivi, colis abîmé | Preuve de service | Tous | Carrousel 4:5 | FAQ, email d'expédition | Non |

## Fiches détaillées

### S01 — ETB ou display : lequel choisir ?
- **Angle** : deux formats, deux usages ; on aide à choisir selon l'envie (ouvrir beaucoup ou avoir un coffret complet), pas selon une « valeur ».
- **Hook** : « ETB ou display ? La différence en 30 secondes. »
- **Plan** : 1. Le display : une boîte de boosters d'une même extension (le nombre exact figure sur la fiche ; souvent 36 pour une extension principale, 18 pour un demi-display). 2. L'ETB (coffret Dresseur d'élite) : des boosters + des accessoires de jeu (protège-cartes, dés, marqueurs… selon le coffret). 3. Pour qui : ouvrir à plusieurs, compléter une extension → display ; premier coffret, cadeau, jouer → ETB. 4. Ce qui ne change pas : le contenu des boosters est aléatoire. 5. Où voir le contenu exact : la ligne « Contenu » de chaque fiche.
- **Format** : carrousel 4:5 (6 slides, gabarit `carrousel-4x5-*`) ; Reel 30 s (script V1) ; article SEO « ETB ou display » (SEO.md §4).
- **Visuels réels nécessaires** : un display et un ETB de la même extension, côte à côte, face et dos (mention de contenu lisible) ; contenu d'un ETB étalé **sans ouvrir de produit vendu** (ETB de démonstration acheté et imputé en acquisition, ou photo d'un ETB ouvert à titre privé — décision propriétaire).
- **Faits à sourcer** : contenu de chaque produit montré (fiche validée).
- **CTA** : « Voir la collection Displays / ETB » ; avant ouverture : « Recevoir l'alerte d'ouverture ».

### S02 — Choisir un premier coffret
- **Angle** : guider un débutant ou un parent vers un premier achat simple et adapté, sans surenchère.
- **Hook** : « Premier achat de cartes Pokémon : par où commencer ? »
- **Plan** : 1. Collectionner ou jouer ? 2. Budget : 3 tranches (sans prix de produit), renvoi aux collections « Idées cadeaux ». 3. Les formats d'entrée : booster, tripack/bundle, coffret, ETB. 4. Ajouter des protège-cartes. 5. Vérifier la langue (lien S06).
- **Format** : article SEO (≈ 800 mots) ; carrousel 4:5 ; bloc de l'email de bienvenue.
- **Visuels réels nécessaires** : 3 à 4 produits d'entrée de gamme alignés par taille ; mains d'adulte tenant un coffret (pas d'enfant identifiable sans accord écrit).
- **Faits à sourcer** : contenus des produits montrés.
- **CTA** : « Voir les idées cadeaux par budget ».

### S03 — Comprendre une extension
- **Angle** : expliquer ce qu'est une extension (série de cartes publiée à une date, déclinée en plusieurs produits) pour lire nos pages d'extension.
- **Hook** : « Méga-Évolution, 30ᵉ Anniversaire… c'est quoi, une extension ? »
- **Plan** : 1. Une extension = une série de cartes avec un nom, un symbole et une date de sortie. 2. Elle se décline en displays, ETB, bundles, coffrets. 3. Extensions principales et spéciales. 4. Où lire le nom exact (emballage FR). 5. Notre page par extension : ce qui est en stock local, en précommande, en alerte.
- **Format** : article SEO = gabarit des pages d'extension (SEO.md §2) ; carrousel par extension à chaque sortie réelle.
- **Visuels réels nécessaires** : plusieurs produits d'une même extension (après réception) ; gros plan sur le nom de l'extension sur l'emballage.
- **Faits à sourcer** : nom, date de sortie et liste des produits **depuis l'annonce officielle datée** (pokemon.com/fr ou distributeur) ; ne jamais présenter une date de sortie comme une date d'arrivée chez nous.
- **CTA** : « Voir la page de l'extension » / « Alerte si l'extension arrive en stock ».

### S04 — Acheter pour offrir : 3 questions avant d'acheter
- **Angle** : réduire le mauvais cadeau (mauvaise langue, mauvais format) et donc les retours.
- **Hook** : « Offrir des cartes Pokémon sans se tromper : 3 questions. »
- **Plan** : 1. La personne joue-t-elle ou collectionne-t-elle ? 2. Quelle langue lit-elle (FR chez nous) ? 3. Quel budget ? → renvoi aux collections cadeaux ; bonus : délai d'expédition et date limite avant les fêtes (seulement si confirmée par le transporteur) ; bon sans prix sur demande.
- **Format** : carrousel 4:5 ; article ; bloc de l'email de décembre.
- **Visuels réels nécessaires** : produits emballés pour un cadeau (papier neutre), carte merci DA.
- **Faits à sourcer** : dates limites d'expédition (transporteur, BL-053).
- **CTA** : « Idées cadeaux par budget ».

### S05 — Protéger ses cartes
- **Angle** : gestes simples pour garder des cartes en bon état ; fait vendre des accessoires utiles.
- **Hook** : « 3 gestes pour protéger vos cartes. »
- **Plan** : 1. Protège-cartes (sleeves) au format standard. 2. Classeur à pochettes pour ranger. 3. À l'abri de l'humidité, de la chaleur et du soleil. 4. Manipuler les mains propres et sèches.
- **Format** : Reel 30 s (script V5) ; carrousel ; texte de la fiche accessoire.
- **Visuels réels nécessaires** : mettre une carte dans un protège-carte (gros plan mains), classeur ouvert, boîte de rangement — accessoires réellement en stock.
- **Faits à sourcer** : format des protège-cartes vendus (fiche).
- **CTA** : « Voir les accessoires ».

### S06 — Repérer la langue d'un produit
- **Angle** : notre promesse « en français » se vérifie ; apprendre à ne pas se tromper (sujet n° 1 d'erreur d'achat en ligne).
- **Hook** : « FR, EN ou JP ? Comment repérer la langue d'une boîte. »
- **Plan** : 1. Le nom de l'extension et les textes en français sur l'emballage. 2. Les mentions légales et de sécurité en français. 3. La langue dans le titre de nos fiches (« — FR »). 4. Ce que nous vérifions à la réception (lien S13).
- **Format** : Reel 25 s (script V2) ; carrousel ; entrée de FAQ.
- **Visuels réels nécessaires** : un produit FR, face et dos, gros plans des textes français ; **pas** de produit d'une autre langue acheté pour l'occasion (sauf si déjà possédé à titre privé).
- **Faits à sourcer** : aucun au-delà de l'emballage filmé.
- **CTA** : « Tous nos produits sont en français : voir le stock local ».

### S07 — Comment marchent nos précommandes
- **Angle** : transparence : une précommande n'ouvre que sur quantité confirmée par écrit ; ce qui se passe si la date change.
- **Hook** : « Pourquoi nous n'ouvrons pas de précommande sur chaque sortie. »
- **Plan** : 1. Quantité confirmée par écrit, sinon pas de précommande. 2. Prix fixé à la commande. 3. Date estimée vs confirmée. 4. Report : on vous écrit ; au-delà de {{SEUIL_REPORT_PRECOMMANDE}}, annulation et remboursement possibles. 5. Quantité réduite : servies dans l'ordre de paiement, les autres remboursées.
- **Format** : carrousel 4:5 (texte, gabarit DA) ; reprise de la page Précommandes ; bloc d'email.
- **Visuels réels nécessaires** : aucun produit ; gabarits DA et badges « Précommande ».
- **Faits à sourcer** : `docs/04-legal/PRECOMMANDES.md` (bloc public, version validée par le juriste).
- **CTA** : « Lire nos conditions de précommande ».

### S08 — Coulisses d'expédition
- **Angle** : montrer le soin réel : scan, contrôle, calage, sticker de fermeture ; c'est la preuve de service.
- **Hook** : « Ce qui arrive à votre commande entre le clic et le dépôt du colis. » (nommer le transporteur seulement une fois le contrat signé, B17)
- **Plan** : 1. Bon de préparation. 2. Scan du code-barres. 3. Contrôle langue, scellé, quantité. 4. Calage sur les six faces. 5. Sticker de fermeture. 6. Dépôt et numéro de suivi par email.
- **Format** : Reel 40 s (script V4) ; stories ; bloc de l'email récapitulatif.
- **Visuels réels nécessaires** : session de préparation réelle (SOP colis P1-P12) **sans** nom, adresse ni étiquette lisible, sans écran d'outil interne.
- **Faits à sourcer** : `docs/07-ops/SOP_PREPARATION_COLIS.md`.
- **CTA** : « Voir le stock local ».

### S09 — Lire une fiche : les 3 statuts
- **Angle** : « Stock local », « Précommande (allocation confirmée) », « Rupture – alerte » : ce que chaque mention promet, et ce qu'elle ne promet pas.
- **Hook** : « Stock local, précommande, rupture : ce que ça veut dire chez nous. »
- **Plan** : reprise de la section « Trois statuts, pas de flou » de la landing ; + « nous n'affichons jamais de stock que nous n'avons pas ».
- **Format** : carrousel 4:5 avec les badges DA ; story épinglée.
- **Visuels réels nécessaires** : captures de fiches réelles (après ouverture) ou badges DA (avant).
- **Faits à sourcer** : `site/shopify/MODELE_FICHE_PRODUIT.md` §3.
- **CTA** : « Recevoir l'alerte d'ouverture » puis « Voir le stock local ».

### S10 — Que contient vraiment la boîte ?
- **Angle** : bundle, tripack, coffret, demi-display : le contenu exact, pour comparer sans se tromper.
- **Hook** : « Bundle, tripack, coffret : combien de boosters dedans ? »
- **Plan** : pour chaque produit en stock : nom exact, contenu de la fiche, ce qui n'est pas inclus.
- **Format** : carrousel 1:1 ; article ; ligne « Contenu » des fiches.
- **Visuels réels nécessaires** : chaque produit en stock, face avec la mention de contenu lisible.
- **Faits à sourcer** : `boutique.contenu_valide` de chaque fiche (jamais de contenu « type » présenté comme exact).
- **CTA** : « Comparer dans la collection ».

### S11 — Carte rare garantie ? Non.
- **Angle** : désamorcer la promesse de rareté et de valeur ; renforcer la confiance (BP §7).
- **Hook** : « Peut-on garantir une carte rare ? Non. Voici pourquoi. »
- **Plan** : 1. Le contenu des boosters est tiré au hasard par le fabricant. 2. Aucun revendeur ne peut garantir une carte. 3. Nous ne pesons ni ne trions nos produits. 4. Nous vendons pour collectionner et jouer, pas des placements.
- **Format** : Reel 25 s (face caméra ou texte) ; carrousel ; FAQ.
- **Visuels réels nécessaires** : produits scellés posés (aucune carte rare mise en avant).
- **Faits à sourcer** : FAQ client (`docs/07-ops/FAQ_CLIENTS.md`).
- **CTA** : « Lire notre FAQ ».

### S12 — Ranger et classer sa collection
- **Angle** : du tas de cartes à la collection organisée (classeurs, boîtes, intercalaires) ; accessoires réellement en stock.
- **Hook** : « Votre collection déborde ? 3 façons de la ranger. »
- **Plan** : 1. Classeur à pochettes. 2. Boîte de rangement. 3. Classer par extension (lien S03). 4. Garder les doubles à part.
- **Format** : article SEO ; Reel ; fiche accessoire.
- **Visuels réels nécessaires** : classeur rempli de cartes (collection privée, aucune carte présentée comme « de valeur »), boîte de rangement.
- **Faits à sourcer** : caractéristiques des accessoires (fiche).
- **CTA** : « Voir les accessoires ».

### S13 — Scellé et authentique : ce que nous contrôlons
- **Angle** : nos contrôles à réception (langue, scellé, contenu annoncé sur l'emballage, impression), sans jamais ouvrir un produit ; ce que le client peut vérifier à la livraison.
- **Hook** : « Avant d'être en vente, chaque boîte passe ce contrôle. »
- **Plan** : 1. Comptage et code-barres. 2. Langue FR. 3. Film et scellés intacts. 4. Impression et cohérence. 5. Un doute = pas en vente. 6. À la livraison : photographiez tout dommage et écrivez-nous dans {{DELAI_SIGNALEMENT}}.
- **Format** : Reel 35 s (script V3) ; carrousel ; page À propos.
- **Visuels réels nécessaires** : réception réelle (SOP réception C1-C9), sans document d'achat, facture ou étiquette lisible.
- **Faits à sourcer** : `docs/07-ops/SOP_RECEPTION_STOCK.md` §3 C.
- **CTA** : « Voir le stock local ».

### S14 — Date de sortie, avant-première, réassort : le vocabulaire
- **Angle** : éviter les malentendus (« sorti » ≠ « chez nous ») ; expliquer pourquoi une date peut changer.
- **Hook** : « Sortie, avant-première, réassort : qui fait quoi ? »
- **Plan** : 1. Date de sortie annoncée par l'éditeur. 2. Avant-premières : dans des boutiques participantes, pas chez nous. 3. Arrivée chez un revendeur : après la sortie, selon les livraisons. 4. Réassort : nouvelle livraison, jamais garantie. 5. Notre alerte.
- **Format** : carrousel 4:5 ; article ; email.
- **Visuels réels nécessaires** : aucun produit ; gabarits DA.
- **Faits à sourcer** : calendrier officiel daté (ex. sortie FR de Méga-Évolution – Règne Delta le 6.11.2026 selon l'annonce indexée dans `docs/01-marche/ASSORTIMENT_PILOTE.md`, à reconfirmer avant publication).
- **CTA** : « Recevoir les alertes ».

### S15 — Votre colis : délais, suivi, colis abîmé
- **Angle** : tout ce qui se passe après la commande, et quoi faire si quelque chose ne va pas.
- **Hook** : « Commande passée : et maintenant ? »
- **Plan** : 1. Expédition sous {{DELAI_EXPEDITION}} (stock local). 2. Numéro de suivi par email. 3. Colis bloqué depuis {{SEUIL_COLIS_BLOQUE}} : on ouvre une recherche. 4. Colis abîmé : photos et message sous {{DELAI_SIGNALEMENT}}. 5. Livraison en Suisse uniquement.
- **Format** : carrousel 4:5 ; FAQ ; bloc de l'email d'expédition.
- **Visuels réels nécessaires** : colis fermé avec sticker DA (sans étiquette lisible).
- **Faits à sourcer** : `docs/04-legal/LIVRAISON_RETOURS.md`, champs validés du registre.
- **CTA** : « Lire Livraison et retours ».

## Validation humaine requise

- [ ] Valider la liste des 15 sujets (BL-100) et l'ordre de priorité du calendrier.
- [ ] Décider si un produit de démonstration peut être ouvert pour S01, S10 ou une « ouverture authentique » (imputé en dépense d'acquisition, au coût historique), ou si l'on n'utilise que des photos d'emballages fermés.
- [ ] Autoriser (ou non) l'apparition de vos mains et de votre voix dans les vidéos ; aucune personne identifiable sans accord écrit.
- [ ] Reconfirmer chaque date de sortie citée sur la source officielle avant publication (S03, S14).
