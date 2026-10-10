# Structure de la boutique Shopify — {{NOM_BOUTIQUE}}

> Propriétaire (build) : agent « site-contenu ». Exploitation : agent 07 Site (BL-087 thème, collections et pages), agent 04 Catalogue (fiches), agent 08 SEO (textes), agent 12 (recette).
> Sources : BP §7 (structure, fiche, paiement, recette), §5 (stock local ≠ stock fournisseur ; précommande sur allocation ferme), §8 (DA), SPEC §0.2-0.5 ; DA `docs/05-da/components/` ; textes `docs/04-legal/`.
> Nom de travail provisoire : « Quai des Cartes » (non validé). Statut : **proposition à valider** ; rien n'est créé dans Shopify (compte : intervention B15).

## 1. Ce que la boutique doit montrer (BP §7)

| Élément | Exigence BP | Traduction ici |
|---|---|---|
| Accueil | Promesse, nouveautés, produits **réellement disponibles**, sélection cadeaux | Sections du §6 ; une section vide (aucun produit) est **masquée**, jamais remplie par des produits en rupture |
| Collections | Displays, ETB, bundles, coffrets, boosters, accessoires | §3.1, collections automatiques par type de produit |
| Pages | Extensions, précommandes, livraison et retours, FAQ, contact, à propos, CGV, confidentialité, mentions légales | §5 ; textes = blocs publics de `docs/04-legal/` et `docs/07-ops/FAQ_CLIENTS.md` |
| Recherche et filtres | Format, extension, budget, FR, stock local, précommande | §4 (application Search & Discovery) |
| Langue, livraison | Français au lancement ; Suisse uniquement | Marché unique Suisse, CHF ; allemand après validation commerciale (BP §7) |

## 2. Données publiques d'un produit (métachamps `boutique.*` et tags miroirs)

Ces champs sont **les seuls** que le thème lit en plus des champs natifs (titre, prix, images, variantes, inventaire). Ils sont écrits par la publication (`engine/pokeshop/publish.py`, agent integrations) à partir du catalogue validé. **Aucun coût, prix d'achat, marge, fournisseur, allocation chiffrée ou stock amont** n'est jamais écrit dans Shopify (SPEC §0.2) : le filtre de champs publics de `publish.py` doit refuser toute autre clé.

