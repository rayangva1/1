# site/ — landing de validation et boutique Shopify

> Propriétaire (build) : agent « site-contenu ». Exploitation : agent 07 Site et intégrations (écriture), agents 04, 08, 09, 12 (lecture).
> Sources : BP §1 (landing de validation), §7 (site marchand), §8 (DA), §9 (communication) ; SPEC §0 ; DA `docs/05-da/`.
> Nom de travail **« Quai des Cartes », provisoire et non validé** (C06). Aucun compte, domaine ou service n'a été créé.

## Contenu

| Chemin | Rôle |
|---|---|
| `landing/` | Page de présentation + inscription aux alertes (statique, sans faux stock, sans prix, sans précommande), en ambiance « Atelier » : héro plein écran, récit en huit chapitres porté par le renard « Braise » (nom provisoire), fil orange qui traverse les filets photographiés et relie les numéros de chapitre, pages secondaires illustrées. Mode d'emploi : `landing/README.md` |
| `maquettes/` | Maquettes **jamais publiées** de la boutique dans la même ambiance : `fiche-produit.html` (produit FICTIF en réservation garantie) et `drop.html` (drop FICTIF) |
| `config/visuels.json` | Source unique des 13 visuels de la marque (10 illustrations du renard, 3 photos d'ambiance : dimensions, format, nature, usage, description, texte alternatif, filet orange mesuré, largeurs des variantes, source importée) ; `outils/visuels.py` les applique aux pages, `outils/rapatrier_visuels.py --importer <dossier>` les importe **en local** (source d'origine archivée dans `visuels-sources/`, ignoré par git ; variantes WebP budgétées dans `landing/assets/visuels/`) |
| `config/publication_landing.yaml` | Champs propres à la landing (URL publique, mois d'ouverture, webhook n8n), même format que le registre légal |
| `shopify/STRUCTURE_BOUTIQUE.md` | Collections, filtres, pages, navigation, métachamps publics, installation du thème |
| `shopify/MODELE_FICHE_PRODUIT.md` | Fiche produit standard (BP §7) : champs, sources, interdits, exemple FICTIF, contrôle |
| `shopify/snippets/` | Snippets Liquid : `da-badges`, `da-statut-stock`, `da-delai-sortie`, `da-mention-independance`, `da-formulaire-alertes`, `da-icone` |
| `outils/da_sync.py` | Copie les fichiers DA approuvés dans `landing/assets/da/` (+ manifeste d'empreintes) ; bascule de direction A/B et d'ambiance (Atelier, toujours claire ; une ambiance archivée, comme Nuit, est refusée) |
| `outils/visuels.py`, `outils/rapatrier_visuels.py`, `outils/renard_svg.py` | Balises `data-visuel` synchronisées avec `config/visuels.json` (adresses, dimensions, texte alternatif et filet orange mesuré `data-fil` ; jamais de PNG dans un `srcset`) ; import local contrôlé (format réel JPEG/PNG/WebP, proportions, orientation EXIF, sRGB, aucune métadonnée publiée), variantes WebP dans un budget de poids, bascule en local, fermé par défaut ; silhouette SVG du renard pour le décor de secours |
| `outils/publication.py` | Pages secondaires (`source` ; la confidentialité vient de `docs/04-legal/CONFIDENTIALITE_LANDING.md`, notice limitée à la landing), dossier d'aperçu (`apercu`), dossier final (`publication`, refusé tant qu'un champ de la liste fermée `CHAMPS_LANDING` n'est pas validé : publiable à J10, sans champ de la boutique), `etat` |
| `outils/verifier_site.py` | Contrôles : HTML, liens, ressources externes, termes interdits, prix, mascotte (aucune trace de l'ancienne mascotte ; Braise toujours « nom provisoire » et création originale « pour la boutique », jamais « de la boutique »), image de partage (JPEG ou WebP local de 1200 × 630, au plus 300 Ko, sans métadonnées, gabarit sans « stock réel » et avec la non-affiliation), affirmations inexactes (réponse humaine systématique, contenu des boîtes vérifié, « ouvre la boîte » alors que les produits scellés ne sont jamais ouverts, finalité « uniquement », limite « par commande »), notice de confidentialité couvrant chaque champ du formulaire, nom de travail absent des modèles Shopify, message sans JavaScript exact sur la page publiée, chaque champ de la landing fourni au plus tard à J10 (interventions et backlog), workflow d'inscription sans exécution conservée (dès son export), accessibilité de base, typographie, snippets Liquid, synchronisation |
| `outils/typo.py`, `outils/markdown_mini.py` | Espaces insécables du français ; conversion des textes légaux en HTML |
| `outils/generer_og.py`, `outils/og/` | Image de partage 1200 × 630 (`landing/assets/og-image.jpg`, JPEG d'au plus 300 Ko, sans métadonnées) : renard du héro, titre sur voile papier, « ouverture prochaine » (jamais « stock réel ») et mention de non-affiliation lisible ; outil local facultatif, sans réseau (Playwright pour Python, ou pour Node via `og/rendre_og.mjs`, + Chromium, hors dépendances du projet) |
| `tests/` | Tests `pytest` du périmètre ; `tests/e2e/atelier.mjs` : tests navigateur (Node + Playwright + Chromium, polices OFL servies en local depuis `tests/e2e/polices/`), lancés par `scripts/run_all_tests.sh` |
| `dist/` | Dossiers construits (ignorés par git) |

## Commandes

```bash
cd /home/user/1
python site/outils/da_sync.py                      # recopie la DA (direction du manifeste, A par défaut)
python site/outils/publication.py source           # régénère merci / confirmation / désinscription / confidentialité
python site/outils/publication.py etat             # champs requis pour publier, avec statut et décideur
python site/outils/publication.py apercu           # site/dist/apercu/
python site/outils/publication.py publication      # site/dist/landing/ (refus motivé tant que non validé)
python site/outils/rapatrier_visuels.py --importer <dossier>   # visuels en local (aucun réseau)
python site/outils/verifier_site.py                # contrôles (code 1 si erreur)
python -m pytest site/tests -q                     # tests
node site/tests/e2e/atelier.mjs                    # tests navigateur (code 1 si un contrôle échoue)
E2E_FILTRE=fil node site/tests/e2e/atelier.mjs     # seulement les contrôles dont le nom correspond
```

Tests de rendu Liquid : ils utilisent `python-liquid` **s'il est installé** (outil de test local, pas une dépendance du projet) ; sinon ils sont ignorés, et le contrôle statique des snippets (balises équilibrées, libellés, termes interdits) s'exécute toujours. Tests navigateur : `site/tests/e2e/atelier.mjs` (Node + Playwright ; module `playwright`, sinon `PLAYWRIGHT_MJS`, sinon `/opt/node-tools` ; `CHROMIUM` pour un exécutable précis ; jamais d'appel réseau : polices et webhook interceptés) — formulaire, pause et mouvement réduit (défilement doux compris), sans JavaScript, clavier, images indisponibles, WebP budgété, contraste AA des textes posés sur une illustration (images remplacées par du noir et du blanc purs), bouton du héro au-dessus du pli, aucun renard fantôme, aucun mot coupé dans un titre, fil orange jamais sur un texte, hiérarchie des titres, longueur de page bornée. `scripts/run_all_tests.sh` les lance quand Node et Playwright sont présents et annonce en toutes lettres quand ils sont **ignorés**. `tests/test_landing_e2e.py` (Playwright pour Python) couvre le même parcours s'il est installé, sinon il est ignoré.

## Principes appliqués

1. **Aucune donnée interne** dans une page, un snippet, un payload ou un visuel (SPEC §0.2) : contrôlé par `verifier_site.py`.
2. **Aucun faux stock, aucune précommande sans allocation ferme** (SPEC §0.3) : la landing n'affiche ni stock ni prix ; les snippets n'affichent que trois statuts, et l'inventaire Shopify a le dernier mot.
3. **Simulation par défaut** (SPEC §0.6) : le formulaire reste désactivé tant que le webhook n'est pas configuré ; la publication refuse tout champ non validé.
4. **Une valeur, un endroit** : identité dans le registre légal, DA dans `docs/05-da/` (copies vérifiées par empreinte), textes légaux dans `docs/04-legal/` (convertis, jamais réécrits).

## Validation humaine requise

- [ ] C06 : valider le nom (la publication refuse le nom de travail).
- [ ] C10 : valider l'ambiance « Atelier » appliquée le 10.10.2026 (`docs/05-da/DIRECTION_ATELIER.md`, retenue par le propriétaire le 06.10.2026) et la mascotte, un renard au nom provisoire « Braise » (alternatives : Suie, Kit ; recherche de marque à faire).
- [ ] Valider l'accroche du héro (« Le calme avant le drop. », proposition) et les titres des chapitres (`landing/README.md` §0).
- [ ] B08, B04, B15 : domaine, outil d'envoi d'emails, boutique Shopify (comptes au nom de l'entité).
- [ ] C07 : GO de publication de la landing après la checklist de `landing/README.md` §6.
