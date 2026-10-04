# SEO — pages d'extension, mots-clés et modèles de métadonnées

> Propriétaire (build) : agent « site-contenu ». Exploitation : agent 08 SEO et rédaction (BL-143 pages d'extension, J70 ; guides), agent 07 (thème, données structurées), agent 12 (contrôle).
> Sources : BP §9 (J61-90 « SEO extensions »), §7 (structure : pages extensions, recherche, fiche produit, « aucune promesse de carte rare ou de valeur »), §11 (agent 8 : « faits produits uniquement sourcés ») ; `site/shopify/STRUCTURE_BOUTIQUE.md` ; `15_SUJETS.md` ; `TON_EDITORIAL.md`.
> **Aucun volume de recherche n'est cité** : aucune donnée de volume n'a été mesurée. Les mots-clés ci-dessous sont des hypothèses d'intention, à confirmer avec Google Search Console (après mise en ligne) et, si un compte publicitaire existe, l'outil de planification de mots-clés de la plateforme.

## 1. Principes

1. Le SEO attire un trafic qualifié au coût d'acquisition le plus bas ; il ne justifie jamais un texte inexact.
2. Une page par intention : une page d'extension, une collection par format, un guide par question. Pas de pages vides « pour le SEO » : une extension n'a de page que si au moins un produit est en stock local, en précommande ouverte ou en alerte de réassort.
3. Faits produits **uniquement** depuis la fiche validée ou l'annonce officielle datée ; source et date notées dans le brouillon de l'agent 08.
4. Ni prix ni disponibilité dans les métadonnées (ils changent plus vite que l'index) ; ni urgence, ni rareté, ni valeur.
5. Français de Suisse romande au lancement ; l'allemand viendra avec une vraie traduction et des URL dédiées (BP §7).

## 2. Structure d'une page d'extension

URL : `/collections/<slug-extension>` (collection automatique par tag `ext:<slug>`, `STRUCTURE_BOUTIQUE.md` §3.3). Index : `/pages/extensions`.

| Ordre | Bloc | Contenu | Source |
|---|---|---|---|
| 1 | Fil d'Ariane | Accueil / Extensions / {Extension} | Thème |
| 2 | H1 | « {Extension} — JCC Pokémon en français » | Nom exact imprimé sur l'emballage FR |
| 3 | Chapeau (2-3 phrases) | Ce qu'est l'extension, sa date de sortie en français, ce que nous proposons | Annonce officielle datée ; statuts du catalogue |
| 4 | Produits | Grille de la collection : statut explicite sur chaque carte (Stock local / Précommande (allocation confirmée) / Rupture – alerte) | Shopify (snippets `da-statut-stock`, `da-badges`) |
| 5 | Les formats de l'extension | Liste factuelle des formats **annoncés** (display, ETB, bundle…), avec mention « proposé chez nous » ou « non proposé » | Annonce officielle ; catalogue |
| 6 | Bon à savoir | Langue (FR), contenu aléatoire des boosters, lien vers la page Précommandes | `TON_EDITORIAL.md` §5 |
| 7 | FAQ (3 questions) | « Quand sort {Extension} en français ? » · « Quelle différence entre le display et l'ETB de {Extension} ? » · « Serez-vous réapprovisionnés ? » (réponse : alerte, aucune date promise) | Faits sourcés |
| 8 | Liens internes | Guides S03 (extension), S01 (ETB/display), S14 (vocabulaire des sorties) ; extensions voisines | `15_SUJETS.md` |

Texte : 200 à 400 mots au-dessus et au-dessous de la grille (repère éditorial, pas une règle de classement). Le texte n'affirme jamais qu'un produit est disponible : c'est la grille qui le montre.

## 3. Mots-clés français (hypothèses d'intention, sans volume)

| Intention | Exemples de requêtes | Page cible |
|---|---|---|
| Achat par format | display pokémon français ; display pokémon fr suisse ; etb pokémon français ; coffret dresseur d'élite ; bundle pokémon fr ; tripack pokémon ; booster pokémon français | Collections de format |
| Achat par extension | {extension} display fr ; {extension} etb ; {extension} français ; précommande {extension} | Page d'extension |
| Achat local | cartes pokémon genève ; boutique cartes pokémon suisse romande ; acheter cartes pokémon en ligne suisse | Accueil, page À propos |
| Cadeau | cadeau cartes pokémon enfant ; idée cadeau pokémon ; coffret pokémon à offrir | Collections « Idées cadeaux », guide S04 |
| Information | différence etb display ; c'est quoi une extension pokémon ; comment reconnaître une carte pokémon française ; protéger ses cartes pokémon ; ranger ses cartes pokémon ; sortie {extension} français date | Guides S01, S03, S06, S05, S12, S14 |
| Service | livraison cartes pokémon suisse ; précommande pokémon comment ça marche | Pages Livraison et retours, Précommandes, guide S07 |

À exclure (contraires au positionnement ou à la loi) : requêtes de rareté ou de valeur (« carte rare garantie », « cote », « investissement »), contrefaçons, cartes à l'unité, autres langues tant qu'elles ne sont pas vendues.

## 4. Modèles de métadonnées

Repères : titre d'environ 60 caractères, description d'environ 150 caractères (affichage tronqué au-delà selon les moteurs ; repère, pas une règle). Nom de la boutique en fin de titre : `{{NOM_BOUTIQUE}}`.

| Page | Balise title | Méta-description |
|---|---|---|
| Accueil | Cartes Pokémon en français, expédiées de Genève · {{NOM_BOUTIQUE}} | Displays, ETB, bundles et coffrets du JCC Pokémon en français. Stock affiché tel qu'il est, livraison en Suisse, frais affichés avant paiement. |
| Collection de format | {Format} Pokémon en français · {{NOM_BOUTIQUE}} | {Format} du JCC Pokémon en français, par extension. Statut clair sur chaque produit : stock local, précommande ou alerte. Livraison en Suisse. |
| Page d'extension | {Extension} — JCC Pokémon en français · {{NOM_BOUTIQUE}} | {Extension} en français : displays, ETB et autres formats, avec leur disponibilité réelle. Expédition depuis Genève, livraison en Suisse. |
| Fiche — stock local | {Titre exact de la fiche} · {{NOM_BOUTIQUE}} | {Format} de l'extension {Extension}, en français, neuf et scellé, en stock local à Genève. Contenu exact et délai indiqués sur la fiche. |
| Fiche — précommande | {Titre exact} — précommande · {{NOM_BOUTIQUE}} | Précommande sur quantité confirmée : {Format} {Extension} en français. Date de sortie et conditions indiquées sur la fiche. |
| Fiche — rupture | {Titre exact de la fiche} · {{NOM_BOUTIQUE}} | {Format} {Extension} en français. Actuellement en rupture : recevez une alerte au retour en stock local. |
| Guide | {Question du guide} · {{NOM_BOUTIQUE}} | {Réponse en une phrase}. Guide simple, sans jargon, par une boutique indépendante de cartes Pokémon en français. |
| Idées cadeaux | Idées cadeaux cartes Pokémon par budget · {{NOM_BOUTIQUE}} | Des produits Pokémon JCC en français classés par budget, en stock local à Genève. Bon sans prix sur demande, livraison en Suisse. |
| Précommandes | Précommandes : comment ça marche · {{NOM_BOUTIQUE}} | Précommandes ouvertes uniquement sur quantité confirmée par écrit. Prix fixé à la commande, information en cas de report. |
| Livraison et retours | Livraison et retours · {{NOM_BOUTIQUE}} | Livraison en Suisse uniquement, délais, suivi, colis abîmé et retours : tout ce qu'il faut savoir avant de commander. |

Textes alternatifs des images : « {Format} {Extension}, version française, {face avant / dos / côté avec la mention de langue} ».

## 5. Règles techniques (agent 07, à vérifier sur le thème retenu)

| Point | Règle |
|---|---|
| Un seul H1 par page | Titre de la fiche, de la collection ou du guide |
| URL | En minuscules, sans accents, mots séparés par des tirets ; jamais modifiées après publication (sinon redirection 301 dans l'admin) |
| Canonique | Celle produite par Shopify ; vérifier que les URL filtrées ne sont pas présentées comme canoniques |
| Données structurées produit | La disponibilité annoncée doit suivre le **statut public** : `InStock` pour `stock_local`, `PreOrder` pour `precommande`, `OutOfStock` pour `rupture`. Un thème standard déclare souvent `InStock` dès qu'il y a de l'inventaire : il marquerait une précommande comme « en stock ». À corriger dans le gabarit JSON-LD du thème à partir de `boutique.statut_stock` (`STRUCTURE_BOUTIQUE.md` §2) |
| Prix dans les données structurées | Prix public de la fiche, en CHF ; jamais un prix barré sans prix antérieur réel |
| Fil d'Ariane | Données structurées `BreadcrumbList` sur collections et fiches |
| Images | Photos réelles, compressées, nommées comme le texte alternatif |
| Langue | `lang="fr-CH"` ; balises `hreflang` à l'arrivée de l'allemand |
| Landing de validation | `noindex` tant qu'elle est en aperçu ; indexable une fois publiée (`site/landing/README.md`) |

## 6. Maillage interne

- Chaque fiche renvoie vers sa page d'extension et vers un guide (S01, S06 ou S10 selon le format).
- Chaque guide renvoie vers une collection **et** vers un autre guide.
- Les pages d'extension se renvoient entre elles (précédente, suivante).
- Accueil → Extensions, Guides, Idées cadeaux.

## 7. Suivi (sans objectif chiffré inventé)

| Indicateur | Outil | Fréquence | Usage |
|---|---|---|---|
| Impressions, clics, position moyenne par page et par requête | Google Search Console (compte créé par la propriétaire, propriété du domaine) | Mensuelle | Remplacer les hypothèses du §3 par les requêtes réelles |
| Commandes payées par source « organique » | Shopify (référents) | Hebdomadaire | CAC proche de zéro : contribue directement à l'étoile polaire |
| Pages sans clic après 90 jours | Search Console | Trimestrielle | Fusionner, réécrire ou retirer |

## 8. Checklist par page publiée (agent 12)

- [ ] Title et description selon le §4, sans prix, sans urgence, sans rareté.
- [ ] H1 unique, faits sourcés (source et date dans le brouillon), lien vers un guide.
- [ ] Données structurées : disponibilité = statut public.
- [ ] Textes alternatifs renseignés ; images réelles.

## Validation humaine requise

- [ ] Valider les modèles de métadonnées (§4) et la liste des requêtes exclues (§3).
- [ ] Créer la propriété Google Search Console du domaine (compte de la propriétaire) et déléguer la lecture à l'agent 08.
- [ ] Agent 07 / propriétaire : accepter la modification du gabarit JSON-LD du thème pour la disponibilité « précommande ».
