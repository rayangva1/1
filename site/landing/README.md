# Landing de validation — présentation et inscription aux alertes

> Propriétaire (build) : agent « site-contenu ». Exploitation : agent 07 Site (BL-031), suivi KPI agent 10 (BL-034), contrôle agent 12.
> Sources : BP §1 (« Tester une page de présentation avec inscription aux alertes. Aucun faux stock et aucune précommande encaissée sans allocation »), §7, §8, §9 (J1-15) ; protocole `docs/01-marche/PROTOCOLE_LANDING_TEST.md` ; DA `docs/05-da/`.
> Nom de travail **« Quai des Cartes » — provisoire, non validé** (décision C06). Statut : **aperçu prêt ; publication bloquée** tant que les champs ne sont pas validés (voir §6). Les visuels sont déjà servis **en local** (§3.0).
> **Ambiance « Atelier »** (direction A, toujours claire, `docs/05-da/DIRECTION_ATELIER.md`), retenue par le propriétaire le 06.10.2026 et appliquée le 10.10.2026 : papier crème, charbon mat, un seul **fil orange**. La page est un récit en chapitres porté par un renard original, **Braise (nom provisoire)**, avec trois photos d'ambiance du propriétaire. L'ambiance « Nuit sur le Léman » et l'ancienne mascotte sont abandonnées (archives de la DA seulement, refusées par les outils du site).

### 0. Le récit (ordre des chapitres)

