# Landing de validation — présentation et inscription aux alertes

> Propriétaire (build) : agent « site-contenu ». Exploitation : agent 07 Site (BL-031), suivi KPI agent 10 (BL-034), contrôle agent 12.
> Sources : BP §1 (« Tester une page de présentation avec inscription aux alertes. Aucun faux stock et aucune précommande encaissée sans allocation »), §7, §8, §9 (J1-15) ; protocole `docs/01-marche/PROTOCOLE_LANDING_TEST.md` ; DA `docs/05-da/`.
> Nom de travail **« Quai des Cartes » — provisoire, non validé** (décision C06). Statut : **aperçu prêt ; publication bloquée** tant que les champs ne sont pas validés et que les visuels ne sont pas rapatriés en local (voir §6).
> Ambiance **« Nuit sur le Léman »** (direction B, toujours sombre) : `docs/05-da/DIRECTION_NUIT.md`. Mascotte **Lumi (nom provisoire)**, loutre originale.

## 1. Ce que la page fait, et ce qu'elle ne fait jamais

| Fait | Ne fait jamais |
|---|---|
| Présente la promesse du BP §1 : Pokémon JCC en français, expédié depuis la Suisse, disponibilité lisible, produits correctement identifiés, service fiable | Afficher un stock, un compteur, « dernières pièces », un minuteur |
| Explique le jour du drop et la **réservation garantie** de la future boutique (badges DA « Réservation garantie » et « Drop le JJ.MM », les deux phrases exactes du moteur : le supplément paie la garantie, pas le produit ; aucun remboursement de la différence) | Ouvrir une réservation, afficher un prix de drop ou de réservation, un supplément en francs |
| Explique les 3 statuts (Stock local, Précommande sur quantité confirmée, Rupture) avec les badges DA | Afficher un prix, même indicatif (les tranches de budget du formulaire sont des préférences déclarées, pas des prix) |
| Liste les formats prévus, sans engagement de sélection | Prendre une précommande, un acompte ou une réservation |
| Recueille l'inscription aux alertes : email, prénom facultatif, formats, budget, pour qui, canton, **consentement non pré-coché** | Envoyer un email sans confirmation (double opt-in fait par n8n) |
| Affiche la mention d'indépendance (non-affiliation à The Pokémon Company), l'exploitant et le lien confidentialité | Utiliser un logo, un personnage ou une police de la licence ; contenir un coût, une marge ou un nom de fournisseur |
| Ambiance de nuit immersive, toujours sombre (contrastes AA calculés, `DIRECTION_NUIT.md`), mobile d'abord, accessible (libellés, erreurs annoncées, focus visible en or, cibles de 44 px, textes alternatifs) ; animations coupées par `prefers-reduced-motion` et par le bouton « Pause des animations » (WCAG 2.2.2) ; rien n'est masqué sans JavaScript | Charger un script tiers, un pixel publicitaire ou un cookie (ressources externes : Google Fonts, retirable ; en **aperçu seulement**, les visuels de la marque à leur adresse distante — jamais dans le dossier publié) |

## 2. Fichiers