| Métachamp | Type Shopify | Valeurs | Source dans le moteur | Utilisé par |
|---|---|---|---|---|
| `boutique.statut_stock` | Texte sur une ligne | `stock_local` · `precommande` · `rupture` | **Recalculé par le moteur** à chaque publication, jamais repris de la fiche déclarée (`publish.stock_status_for`) : `stock_local` seulement si le registre du stock local (`POST /stock/receive`) a du stock vendable ; `precommande` seulement pour la fiche `-PRECO` couverte par une allocation ferme d'offres fraîches ; sinon `rupture` (une nouvelle référence en rupture reste en brouillon) | Snippets badges, statut, délai ; filtre « Disponibilité » |
| `boutique.langue` | Texte sur une ligne | `FR` (puis `DE`, `EN`… plus tard) | `catalog.normalize_language` ; `UNKNOWN` ⇒ fiche en brouillon, jamais publiée | Badge FR ; filtre « Langue » |
| `boutique.extension` | Texte sur une ligne | Nom exact imprimé sur l'emballage FR | Catalogue (table d'alias des extensions) | Filtre « Extension » ; pages d'extension |
| `boutique.format` | Texte sur une ligne | Libellé FR de `catalog.FORMAT_LABELS_FR` | `catalog.normalize_format` | Filtre « Format » (aussi recopié dans le **type de produit**) |
| `boutique.contenu_valide` | Texte multiligne | Contenu confirmé par écrit (nombre de boosters, accessoires) | Fiche technique de l'offre, contrôlée à réception | Fiche (bloc « Contenu ») |
| `boutique.date_sortie` | Date | AAAA-MM-JJ | Annonce datée (source et date conservées en interne) | Statut et bloc délai |
| `boutique.date_sortie_statut` | Texte sur une ligne | `confirmee` · `estimee` · `inconnue` | Catalogue | Libellé « confirmée » / « estimée, peut changer » |
| `boutique.delai_expedition` | Texte sur une ligne | Ex. « 2 jours ouvrés » (facultatif : sinon réglage du thème) | Registre `DELAI_EXPEDITION` | Statut et bloc délai |
| `boutique.quantite_max` | Entier | ≥ 1 | Règle de limite (`LIMITE_PAR_CLIENT`) | Bloc délai ; contrôle panier (§7) |
| `boutique.alerte_reassort` | Booléen | vrai si l'inscription à l'alerte est ouverte | Catalogue | Badge « Alerte réassort », libellé « Rupture – alerte », formulaire |
| `boutique.fin_de_serie` | Booléen | vrai si aucun réassort possible | Catalogue | Libellé « Rupture » + « Fin de série » |
| `boutique.date_drop` | Date | AAAA-MM-JJ | Pré-drop du registre du moteur (`engine/pokeshop/predrop.py`, date **en vigueur** : un report la met à jour), sur la fiche de réservation **et** sur la fiche normale | Badge « Drop le JJ.MM (date estimée) » (jusqu'au jour du drop), encart de réservation, bloc délai — toujours « (date estimée) » |
| `boutique.reservation_statut` | Texte sur une ligne | `prioritaire` · `ouvertes` · `fermees` | **Calculé par le moteur** (paramètres signés, quota, gel, quarantaine, fenêtre prioritaire) : jamais une heure de fermeture ni un nombre d'unités | Badge « Réservation garantie », statut « Réservations ouvertes / fermées », accès au bouton d'achat |
| `boutique.fiche_liee` | Texte sur une ligne | handle de la fiche jumelle | Fiche normale ↔ fiche de réservation (publication du moteur) | Liens de l'encart (`all_products[handle]`), étiquette d'accès prioritaire `alerte-produit:<handle>` |
| `boutique.prix_drop` | Texte sur une ligne | décimal `209.90` | **Prix du drop figé** à l'ouverture du pré-drop (moteur), sur les deux fiches ; la fiche normale pratique ce prix (prix natif figé jusqu'au jour du drop inclus, sinon fiche de réservation retirée) | Ligne « Au drop » de l'encart, affichée « CHF 209.90 » |
| `boutique.prix_reservation` | Texte sur une ligne | décimal `229.90` | **Prix pré-drop figé** (moteur), égal au prix natif vérifié de la fiche de réservation | Ligne « Réservation garantie » de l'encart, affichée « CHF 229.90 » |

**Tags miroirs**, écrits **dans le même appel** `productSet` que les métachamps (donc jamais désynchronisés) : `statut:stock-local` · `statut:precommande` · `statut:rupture` ; `ext:<slug-extension>` ; `reservation-garantie` (fiche de réservation dont les réservations sont ouvertes) ; `nouveaute` (posé à la mise en vente, retiré après {{N_JOURS_NOUVEAUTE}} jours par le workflow quotidien) ; `cadeau` (sélection éditoriale) ; `petit-produit` (petit produit prixé sans les frais par commande, seulement quand la règle petits produits est active : lu par la validation de panier du §7, point 8). Ils servent aux collections automatiques, aux notifications email et aux filtres si un métachamp n'y est pas utilisable.

**Règle d'autorité** : Shopify décide si un produit **peut être acheté** (inventaire ; BP §6 « ne pas maintenir deux autorités concurrentes du stock local »). Le thème affiche donc « Rupture » dès que `product.available` est faux, quel que soit le métachamp. Un produit achetable dont le statut public est absent ou incohérent s'affiche « Disponibilité à confirmer » avec `data-statut="inconnu"` : la recette le détecte et la fiche repasse en brouillon.

**Précommande** : une fiche (ou une variante) **distincte** de la version en stock local, dont le titre de variante contient « Précommande » ; inventaire Shopify = quota calculé par `stock.preorder_quota` (allocation ferme − précommandes engagées − réserve). Jamais de vente sur stock négatif (« continuer à vendre en rupture » désactivé sur **toutes** les variantes).

