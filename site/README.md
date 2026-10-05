# site/ — landing de validation et boutique Shopify

> Propriétaire (build) : agent « site-contenu ». Exploitation : agent 07 Site et intégrations (écriture), agents 04, 08, 09, 12 (lecture).
> Sources : BP §1 (landing de validation), §7 (site marchand), §8 (DA), §9 (communication) ; SPEC §0 ; DA `docs/05-da/`.
> Nom de travail **« Quai des Cartes », provisoire et non validé** (C06). Aucun compte, domaine ou service n'a été créé.

## Contenu

| Chemin | Rôle |
|---|---|
| `landing/` | Page de présentation + inscription aux alertes (statique, sans faux stock, sans prix, sans précommande). Mode d'emploi : `landing/README.md` |
| `config/publication_landing.yaml` | Champs propres à la landing (URL publique, mois d'ouverture, webhook n8n), même format que le registre légal |
| `shopify/STRUCTURE_BOUTIQUE.md` | Collections, filtres, pages, navigation, métachamps publics, installation du thème |
| `shopify/MODELE_FICHE_PRODUIT.md` | Fiche produit standard (BP §7) : champs, sources, interdits, exemple FICTIF, contrôle |
| `shopify/snippets/` | Snippets Liquid : `da-badges`, `da-statut-stock`, `da-delai-sortie`, `da-mention-independance`, `da-formulaire-alertes`, `da-icone` |
| `outils/da_sync.py` | Copie les fichiers DA approuvés dans `landing/assets/da/` (+ manifeste d'empreintes) ; bascule de direction A/B |
| `outils/publication.py` | Pages secondaires (`source` ; la confidentialité vient de `docs/04-legal/CONFIDENTIALITE_LANDING.md`, notice limitée à la landing), dossier d'aperçu (`apercu`), dossier final (`publication`, refusé tant qu'un champ de la liste fermée `CHAMPS_LANDING` n'est pas validé : publiable à J10, sans champ de la boutique), `etat` |
| `outils/verifier_site.py` | Contrôles : HTML, liens, ressources externes, termes interdits, prix, affirmations inexactes (réponse humaine systématique, contenu des boîtes vérifié, finalité « uniquement », limite « par commande »), notice de confidentialité couvrant chaque champ du formulaire, nom de travail absent des modèles Shopify, accessibilité de base, typographie, snippets Liquid, synchronisation |
| `outils/typo.py`, `outils/markdown_mini.py` | Espaces insécables du français ; conversion des textes légaux en HTML |
| `outils/generer_og.py`, `outils/og/` | Image de partage 1200 × 630 (outil local facultatif : Playwright + Chromium, hors dépendances du projet) |
| `tests/` | Tests `pytest` du périmètre |
| `dist/` | Dossiers construits (ignorés par git) |

## Commandes

```bash
cd /home/user/1
python site/outils/da_sync.py                      # recopie la DA (direction du manifeste, A par défaut)
python site/outils/publication.py source           # régénère merci / confirmation / désinscription / confidentialité
python site/outils/publication.py etat             # champs requis pour publier, avec statut et décideur
python site/outils/publication.py apercu           # site/dist/apercu/
python site/outils/publication.py publication      # site/dist/landing/ (refus motivé tant que non validé)
python site/outils/verifier_site.py                # contrôles (code 1 si erreur)
python -m pytest site/tests -q                     # tests
```

Tests de rendu Liquid : ils utilisent `python-liquid` **s'il est installé** (outil de test local, pas une dépendance du projet) ; sinon ils sont ignorés, et le contrôle statique des snippets (balises équilibrées, libellés, termes interdits) s'exécute toujours. Test de bout en bout du formulaire : Playwright + Chromium s'ils sont disponibles (variable `CHROMIUM` pour le chemin de l'exécutable), sinon ignoré.

## Principes appliqués

1. **Aucune donnée interne** dans une page, un snippet, un payload ou un visuel (SPEC §0.2) : contrôlé par `verifier_site.py`.
2. **Aucun faux stock, aucune précommande sans allocation ferme** (SPEC §0.3) : la landing n'affiche ni stock ni prix ; les snippets n'affichent que trois statuts, et l'inventaire Shopify a le dernier mot.
3. **Simulation par défaut** (SPEC §0.6) : le formulaire reste désactivé tant que le webhook n'est pas configuré ; la publication refuse tout champ non validé.
4. **Une valeur, un endroit** : identité dans le registre légal, DA dans `docs/05-da/` (copies vérifiées par empreinte), textes légaux dans `docs/04-legal/` (convertis, jamais réécrits).

## Validation humaine requise

- [ ] C06 : valider le nom (la publication refuse le nom de travail).
- [ ] C10 : valider la direction DA (A par défaut ; bascule en une commande).
- [ ] B08, B04, B15 : domaine, outil d'envoi d'emails, boutique Shopify (comptes au nom de l'entité).
- [ ] C07 : GO de publication de la landing après la checklist de `landing/README.md` §6.