| Fichier | Rôle | Modifié par |
|---|---|---|
| `index.html` | Page principale (source, champs `{{…}}` visibles) | À la main (agent 07) |
| `merci.html`, `inscription-confirmee.html`, `desinscription.html` | Pages de retour du workflow n8n (sans JavaScript, après confirmation, après désinscription) | **Générées** : `python site/outils/publication.py source` |
| `confidentialite.html` | Notice de confidentialité **de la landing** = bloc public de `docs/04-legal/CONFIDENTIALITE_LANDING.md` converti en HTML (chaque champ du formulaire y est déclaré : contrôlé par `verifier_site.py`) ; la déclaration complète de la boutique (`CONFIDENTIALITE.md`) la remplace à l'ouverture | **Générée** (même commande) ; le texte se corrige dans `docs/04-legal/` |
| `css/landing.css` | Mise en page de la landing **et des maquettes** (`site/maquettes/`) : héro, scènes de secours dessinées en CSS (ciel, lune, lac, montagnes, Lumi), cartes « verre dépoli », formulaire ; uniquement des variables `--da-*` ; mouvement seulement sous `prefers-reduced-motion: no-preference` | À la main |
| `js/theme.js` | Avant affichage : classe `lp-js` (les apparitions ne masquent rien sans script) et choix « Pause des animations » mémorisé | À la main |
| `js/landing.js` | Formulaire (validation, envoi, messages) ; fonctions pures dans `LandingCore` | À la main |
| `js/nuit.js` | Effets : fondu des visuels (et masquage d'une image qui ne charge pas : le décor CSS reste), apparitions au défilement, parallaxe, lueur du pointeur, survol 3D des cartes, bouton « Pause des animations ». Aucun appel réseau | À la main |
| `assets/visuels/` | Visuels de la marque **rapatriés** (absents tant que `rapatrier_visuels.py` n'a pas tourné) | **Générés** : `python site/outils/rapatrier_visuels.py` |
| `../config/visuels.json` | **Source unique** des 12 visuels (adresse distante, dimensions, usage) ; les pages n'ont que des balises `data-visuel` | `rapatrier_visuels.py` (bascule `source`), à la main pour ajouter un visuel |
| `js/config.js` | `webhookUrl` (vide = formulaire désactivé avec message), `mode`, `emailSupport` | `publication.py` (ou à la main, §3.4) |
| `assets/da/` | Copies des fichiers DA (tokens, composants, `ambiance.css` = tokens Nuit, logos, favicons) + `manifeste.json` (direction **b**, ambiance **nuit**) | **Générées** : `python site/outils/da_sync.py` |
| `assets/og-image.png` | Image de partage 1200 × 630 (ambiance Nuit, décor CSS, sans image distante) | `python site/outils/generer_og.py` (outil local facultatif) |
| `inscription.schema.json` | Contrat des champs envoyés au webhook n8n | À la main, avec l'agent integrations |
| `../config/publication_landing.yaml` | `URL_LANDING`, `MOIS_OUVERTURE`, `WEBHOOK_INSCRIPTION` (mêmes statuts que le registre légal) | Agent 07, propriétaire |

Les champs d'identité (`NOM_BOUTIQUE`, `RAISON_SOCIALE`, `ADRESSE_POSTALE`, `EMAIL_SUPPORT`…) viennent **uniquement** du registre légal `docs/04-legal/champs_a_remplir.yaml` : une valeur, un endroit.

## 3. Déployer sans écrire de code

### 3.0 Rapatrier les visuels (avant toute mise en ligne)

Les 12 visuels de la marque, générés avec Higgsfield (héro « Nuit étoilée », jour de drop, réservation garantie, Léman, aurore, Alpes, planche et autocollant de Lumi…), sont listés dans **un seul fichier**, `site/config/visuels.json`. En aperçu, la page les charge à leur **adresse distante** (celle de l'outil de génération) ; **la page publiée doit les servir elle-même** : la politique de sécurité publiée n'autorise que les images du site (`img-src 'self'`) et aucune adresse IP de visiteur ne doit partir vers un tiers. Sur une machine dont le réseau atteint cette adresse :

```bash
cd /home/user/1
python site/outils/rapatrier_visuels.py              # télécharge les 24 fichiers (≈ 12 PNG HD + 12 WebP légers) dans site/landing/assets/visuels/
python site/outils/rapatrier_visuels.py --verifier   # contrôle format et dimensions, sans réseau
python site/outils/visuels.py verifier               # pages synchronisées avec le manifeste
```

Le script contrôle chaque fichier (signature PNG/WebP, taille, dimensions de la PNG identiques au manifeste, proportions de la version légère), mesure la largeur réelle des versions légères (les `srcset` deviennent exacts), passe `source` à `local` et réécrit les balises `data-visuel` de la landing et des maquettes. **Fermé par défaut** : si un fichier manque ou est refusé, rien ne bascule (relancer plus tard ; `--forcer` retélécharge tout). `--distant` revient à l'aperçu distant (la publication est alors refusée). Les PNG pèsent plusieurs mégaoctets : ils ne servent qu'aux grands écrans (`srcset`), la version WebP légère est chargée en priorité. Tant que le réseau ne permet pas le téléchargement, chaque emplacement garde un **décor de secours en CSS** (ciel, lune, lac, montagnes, Lumi dessinée) : la page reste belle sans image.

Ajouter ou remplacer un visuel : l'ajouter dans `visuels.json` (identifiant, nom de fichier sans extension, dimensions, description), écrire la balise `<img data-visuel="…" alt="…" sizes="…" loading="lazy" decoding="async">` dans la page, puis `python site/outils/visuels.py appliquer`. Jamais d'adresse d'image écrite à la main (contrôlé par `verifier_site.py`).

### 3.1 Préparer le dossier (agent 07, 1 commande)

```bash
cd /home/user/1
python site/outils/publication.py etat          # ce qui manque encore, et qui doit le fournir
python site/outils/publication.py apercu        # dossier d'aperçu : site/dist/apercu/ (page non indexée)
python site/outils/publication.py publication   # dossier final : site/dist/landing/ — REFUSE tant que tout n'est pas validé et que les visuels sont distants
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
- [ ] Aucun logo ni personnage Pokémon ; mention d'indépendance présente sur chaque page ; Lumi affichée comme mascotte originale au nom provisoire.
- [ ] Visuels rapatriés en local (`rapatrier_visuels.py`), aucun visuel distant dans `site/dist/landing/` (contrôlé par `verifier_site.py --dossier`).
- [ ] Réservation garantie : les deux phrases du moteur reprises mot pour mot (contrôlé) ; aucun prix, aucun bouton de réservation sur la landing.
- [ ] Exploitant, adresse et email de contact visibles ; lien de confidentialité sur chaque page.
- [ ] Case de consentement non pré-cochée et obligatoire ; double opt-in et désinscription testés de bout en bout (§4).
- [ ] n8n hébergé en HTTPS (B27, J8) ; workflow d'inscription recetté sans exécution conservée (BL-187, J9 ; §4 « Effacement de l'IP »).
- [ ] Page publiée : le message sans JavaScript dit que le formulaire fonctionne aussi sans script (contrôle 13 de `verifier_site.py`).
- [ ] Aucune donnée interne dans le code source.
- [ ] Notice de la landing relue par le juriste (relecture express) et datée ; `publication.py etat` : tous les champs de la liste fermée `valide`.
- [ ] Affichage mobile (390 px) et ordinateur (1440 px) vérifié avec les visuels réels (l'ambiance est toujours sombre), animations en pause et `prefers-reduced-motion` testés, navigation au clavier testée.
- [ ] Liens UTM générés pour chaque source.

## 7. Changer la direction DA ou le nom

- Direction actuelle : **B + ambiance Nuit** (`python site/outils/da_sync.py --direction b --ambiance nuit` : copie les fichiers B et `tokens-nuit.css`, le logo Nuit, aligne `data-da`, `data-ambiance`, la feuille d'ambiance et Google Fonts sur toutes les pages, maquettes comprises). La feuille `css/landing.css` est dessinée pour l'ambiance Nuit : revenir à A ou à B sans ambiance (`--ambiance aucune`) demande de reprendre la mise en page.
- Image de partage : `python site/outils/generer_og.py` (gabarit `site/outils/og/og-image.html`, décor CSS).
- Maquettes de la boutique (jamais publiées) : `site/maquettes/fiche-produit.html` (fiche d'un produit FICTIF en réservation garantie, deux prix FICTIFS) et `site/maquettes/drop.html` (page d'un drop FICTIF) ; mêmes feuilles que la landing ; contrôlées par `verifier_site.py` (FICTIF à côté de chaque prix et date, textes de garantie exacts, aucune urgence).
- Nom validé différent de « Quai des Cartes » : saisir `NOM_BOUTIQUE` (statut `valide`) dans le registre légal ; la publication remplace le nom partout, mais **refuse** tant que le logo DA n'a pas été refait pour ce nom (le logo est un lettrage du nom de travail) ; régénérer ensuite l'image de partage.

## Validation humaine requise

- [ ] **C06** : valider le nom ; la page publiée n'utilise jamais le nom de travail.
- [ ] **B08 / B04** : acheter le domaine, créer le compte d'hébergement (ou réclamer le site Netlify) et l'outil d'envoi d'emails ; renseigner `URL_LANDING`.
- [ ] Valider `MOIS_OUVERTURE` (proposé : « novembre 2026 », sans date ferme) dans `site/config/publication_landing.yaml`.
- [ ] Valider le texte de consentement (avec le juriste si souhaité) : toute modification crée une nouvelle `consentement_version`.
- [ ] Choisir : Google Fonts (DA) ou polices système (`--sans-google-fonts`), et renseigner `ST_POLICES` en conséquence ; choisir l'outil de mesure des visiteurs (ou aucun : la notice dit « aucun outil de mesure d'audience », à modifier avant d'en ajouter un).
- [ ] **C10** : valider l'ambiance « Nuit sur le Léman » (direction B) et la mascotte Lumi (nom provisoire) ; juriste : usage des visuels générés (mascotte originale, boîtes génériques sans marque) et conditions commerciales de l'outil de génération.
- [ ] Avant la mise en ligne : rapatrier les visuels (§3.0) sur une machine qui atteint leur adresse, vérifier le rendu avec les vraies images (héro 21:9 sur ordinateur, couverture 9:16 sur mobile).
- [ ] **C07** : donner le GO de publication après la checklist §6 et les tests de recette du contrat n8n (§4).