**Pré-drop (réservation garantie, décision du 6.10.2026, `docs/SPEC.md` §2.11)** : une **fiche jumelle** « Réservation garantie — <titre> » (type de produit « Réservation garantie », handle `<handle>-reservation-garantie`, SKU `<SKU>-RESA-<AAAAMMJJ>` de la date du drop, une seule variante, `DENY`) construite par le moteur (`publish.build_predrop_publication`, route `POST /predrop/{predrop_id}/publish`, workflow 01) : prix = **prix pré-drop figé** du moteur (prix drop × (1 + supplément), arrondi et revérifié, ≤ prix drop × 1,10 et ≤ référence marché) ; **inventaire = réservations encore ouvertes** du registre (diminuées des commandes Shopify pas encore relevées, jamais écrit en texte) ; statut public `precommande` (allocation ferme) tant que les réservations sont ouvertes, sinon `rupture` ; **retirée au drop** (brouillon), à la fermeture, sur paramètres non signés, gel, stop-loss non évaluable ou quarantaine. Pourquoi une fiche et pas une variante : `productSet` a une sémantique « ensemble » ; ajouter puis retirer une variante changerait les options de la fiche normale et pourrait recréer sa variante (et son article d'inventaire) le jour même où elle reçoit le stock. La **fiche normale** garde sa structure (même variante, même SKU) ; pendant le pré-drop elle porte seulement `boutique.date_drop`, `boutique.reservation_statut`, `boutique.fiche_liee`, `boutique.prix_drop` et `boutique.prix_reservation`. Revue pré-drop (PDL-01, PDL-02) : son **prix natif est figé au prix du drop** jusqu'au jour du drop inclus (planchers revérifiés ; sinon prix inchangé, revue humaine, et la fiche de réservation est retirée tant que la fiche normale écrite ne pratique pas le prix du drop) ; son **stock local est retenu jusqu'au drop** (une réception avant le drop ne rend rien vendable au prix du drop : statut `rupture`, inventaire 0) et, ensuite, les unités des réservations confirmées non expédiées restent hors vente (`POST /stock/receive` le dit : `sellable_at_drop_price`). L'encart ne s'affiche jamais sur une fiche normale en stock local. SKU de la fiche de réservation **figé à l'ouverture** (stable après un report de la date). Le supplément paie la **garantie** d'être servi en premier et expédié dès réception, **pas le produit** ; **aucun remboursement de la différence** si des unités restent au drop (textes de l'encart `da-reservation-garantie`, identiques à `predrop.GUARANTEE_TEXT_FR` et `predrop.NO_DIFFERENCE_REFUND_FR`). Jamais de compte à rebours, de « plus que N », de coût ni de marge.

## 3. Collections

### 3.1 Par format (automatiques, condition « Type de produit est égal à »)

| Collection | URL proposée | Types de produit inclus | Tri par défaut |
|---|---|---|---|
| Displays | `/collections/displays` | Display, Demi-display | Disponibilité, puis nouveautés |
| Coffrets Dresseur d'élite (ETB) | `/collections/etb` | Coffret Dresseur d'Élite (ETB) | idem |
| Bundles et tripacks | `/collections/bundles-tripacks` | Bundle, Tripack | idem |
| Coffrets | `/collections/coffrets` | Coffret, Pokébox / tin | idem |
| Boosters | `/collections/boosters` | Booster | idem |
| Accessoires | `/collections/accessoires` | Protège-cartes, Classeur, Boîte de rangement (deck box), Tapis de jeu, Accessoire | idem |

### 3.2 Par disponibilité et usage (automatiques par tag ou prix)