| Chapitre | Visuel | Contenu |
|---|---|---|
| Héro | `renard-heros` (ordinateur dès 1280 px : l'illustration occupe l'écran, titre, introduction et bouton posés dans sa moitié libre sur un voile papier 64 %, bouton au-dessus du pli dès 1280 × 720) · `renard-heros-portrait` (mobile : titre posé dans le haut libre du portrait, accroche avant la ligne de référencement) | Titre `h1` : « Pokémon JCC en français, expédié depuis Genève » + accroche **« Le calme avant le drop. »** (proposition à valider) ; alerte d'ouverture ; six engagements |
| 01 Rencontre | `renard-assis` (cadre fondu dans le papier) | Braise (nom provisoire), sa fiche (caractère, rôle, ce qu'il ne fait jamais), création originale sans lien avec Pokémon |
| 02 Le jour du drop (charbon) | `renard-jour-de-drop` | Une date, un statut, rien d'autre ; la réservation s'ouvre d'abord pour les inscrits aux alertes du produit |
| 03 Réservation garantie | `renard-reservation` | Les deux phrases du moteur mot pour mot (la garantie dite comme une citation, filet orange au-dessus), trois garanties, badges monochromes, renvoi aux questions |
| 04 Formats | — (aucune image : aucun objet photographié ou dessiné à côté de la ligne « Accessoires ») | Formats prévus, aucun prix, « Tout le catalogue en français » ; ce que vous ne verrez pas chez nous |
| 05 Le soin | `renard-classeur` · `photo-boite-etuis` (sa bande orange prolonge le fil) · `photo-mains-sleeve` (photos d'ambiance, légende neutre) | Stock réel, français vérifié, service qui répond |
| 06 Au bord du Léman | `renard-leman` (scène pleine, titre posé dans le ciel ; le fil ressort de la corde) | Expédié depuis Genève, livré en Suisse |
| 07 Alertes | `renard-alertes` (pleine largeur dès 1100 px : le renard lève les yeux vers le titre et le formulaire, posé comme une feuille sur le mur libre) | Formulaire d'inscription (consentement non pré-coché, lien confidentialité, désactivé sans webhook ; champs facultatifs repliés sous « Préciser mes alertes ») |
| 08 Questions | `photo-classeur` (ordinateur seulement, légende neutre) | Questions fréquentes, dont les mentions de disponibilité et « Qui est Braise ? » |
| Pied de page | `renard-pied-de-page` (décoratif) | Braise s'endort contre une boîte ; le fil orange se pose sous lui ; mention d'indépendance |

**Le fil orange** (DIRECTION_ATELIER.md §6) : une ligne SVG qui traverse les illustrations. Elle sort du filet photographié du héro, descend sous le contenu dans un couloir libre, glisse en S jusqu'à la marge et entre dans le filet de chaque figure `[data-fil-ancre]` ; le raccord est effilé, de l'épaisseur et de la teinte mesurées du filet photographié (`fil`, `fil_epaisseur`, `fil_couleurs` de `site/config/visuels.json`, écrits dans `data-fil`, `data-fil-ep` et `data-fil-couleurs` par `site/outils/visuels.py`) jusqu'au trait de 2 px. Elle passe sous les illustrations pleine largeur, ressort de la corde du Léman (`data-fil-ancre="corde"`), se branche sur le tiret de chaque numéro de chapitre posé contre la marge (`data-fil-chapitre`, le tiret se dessine quand le fil l'atteint) et sur les filets des photos (`data-fil-ancre="branche"`), puis se pose sous le renard du pied de page. Sous 700 px : chaque filet se prolonge et s'effile, pas de fil dans la marge. Dessiné au défilement ; entier et immobile en mouvement réduit ou en pause ; sans JavaScript, une ligne CSS court dans la marge. Décor `aria-hidden` : il ne porte aucune information et ne passe jamais sur un texte (contrôlé par `site/tests/e2e/atelier.mjs`).

## 1. Ce que la page fait, et ce qu'elle ne fait jamais

| Fait | Ne fait jamais |
|---|---|
| Présente la promesse du BP §1 : Pokémon JCC en français, expédié depuis la Suisse, disponibilité lisible, produits correctement identifiés, service fiable | Afficher un stock, un compteur, « dernières pièces », un minuteur |
| Explique le jour du drop et la **réservation garantie** de la future boutique (badges DA « Réservation garantie » et « Drop le JJ.MM », les deux phrases exactes du moteur : le supplément paie la garantie, pas le produit ; aucun remboursement de la différence) | Ouvrir une réservation, afficher un prix de drop ou de réservation, un supplément en francs |
| Explique les 3 statuts (Stock local, Précommande sur quantité confirmée, Rupture) dans les questions fréquentes | Afficher un prix, même indicatif (les tranches de budget du formulaire sont des préférences déclarées, pas des prix) |
| Liste les formats prévus, sans engagement de sélection | Prendre une précommande, un acompte ou une réservation |
| Recueille l'inscription aux alertes : email, prénom facultatif, formats, budget, pour qui, canton, **consentement non pré-coché** | Envoyer un email sans confirmation (double opt-in fait par n8n) |
| Affiche la mention d'indépendance (non-affiliation à The Pokémon Company), l'exploitant et le lien confidentialité | Utiliser un logo, un personnage ou une police de la licence ; contenir un coût, une marge ou un nom de fournisseur |
| Ambiance « Atelier », toujours claire (contrastes AA calculés, `DIRECTION_ATELIER.md`), éditoriale, mobile d'abord, accessible (libellés, erreurs annoncées, focus charbon visible, cibles de 44 px, textes alternatifs) ; fil orange et apparitions coupés par `prefers-reduced-motion` et par le bouton « Pause des animations » (WCAG 2.2.2) ; rien n'est masqué sans JavaScript | Charger un script tiers, un pixel publicitaire ou un cookie (ressources externes : Google Fonts, retirable ; en **aperçu seulement**, les visuels de la marque à leur adresse distante — jamais dans le dossier publié) |

## 2. Fichiers

| Fichier | Rôle | Modifié par |
|---|---|---|
| `index.html` | Page principale (source, champs `{{…}}` visibles) | À la main (agent 07) |
| `merci.html`, `inscription-confirmee.html`, `desinscription.html` | Pages de retour du workflow n8n (sans JavaScript, après confirmation, après désinscription) | **Générées** : `python site/outils/publication.py source` |
| `confidentialite.html` | Notice de confidentialité **de la landing** = bloc public de `docs/04-legal/CONFIDENTIALITE_LANDING.md` converti en HTML (chaque champ du formulaire y est déclaré : contrôlé par `verifier_site.py`) ; la déclaration complète de la boutique (`CONFIDENTIALITE.md`) la remplace à l'ouverture | **Générée** (même commande) ; le texte se corrige dans `docs/04-legal/` |
| `css/landing.css` | Mise en page de la landing, des pages secondaires **et des maquettes** (`site/maquettes/`) : grille 4/8/12 colonnes, chapitres (un seul papier, chapitre charbon), héro (titre, introduction et bouton posés sur un voile papier de 64 % : AA même si l'image devenait noire), fil orange (SVG et repli CSS sans script), cadres d'images avec silhouette du renard en secours, formulaire en « feuille de papier », questions, pied de page ; uniquement des variables `--da-*` ; tout mouvement seulement sous `prefers-reduced-motion: no-preference`, coupé par la pause | À la main |
| `js/theme.js` | Avant affichage : classe `lp-js` (les apparitions ne masquent rien sans script) et choix « Pause des animations » mémorisé | À la main |
| `js/landing.js` | Formulaire (validation, envoi, messages) ; fonctions pures dans `LandingCore` | À la main |
| `js/atelier.js` | Effets : **fil orange** (projection des filets mesurés `data-fil` dans la page, cadrage `object-fit` compris ; raccords effilés `data-fil-ep`/`data-fil-couleurs` ; couloirs libres et S jusqu'à la marge ; passage sous les illustrations pleine largeur ; branches vers les numéros et les photos ; dessin au défilement), image indisponible masquée (la silhouette du renard reste), apparitions au défilement, en-tête au défilement, question fréquente ouverte par un lien, boutons « Pause des animations » (en-tête et pied de page). Aucun appel réseau | À la main |
| `assets/visuels/` | Variantes WebP des 13 visuels de la marque (`<clé>-<largeur>.webp`, sans métadonnées) ; les fichiers d'origine restent archivés dans `site/visuels-sources/` (hors du dossier publié, ignoré par git) | **Générées** : `python site/outils/rapatrier_visuels.py` |
| `../config/visuels.json` | **Source unique** des 13 visuels (clé, dimensions, format, nature, usage, description, texte alternatif, filet orange mesuré, largeurs des variantes) ; les pages n'ont que des balises `data-visuel` | `rapatrier_visuels.py --importer` (remplit `variantes`, `fichier_source`, `empreinte_source`, source « local »), à la main pour ajouter un visuel |
| `js/config.js` | `webhookUrl` (vide = formulaire désactivé avec message), `mode`, `emailSupport` | `publication.py` (ou à la main, §3.4) |
| `assets/da/` | Copies des fichiers DA (tokens, composants, `ambiance.css` = `tokens-atelier.css`, logos et favicon de l'Atelier) + `manifeste.json` (direction **a**, ambiance **atelier**) | **Générées** : `python site/outils/da_sync.py` |
| `assets/og-image.png` | Image de partage 1200 × 630 (Atelier : `renard-heros` local et titre sur voile papier ; aucune image distante) | `python site/outils/generer_og.py` (outil local facultatif) |
| `inscription.schema.json` | Contrat des champs envoyés au webhook n8n | À la main, avec l'agent integrations |
| `../config/publication_landing.yaml` | `URL_LANDING`, `MOIS_OUVERTURE`, `WEBHOOK_INSCRIPTION` (mêmes statuts que le registre légal) | Agent 07, propriétaire |

Les champs d'identité (`NOM_BOUTIQUE`, `RAISON_SOCIALE`, `ADRESSE_POSTALE`, `EMAIL_SUPPORT`…) viennent **uniquement** du registre légal `docs/04-legal/champs_a_remplir.yaml` : une valeur, un endroit.

## 3. Déployer sans écrire de code

### 3.0 Visuels de la marque : import local (aucun réseau)

Les 13 visuels (10 illustrations du renard « Braise », nom provisoire, et 3 photos d'ambiance du propriétaire) sont déclarés dans **un seul fichier**, `site/config/visuels.json` : clé, fichier source, nature (`illustration` ou `photo`), format (« 21:9 »…), dimensions, usage, description, **texte alternatif** (écrit dans les pages par `visuels.py`), filet orange mesuré (`fil`), largeurs des variantes. Ils sont servis **en local** : la page publiée ne charge aucune image d'un tiers (CSP `img-src 'self'`).

```bash
python site/outils/rapatrier_visuels.py --importer <dossier>                 # importe les 13 fichiers (JPEG, PNG ou WebP)
python site/outils/rapatrier_visuels.py --importer <dossier> --seulement renard-heros   # remplace un seul visuel
python site/outils/rapatrier_visuels.py --verifier   # format, dimensions, poids, absence de métadonnées, archive
python site/outils/visuels.py verifier               # pages synchronisées avec le manifeste
```

Chaque fichier est cherché sous son `fichier_source` (sinon `<clé>.jpg|.png|.webp`). Contrôles **avant toute écriture** : format réel lu dans l'en-tête, poids maximal, proportions conformes au `format` déclaré (orientation EXIF comprise), largeur suffisante pour la plus grande variante, pages sans visuel inconnu. Puis : orientation appliquée, conversion en sRGB si besoin, variantes WebP (qualité 82, abaissée par paliers jusqu'à 52 pour tenir le budget : 250 Ko jusqu'à 1600 px, 450 Ko au-delà) **sans aucune métadonnée** (ni EXIF, ni GPS), source archivée telle quelle dans `site/visuels-sources/` (ignoré par git), manifeste rempli (`variantes`, `fichier_source`, `empreinte_source` SHA-256), source « local », pages réécrites. **Fermé par défaut** : si un seul fichier manque ou est refusé, rien n'est écrit.

Règles de rédaction contrôlées par `visuels.py` (`docs/05-da/DIRECTION_ATELIER.md` §7–§8) : aucun nom de la licence ; une photo d'ambiance ne se présente jamais comme un produit en vente (« Photo d'ambiance : … ») ; une illustration du renard ne décrit ni plusieurs queues, ni une posture debout, ni vêtements ; toute boîte, carte ou étui décrit est « vierge » ou « sans marque ».

Ajouter ou remplacer un visuel : le déclarer dans `visuels.json`, écrire la balise `<img data-visuel="…" sizes="…" loading="lazy" decoding="async">` dans la page (le texte alternatif vient du manifeste ; `data-alt-contexte` pour garder un texte propre à la page), puis `--importer`. Le mode historique de rapatriement depuis une adresse distante (`base_distante`) reste disponible mais le manifeste n'en a plus : `publication.py` refuse toujours un visuel distant.

### 3.1 Préparer le dossier (agent 07, 1 commande)

```bash
cd /home/user/1
python site/outils/publication.py etat          # ce qui manque encore, et qui doit le fournir
python site/outils/publication.py apercu        # dossier d'aperçu : site/dist/apercu/ (page non indexée)
python site/outils/publication.py publication   # dossier final : site/dist/landing/ — REFUSE tant que tout n'est pas validé ou qu'un visuel n'est pas local
```

**Publication à J10 (BL-032).** La liste des champs exigés est **fermée** (`CHAMPS_LANDING` dans `publication.py`, affichée par `etat` avec la nature de chaque champ) : identité (B07), emails (B02), webhook et emailing (B04), hébergeur de la page et polices (B08, choix des polices), n8n, messagerie et IA, durées de conservation, plus trois champs **provisoires autorisés** — `URL_LANDING` (adresse de l'hébergeur avant le domaine), `MOIS_OUVERTURE` (mois visé), `DATE_VERSION_LANDING` (version de la notice, remplacée à l'ouverture). Provisoire ne veut pas dire « à valider » : chaque champ doit avoir le statut `valide` ; on republie quand la valeur change. Aucun champ ne dépend de la boutique Shopify, du paiement, du transporteur ni de la relecture complète des textes (J28). Une page qui utiliserait un autre champ fait échouer la publication tant que la liste n'a pas été revue. `ST_POLICES` doit dire « Google » si la page charge Google Fonts, et ne pas le dire avec `--sans-google-fonts` : sinon, refus.

Le dossier `publication` contient en plus : `js/config.js` rempli (URL du webhook), `_headers` (politique de sécurité Netlify : seul le webhook est joignable), `robots.txt`, `sitemap.xml`. Le bandeau d'aperçu et la balise `noindex` sont retirés ; le nom validé remplace le nom de travail ; le formulaire fonctionne aussi sans JavaScript (envoi direct au webhook). Option `--sans-google-fonts` : retire Google Fonts (polices système de secours), si la propriétaire préfère ne transmettre aucune adresse IP à Google (nLPD, voir README DA §3).

### 3.2 Option A — Netlify Drop (recommandée : 5 minutes, sans compte au départ)

1. Ouvrir `https://app.netlify.com/drop`.
2. Glisser le dossier **`site/dist/landing/`** (jamais `site/landing/`, qui contient la source et les champs `{{…}}`).
3. Netlify publie aussitôt sur une adresse `*.netlify.app`. Le site reste anonyme et temporaire tant qu'il n'est pas **réclamé** avec un compte (acte de la propriétaire, B04/B08).
4. Pour une mise à jour : page « Deploys » du site → glisser le nouveau dossier.
5. Domaine : après l'achat du domaine (B08), le relier au site dans les réglages de domaine Netlify, puis mettre à jour `URL_LANDING` et relancer `publication`.

Sources : documentation Netlify « Netlify Drop Quickstart » et « Create deploys » (https://docs.netlify.com/start/quickstarts/netlify-drop-quickstart/ ; https://docs.netlify.com/deploy/create-deploys/), consultées via index de recherche le 4.10.2026 : dépôt par glisser-déposer, site anonyme jusqu'à réclamation, mise à jour par la page Deploys. Le fichier `_headers` est le format d'en-têtes de Netlify ; il est ignoré par les autres hébergeurs.

### 3.3 Option B — Page Shopify (quand la boutique existe, B15)

1. Admin Shopify → Boutique en ligne → Thèmes → Personnaliser → créer un modèle de page « landing ».
2. Ajouter une section « Liquid personnalisé » et y coller le contenu de `<main>` de `site/dist/landing/index.html`.
3. Téléverser `landing.css` et les fichiers `assets/da/` dans les ressources du thème (ou les Fichiers), et adapter leurs chemins.
4. **Remplacer le formulaire** par le snippet `site/shopify/snippets/da-formulaire-alertes.liquid` (formulaire client natif de Shopify, tags `alerte-ouverture` et préférences) et activer la confirmation d'inscription (double opt-in) dans les réglages de notifications marketing de Shopify. Le webhook n8n n'est alors plus appelé par la page : le workflow lit les clients Shopify.
5. Recette : inscription test, email de confirmation reçu, désinscription testée (R-H05).

À vérifier au moment de le faire : libellés exacts de l'admin Shopify et réglage du double opt-in (documentation Shopify non consultable depuis l'environnement de build le 4.10.2026 ; source secondaire indexée : https://www.shopify.com/blog/double-opt-in).

### 3.4 Option C — Carrd (ou outil équivalent)

1. Un élément « Embed » (code HTML) accueille le contenu de `<main>` et la feuille `landing.css` + `assets/da/*.css` en ligne. Selon la documentation Carrd indexée le 4.10.2026, l'élément Embed demande une offre **Pro Standard** ou supérieure (https://carrd.com/docs/building/embedding-custom-code).
2. Le formulaire peut rester celui de la page (appel direct du webhook) ou devenir un **formulaire Carrd « Custom » envoyé vers n8n** (offre **Pro Plus** selon https://carrd.co/docs/forms/setting-up-a-custom-n8n-form). Dans ce cas, reproduire **exactement** les champs, le texte de consentement non pré-coché et le lien de confidentialité.
3. Offres et prix Carrd à vérifier le jour de l'achat (compte = acte de la propriétaire, dépense dans le mandat SITE_TOOLS).

### 3.5 Sans outil (dépannage)

Si `publication.py` ne peut pas être lancé : dans une copie du dossier, remplacer à la main chaque `{{CHAMP}}` par sa valeur **validée**, coller l'URL du webhook entre les guillemets de `webhookUrl` dans `js/config.js`, passer `mode` à `"publication"`, supprimer les blocs `<!-- APERCU:DEBUT -->…<!-- APERCU:FIN -->`. Puis faire contrôler par l'agent 12 (`python site/outils/verifier_site.py --dossier <copie>`).

## 4. Contrat avec le workflow n8n « inscription alertes »

Le workflow appartient à l'agent integrations (`orchestration/n8n/`). La landing n'attend que ceci :

| Étape | Exigence |
|---|---|
| Réception | Nœud Webhook `POST`, corps `application/x-www-form-urlencoded`, champs de `inscription.schema.json`. Option « Allowed Origins (CORS) » = origine exacte de `URL_LANDING` (pas `*`). La page envoie une requête « simple » (aucune pré-vérification CORS) |
| Réponse | Requête avec `Accept: application/json` (JavaScript) : `200` + `{"ok": true}`. Sans JavaScript : redirection `303` vers `URL_LANDING + "merci.html"` |
| Contrôles | Revalider chaque champ ; `consentement` = `oui` sinon rejet ; `site_web` non vide = robot (répondre `200`, ne rien faire) ; limiter les appels par adresse IP et par email (ex. 5 par heure, **hypothèse**) ; ignorer une adresse déjà confirmée (pas de second email) |
| Enregistrement | Statut `en_attente`, horodatage **serveur**, texte et version du consentement, préférences, source UTM ; jeton de confirmation aléatoire à usage unique (expiration proposée : 7 jours, **hypothèse**) |
| Double opt-in | Envoyer **uniquement** l'email `docs/06-contenu/EMAILS/` n° 01 (confirmation). Lien `GET …/alertes-confirmer?jeton=…` → statut `confirme`, email n° 02 (bienvenue et préférences), redirection vers `inscription-confirmee.html` |
| Désinscription | Lien `GET …/alertes-desinscrire?jeton=…` dans chaque email → propagation à **tous** les outils (emailing, Shopify, base), liste d'exclusion, redirection vers `desinscription.html` (BP §9, BL-103) |
| Données | Jamais de copie dans un tableur partagé ; pas d'envoi à un prompt d'IA ; conservation selon `DUREE_CONSERVATION_ALERTES` (registre légal) ; réponses facultatives et UTM exploitées **seulement en agrégé** ; l'adresse IP sert uniquement à limiter les appels et n'est **jamais enregistrée avec l'inscription** (promesse de la notice `CONFIDENTIALITE_LANDING.md`, ch. 2) |
| Effacement de l'IP (promesse « effacées après le contrôle ») | Le workflow d'inscription ne conserve **aucune exécution** : réglages `saveDataSuccessExecution` = `none`, `saveDataErrorExecution` = `none`, `saveManualExecutions` = `false` (une exécution conservée garderait les en-têtes `x-forwarded-for` et le corps) ; compteur de limitation en mémoire ou sur une empreinte salée de l'IP, effacé au plus tard 1 heure après l'envoi ; un échec ouvre un incident dans l'API du moteur, qui tourne **en interne dès J8** (B27 : base et API en simulation derrière n8n, jamais exposées), par `POST /incidents` avec le credential de rôle `n8n-06-marketing` (jamais le jeton commun), **sans** IP ni email de l'inscrit ; le workflow 04 le notifie à la propriétaire (email de la boîte des agents B02 ; canal d'alerte C29 dès J26) ; si l'API ne répond pas, le workflow d'erreur 04 envoie seul l'alerte « moteur injoignable » par email ; journaux d'accès du proxy HTTPS de n8n (B27) sans adresse IP complète ou purgés sous 24 h. Contrôle automatique dès que l'export est livré dans `orchestration/n8n/` (`site/outils/verifier_site.py`, contrôle 15) |

**Tests de recette du contrat** (agent 12, avant le GO C07 ; tâche BL-187, J9) : inscription JS → `200` et email 01 reçu ; inscription sans JS → `303` vers `merci.html` ; consentement absent → rejet ; champ piège rempli → aucun email ; double envoi → un seul email ; lien de confirmation → page de confirmation et email 02 ; désinscription → plus aucun envoi, sur chaque outil ; origine non autorisée → refus CORS ; après un envoi réussi **et** après une erreur provoquée, aucune exécution du workflow d'inscription n'apparaît dans la liste des exécutions de n8n, l'incident ouvert (`GET /incidents`) et l'email de 04 ne contiennent ni IP ni email ; API arrêtée : l'alerte « moteur injoignable » arrive quand même.

**Calendrier (publication à J10).** n8n est hébergé en HTTPS au nom de l'entité dès J8 (intervention B27, BL-186), avec la pile interne en simulation (base, API du moteur pour les incidents, sauvegardes) et un proxy qui n'expose que le webhook d'inscription et les liens des emails ; la mise en service complète (workflows 01 à 08, webhooks Shopify, formulaires) suit à J26 (B23). Le workflow d'inscription est construit et recetté à J9 (BL-187) ; les liens des emails (confirmation, préférences, désinscription, refus d'avis) sont servis dès J10 par le workflow 06, ses trois déclencheurs Shopify restant désactivés tant que la boutique n'existe pas (ils s'inscriraient chez Shopify à l'activation). Sans eux, `WEBHOOK_INSCRIPTION` reste non validé et `publication.py` refuse la publication (fermé par défaut).

## 5. Mesure (protocole landing §6)

- **Inscriptions** : comptées dans n8n (démarrées = reçues ; confirmées = lien cliqué), par `utm_source`.
- **Visiteurs** : la page ne contient **aucun** outil de mesure ni cookie. Options à décider (propriétaire) : statistiques serveur de l'hébergeur (sans cookie ; offre et prix à vérifier) ou outil sans cookie déclaré dans `COOKIES.md`. Sans outil, le taux de conversion n'est pas mesurable : seul le nombre d'inscrits confirmés l'est (KPI principal du protocole).
- **Liens suivis** (protocole §5) : `URL_LANDING?utm_source=reseau`, `…=instagram`, `…=tiktok`, `…=club-{nom}`, `…=questionnaire`, `…=entretien`. Les valeurs sont nettoyées par la page (`[a-z0-9._-]`, 60 caractères).

## 6. Avant publication (agent 12, puis GO C07)

```bash
python site/outils/rapatrier_visuels.py --verifier  # visuels présents en local (§3.0)
python site/outils/da_sync.py --verifier
python site/outils/verifier_site.py                 # HTML, liens, termes interdits, accessibilité de base, typographie, visuels, maquettes
python site/outils/publication.py publication       # doit réussir (code 0)
python site/outils/verifier_site.py --dossier site/dist/landing
python -m pytest site/tests -q
```

- [ ] Aucun prix, stock, compteur, bouton d'achat ou de précommande (contrôlé par `verifier_site.py`).
- [ ] Aucun logo ni personnage Pokémon ; mention d'indépendance présente sur chaque page ; Braise affiché comme mascotte originale au nom provisoire.
- [ ] Visuels importés en local (`rapatrier_visuels.py --importer`), aucun visuel distant dans `site/dist/landing/` (contrôlé par `verifier_site.py --dossier`).
- [ ] Réservation garantie : les deux phrases du moteur reprises mot pour mot (contrôlé) ; aucun prix, aucun bouton de réservation sur la landing.
- [ ] Exploitant, adresse et email de contact visibles ; lien de confidentialité sur chaque page.
- [ ] Case de consentement non pré-cochée et obligatoire ; double opt-in et désinscription testés de bout en bout (§4).
- [ ] n8n hébergé en HTTPS (B27, J8) ; workflow d'inscription recetté sans exécution conservée (BL-187, J9 ; §4 « Effacement de l'IP »).
- [ ] Page publiée : le message sans JavaScript dit que le formulaire fonctionne aussi sans script (contrôle 13 de `verifier_site.py`).
- [ ] Aucune donnée interne dans le code source.
- [ ] Notice de la landing relue par le juriste (relecture express) et datée ; `publication.py etat` : tous les champs de la liste fermée `valide`.
- [ ] Affichage mobile (390 px) et ordinateur (1440 px) vérifié avec les visuels réels (l'ambiance est toujours claire), fil orange raccordé aux filets photographiés, animations en pause et `prefers-reduced-motion` testés, navigation au clavier testée.
- [ ] Liens UTM générés pour chaque source.

## 7. Changer la direction DA ou le nom

- Direction appliquée : **A + ambiance Atelier** (`python site/outils/da_sync.py --direction a --ambiance atelier` : copie les fichiers A et `tokens-atelier.css`, les logos et le favicon de l'Atelier, aligne `data-da`, `data-ambiance`, la feuille d'ambiance, `color-scheme` et Google Fonts sur toutes les pages, maquettes comprises). Une ambiance **archivée** (« nuit ») est refusée par `da_sync.py`. La feuille `css/landing.css` est dessinée pour l'Atelier : revenir à A sans ambiance (`--ambiance aucune`) demande de reprendre la mise en page.
- Image de partage : `python site/outils/generer_og.py` (gabarit `site/outils/og/og-image.html` : `renard-heros` local, titre sur voile papier ; Playwright et Chromium requis, outil local facultatif).
- Maquettes de la boutique (jamais publiées) : `site/maquettes/fiche-produit.html` (fiche d'un produit FICTIF en réservation garantie, deux prix FICTIFS) et `site/maquettes/drop.html` (page d'un drop FICTIF) ; mêmes feuilles que la landing ; contrôlées par `verifier_site.py` (FICTIF à côté de chaque prix et date, textes de garantie exacts, aucune urgence).
- Nom validé différent de « Quai des Cartes » : saisir `NOM_BOUTIQUE` (statut `valide`) dans le registre légal ; la publication remplace le nom partout, mais **refuse** tant que le logo DA n'a pas été refait pour ce nom (le logo est un lettrage du nom de travail) ; régénérer ensuite l'image de partage.

## Validation humaine requise

- [ ] **C06** : valider le nom ; la page publiée n'utilise jamais le nom de travail.
- [ ] **B08 / B04** : acheter le domaine, créer le compte d'hébergement (ou réclamer le site Netlify) et l'outil d'envoi d'emails ; renseigner `URL_LANDING`.
- [ ] Valider `MOIS_OUVERTURE` (proposé : « novembre 2026 », sans date ferme) dans `site/config/publication_landing.yaml`.
- [ ] Valider le texte de consentement (avec le juriste si souhaité) : toute modification crée une nouvelle `consentement_version`.
- [ ] Choisir : Google Fonts (DA) ou polices système (`--sans-google-fonts`), et renseigner `ST_POLICES` en conséquence ; choisir l'outil de mesure des visiteurs (ou aucun : la notice dit « aucun outil de mesure d'audience », à modifier avant d'en ajouter un).
- [ ] **C10** : valider l'ambiance « Atelier » appliquée (papier, charbon, fil orange) et la mascotte (renard, nom provisoire « Braise » ; alternatives : Suie, Kit ; recherche de marque, Braixen à examiner en priorité) avec `docs/05-da/DIRECTION_ATELIER.md` ; juriste : usage des visuels générés (renard original, boîtes vierges sans marque), conditions commerciales de l'outil de génération, photos d'ambiance (droits, droit à l'image des mains).
- [ ] Valider l'accroche du héro, proposée : **« Le calme avant le drop. »** (alternatives : « Rien d'inventé, tout en français. », « Le scellé, sans le bruit. ») ; le `h1` garde « Pokémon JCC en français, expédié depuis Genève » pour le référencement.
- [ ] Valider les titres de chapitre (« Une date, un statut, rien d'autre. », « Le soin, sans effet d'annonce. », « L'ouverture, sans la guetter. »…) et le texte de la fiche de Braise.
- [ ] **C07** : donner le GO de publication après la checklist §6 et les tests de recette du contrat n8n (§4).