| Collection | Condition | Remarque |
|---|---|---|
| Disponible maintenant | tag `statut:stock-local` | Section d'accueil « produits réellement disponibles » |
| Précommandes | tag `statut:precommande` | Lien vers la page Précommandes en tête de collection ; contient aussi les fiches de réservation ouvertes |
| Réservations garanties | tag `reservation-garantie` | Pré-drops ouverts (fiches « Réservation garantie ») ; masquée si vide ; encart de garantie en tête |
| Nouveautés | tag `nouveaute` | Le tag n'est posé que sur un produit achetable (DA : « Nouveauté ne sert pas d'appât ») |
| Idées cadeaux — moins de 30 CHF | prix < 30 **et** tag `cadeau` | Bornes = tranches de budget de la landing (préférences déclarées), à ajuster selon l'assortiment réel |
| Idées cadeaux — 30 à 60 CHF | 30 ≤ prix < 60 **et** tag `cadeau` | idem |
| Idées cadeaux — 60 à 120 CHF | 60 ≤ prix < 120 **et** tag `cadeau` | idem |
| Idées cadeaux — plus de 120 CHF | prix ≥ 120 **et** tag `cadeau` | idem |

### 3.3 Par extension (automatiques, tag `ext:<slug>`)

Une collection par extension **effectivement proposée** (stock local, précommande ouverte ou alerte de réassort) ; elle sert aussi de page d'extension SEO (`docs/06-contenu/SEO.md` §2). URL : `/collections/<slug-extension>` (ex. `/collections/mega-evolution-nuit-noire`, à construire à partir du nom exact). Page d'index : `/pages/extensions` (liste des collections d'extension, de la plus récente à la plus ancienne).

## 4. Recherche et filtres (application Search & Discovery de Shopify)

| Filtre | Source | Valeurs affichées | Remarque |
|---|---|---|---|
| Disponibilité | métachamp `boutique.statut_stock` (repli : tags `statut:*`) | Stock local · Précommande · Rupture | **Ne pas** utiliser le filtre natif « en stock » : il compte un quota de précommande comme du stock |
| Format | type de produit | Libellés du §3.1 | — |
| Extension | métachamp `boutique.extension` | Noms exacts | Ordre : la plus récente d'abord |
| Budget | prix (filtre natif) | Curseur en CHF | Prix TTC affichés (mention TVA selon statut, registre `MENTION_TVA`) |
| Langue (FR) | métachamp `boutique.langue` | FR | Masqué tant qu'une seule langue est vendue ; rendu visible dès l'arrivée d'une 2e langue |

Recherche : synonymes à déclarer dans Search & Discovery (« ETB » = « coffret dresseur d'élite », « display » = « boîte de boosters », « tripack » = « pack de 3 boosters », « sleeves » = « protège-cartes », « classeur » = « portfolio »), alignés sur la table d'alias du catalogue.

Disponibilité des types de métachamps comme filtre et comme condition de collection : à vérifier dans l'admin au moment de la création (documentation Shopify non consultable depuis l'environnement de build le 4.10.2026). Les tags miroirs du §2 sont le repli prévu.

## 5. Pages

| Page | URL | Contenu (source) | Statut |
|---|---|---|---|
| Précommandes | `/pages/precommandes` | Bloc public de `docs/04-legal/PRECOMMANDES.md` | Brouillon juriste |
| Livraison et retours | `/pages/livraison-retours` | `docs/04-legal/LIVRAISON_RETOURS.md` | Brouillon juriste |
| FAQ | `/pages/faq` | `docs/07-ops/FAQ_CLIENTS.md` | Brouillon juriste |
| Contact | `/pages/contact` | Email `{{EMAIL_SUPPORT}}` affiché en clair (un formulaire seul ne suffit pas, `docs/04-legal/README.md` L2) + formulaire de contact Shopify | À créer |
| À propos | `/pages/a-propos` | Qui, où (Genève), comment (3 statuts, contrôles à réception), mention d'indépendance complète (`da-mention-independance`, version `complete`) | À rédiger (agent 08) |
| Extensions | `/pages/extensions` | Index des collections d'extension | À créer |
| Guides | `/blogs/guides` | Articles SEO des sujets de `docs/06-contenu/15_SUJETS.md` | À rédiger (agent 08) |
| CGV | Page de politique « Conditions d'utilisation » ou `/pages/cgv` | `docs/04-legal/CGV.md` | Brouillon juriste |
| Confidentialité | `/policies/privacy-policy` | `docs/04-legal/CONFIDENTIALITE.md` | Brouillon juriste |
| Cookies | `/pages/cookies` | `docs/04-legal/COOKIES.md` (relevé réel des cookies) | Brouillon juriste |
| Mentions légales | `/pages/mentions-legales` | `docs/04-legal/MENTIONS_LEGALES.md` | Brouillon juriste |

Chaque URL réellement créée est reportée dans le registre légal (`URL_CGV`, `URL_RETOURS`, `URL_PRECOMMANDES`, `URL_CONFIDENTIALITE`, `URL_COOKIES`, `URL_FAQ`) par l'agent 07.

## 6. Navigation et accueil

**Menu principal** : Disponible maintenant · Précommandes · Displays · ETB · Bundles et tripacks · Coffrets · Accessoires · Extensions · Guides.
**Pied de page** : Livraison et retours · Précommandes · FAQ · Contact · À propos · CGV · Confidentialité · Cookies · Mentions légales · Paramètres des cookies ; mention courte d'indépendance (`da-mention-independance`) ; exploitant et email.
**Bandeau d'annonce** (`da-annonce`) : « Expédition depuis Genève · Livraison en Suisse uniquement · Prix en CHF ». Jamais de compte à rebours ni de « dernières pièces ».

| Ordre | Section d'accueil | Règle d'affichage |
|---|---|---|
| 1 | Bannière (`da-banner`) : promesse BP §1 + bouton « Disponible maintenant » | Toujours |
| 2 | Disponible maintenant (collection §3.2) | Masquée si vide |
| 3 | Nouveautés | Masquée si vide ; produits achetables uniquement |
| 4 | Précommandes ouvertes | Masquée si vide ; lien vers la page Précommandes |
| 4 bis | Réservations garanties (collection §3.2, pré-drops ouverts) | Masquée si vide ; statut et date du drop seulement, jamais de compte à rebours |
| 5 | Idées cadeaux par budget (4 tuiles vers les collections §3.2) | Une tuile vide est masquée |
| 6 | Trois statuts, pas de flou (reprise de la landing) | Toujours |
| 7 | Guides (3 derniers articles) | Dès le premier article |
| 8 | Alertes (`da-formulaire-alertes`, contexte `ouverture`) | Toujours |

## 7. Installation du thème et des snippets

Thème proposé : thème gratuit « Online Store 2.0 » de Shopify (ex. Dawn), à confirmer à la création (B15) ; pas d'application payante au lancement.

1. Ressources du thème : ajouter `tokens.css` et `components.css` (copies synchronisées de `docs/05-da/`, voir `site/outils/da_sync.py`) et les charger dans `layout/theme.liquid` ; fixer `data-da="a"` (ou `"b"`) sur `<html>`.
2. Copier `site/shopify/snippets/*.liquid` dans `snippets/` du thème.
3. Ajouter ces réglages au thème (`config/settings_schema.json`) : `delai_expedition_local` (texte, valeur = `DELAI_EXPEDITION` validé), `url_page_precommandes` (URL), `url_confidentialite` (URL).
4. Fiche produit (`sections/main-product.liquid`) : `{% render 'da-badges', product: product %}` sous le titre ; `{% render 'da-statut-stock', product: product %}` sous le prix ; `{% render 'da-delai-sortie', product: product %}` avant le bouton d'ajout ; si `boutique.alerte_reassort` est vrai et le produit indisponible : `{% render 'da-formulaire-alertes', contexte: 'reassort', product: product %}` à la place du bouton.
5. Carte produit (`snippets/card-product.liquid`) : `{% render 'da-badges', product: card_product %}` et `{% render 'da-statut-stock', product: card_product, contexte: 'carte' %}`.
6. Pied de page : `{% render 'da-mention-independance' %}` ; page À propos et mentions légales : `{% render 'da-mention-independance', version: 'complete' %}`.
7. Quantité maximale : appliquer `boutique.quantite_max` au sélecteur de quantité (`max`) **et** la contrôler côté serveur (règle de commande ou validation du panier, à choisir à la recette) : l'attribut HTML seul ne suffit pas. La limite des CGV (ch. 4.4) est **par référence et par foyer, toutes commandes confondues** : le thème ne voit qu'une commande à la fois, le contrôle entre commandes successives relève de la SOP SAV (SAV-18). Tout texte affiché dit « par foyer », jamais « par commande » (contrôlé par `site/outils/verifier_site.py`).

8. Petits produits (BP §5 « plancher dur 8 CHF par commande ; règles adaptées aux petits produits ») : tant que `small_product_min_order_ttc` et `small_product_max_shipping_ttc` sont nuls dans `config/pricing_rules.v1.yaml` (valeur livrée), la règle est **inactive** : chaque petit produit est prixé avec les frais par commande et respecte seul le plancher (un booster coûtant 3,79 CHF est affiché 23,90 CHF), aucune validation de panier n'est requise. Pour l'activer : mettre en place une **validation de panier côté serveur** (fonction de validation du panier et du paiement Shopify, ou application équivalente) qui refuse tout panier composé **uniquement** de produits étiquetés `petit-produit` dont le sous-total (après remises) est inférieur au minimum, la recetter (§8), puis renseigner ce minimum et le port maximal facturé dans le fichier de règles et le signer de nouveau. Le moteur n'active la règle que si ce minimum couvre son minimum calculé (`pricing.small_product_min_order_required` : 127,00 CHF en assujetti avec port offert, davantage si un port est facturé) ; sinon les frais par commande restent inclus (fermé par défaut).

9. Pré-drop (fiche de réservation **et** fiche normale) : `{% render 'da-reservation-garantie', product: product %}` sous le prix (n'affiche rien hors pré-drop) ; bouton d'ajout au panier conditionné par `{% capture acces_reservation %}{% render 'da-reservation-acces', product: product, customer: customer %}{% endcapture %}` — si `acces_reservation` ≠ `oui` (réservations fermées, ou fenêtre prioritaire et client non connecté ou non inscrit aux alertes de la fiche normale), pas de bouton : l'encart et, sur la fiche normale, `da-formulaire-alertes` (contexte `reassort`) le remplacent. Fenêtre prioritaire : comptes clients **sans mot de passe** (nouveaux comptes clients Shopify) pour que les inscrits se connectent avec l'adresse de leur inscription ; le workflow 02 atteste le même critère à chaque paiement (étiquette `alerte-produit:<handle>` et consentement confirmé).

Les snippets n'affichent **aucun prix en dur** : le prix vient du champ natif, alimenté par le moteur (`pricing.decide_price`, statut `OK` ou `REVIEW` validé) ; l'encart de réservation lit les **prix figés du moteur** (`boutique.prix_reservation`, `boutique.prix_drop`, texte décimal affiché « CHF 229.90 » sans dépendre du format monétaire de la boutique), égaux aux prix natifs vérifiés des deux fiches ; sans ces métachamps, aucun prix n'est affiché. Format monétaire de la boutique (réglages, « Format des devises ») : `CHF {{amount}}` avec la devise visible partout (OIP), à fixer à la création (B15) et à vérifier à la recette.

10. Pré-drop, thème Dawn (revue pré-drop PDL-13) : sur le modèle de la fiche de réservation (type « Réservation garantie »), **désactiver le bloc « État de l'inventaire »** (« Stock faible : N restants ») et vérifier les messages du panier (« vous ne pouvez ajouter que N ») : l'inventaire de la fiche de réservation est le nombre de réservations encore ouvertes, il ne doit jamais apparaître (aucun « plus que N », PRECOMMANDES et CGV ch. 7.12). Exclure le type de produit « Réservation garantie » de **toutes les remises** (codes et remises automatiques : un montant différent du prix pré-drop rend la réservation non servie et remboursée) ; contrôle serveur de la quantité maximale (point 7) en place **avant le premier pré-drop**.

## 8. Recette de la structure (agent 12, avant l'ouverture)

- [ ] Chaque collection du §3 existe, se remplit seule et n'affiche aucun produit en brouillon.
- [ ] Un produit en rupture n'apparaît ni dans « Disponible maintenant » ni dans « Nouveautés ».
- [ ] Un produit FICTIF de test passe par les 3 statuts (stock local → précommande impossible sur la même variante → rupture) et les badges suivent.
- [ ] Aucun produit publié n'affiche `data-statut="inconnu"` (recherche dans le code source de chaque page de collection).
- [ ] Le filtre « Disponibilité » sépare stock local et précommande ; le filtre « Budget » fonctionne en CHF.
- [ ] La quantité maximale est refusée au-delà de la limite, y compris par un panier modifié à la main.
- [ ] Un produit sans stock réel au registre du moteur n'est jamais publié avec `statut:stock-local`, et une fiche de précommande sans allocation ferme reste `statut:rupture`.
- [ ] Pré-drop FICTIF : la fiche « Réservation garantie » apparaît (prix pré-drop, badge « Réservation garantie », « Drop le JJ.MM (date estimée) », encart de garantie avec les deux prix figés « CHF … ») ; pendant la fenêtre prioritaire, pas de bouton pour un visiteur non connecté ; quota épuisé : « Réservations fermées » sans nombre d'unités ; une réception avant le drop ne rend pas la fiche normale achetable (stock retenu) ; au drop, la fiche de réservation repasse en brouillon et la fiche normale devient achetable **au prix affiché « Au drop »**, sans les unités réservées non expédiées ; aucune heure, aucun compte à rebours, aucun « plus que N » (bloc « État de l'inventaire » désactivé, messages du panier vérifiés, §7 point 10).
- [ ] Format monétaire de la boutique `CHF {{amount}}` vérifié sur les fiches, le panier et les emails ; aucune remise applicable au type « Réservation garantie ».
- [ ] Si la règle petits produits est activée (§7, point 8) : une commande d'un seul produit `petit-produit` sous le minimum est refusée au paiement, y compris par un panier modifié à la main ; un panier mixte (petit produit + produit principal) passe.
- [ ] Le code source public ne contient aucun terme interne (coût, marge, fournisseur, B2B) ni métachamp autre que `boutique.*` (lecture de la page et de `/products/<handle>.json`).
- [ ] Parcours BP §7 complet sur mobile et ordinateur (`docs/07-ops/RECETTE_AVANT_OUVERTURE.md`).

## Validation humaine requise

- [ ] **B15** : créer la boutique Shopify (compte, offre) et confirmer le thème gratuit retenu.
- [ ] Valider la liste des collections, des filtres et du menu (§3 à §6).
- [ ] Valider les tranches « Idées cadeaux » (proposées : < 30, 30-60, 60-120, ≥ 120 CHF) ou les ajuster à l'assortiment réel.
- [ ] Fixer `N_JOURS_NOUVEAUTE` (durée du badge « Nouveauté », proposée : 30 jours, **hypothèse**).
- [ ] Choisir le mécanisme serveur de la quantité maximale (§7, point 7).
- [ ] Décider d'activer ou non la règle petits produits (§7, point 8) : validation de panier recettée, puis minimum de commande et port maximal renseignés dans les règles signées.
- [ ] Agent integrations : confirmer que `publish.py` écrit exactement les métachamps et tags du §2, et rien d'autre.
- [ ] Pré-drop : valider la fiche jumelle « Réservation garantie » (plutôt qu'une variante), la collection « Réservations garanties », les textes de l'encart et l'accès prioritaire par comptes clients sans mot de passe (§7, point 9) ; vérifier sur la version de Shopify en service le comportement de `productSet` et de `all_products`.
- [ ] Pré-drop (revue PDL-13) : bloc « État de l'inventaire » désactivé sur la fiche de réservation, messages du panier vérifiés, format monétaire `CHF {{amount}}`, type « Réservation garantie » exclu des remises (§7, point 10).
