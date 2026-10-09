# 05-da — Direction artistique

> Propriétaire : agent « direction-artistique ». Date : 4 octobre 2026 (ambiance Atelier : 9 octobre 2026). Source métier : BP §8 (et §1, §7, §9).
> Statut : **PROPOSITION — identité non validée.** Nom de travail : **Quai des Cartes** (`{{NOM_BOUTIQUE}}` reste le placeholder des textes publics tant que le nom n'est pas validé, SPEC §5).

La DA sert l'étoile polaire (contribution nette cumulée) : faire acheter en confiance, réduire les erreurs d'achat et le SAV, produire vite et pour presque rien. Elle ne compense pas une marge insuffisante (BP §1).

## 1. Ce qui est livré

| Livrable (brief) | Où | Contenu |
|---|---|---|
| 1. Naming | `NAMING.md` | 3 pistes + 5 alternatives + noms écartés, prononciation FR/DE, recherche web préliminaire sourcée, recommandation, check-list des vérifications humaines |
| 2. Deux directions | `DIRECTION_A.md` (Quai, orange) · `DIRECTION_B.md` (Pochette, violet) | Concept, palette clair/sombre avec rôles, **96 contrastes WCAG calculés**, polices, grille, icônes, photo, références, page produit |
| 2 bis. **Ambiance Atelier** (retenue le 06.10.2026) | `DIRECTION_ATELIER.md` (bâtie sur A, toujours claire) · `tokens/tokens-atelier.css` · `logo/a/logo-a-atelier.svg`, `logo/a/logo-a-atelier-fond-sombre.svg`, `logo/a/favicon-atelier.svg` | Palette **mesurée sur les photos du propriétaire** (papier `#EFEAE1`, charbon `#1D1B19`, fil orange `#F26A1B`), **45 contrastes calculés**, Geist + Instrument Serif + Geist Mono, grille éditoriale, motif signature « le fil orange », règles photo, **règles de marque du renard Braise (nom provisoire)**, alternatives de nom |
| 2 ter. Ambiance Nuit (**archivée**) | `DIRECTION_NUIT.md` (« Nuit sur le Léman », bâtie sur B, toujours sombre) · `tokens/tokens-nuit.css` · `logo/b/logo-b-nuit.svg` | Remplacée par Atelier (décision du propriétaire du 06.10.2026) ; gardée tant que la landing actuelle n'est pas refaite. La loutre Lumi est abandonnée. |
| 3. Tokens | `tokens/tokens.json` (source) · `tokens/tokens.css`, `tokens/tokens-atelier.css`, `tokens/tokens-nuit.css` (générés) | 2 directions × clair/sombre + ambiances (bloc `ambiances` : un seul mode chacune, paires de contraste propres), espacements, typo, rayons, ombres |
| 4. Logos | `logo/a/`, `logo/b/`, `logo/png/`, `logo/REGLES_LOGO.md` | Principal, horizontal/empilé, fond sombre, mono noir/blanc, monogramme, favicon ; zone de protection, tailles mini |
| 5. Mini-charte | `CHARTE.html` | 12 sections, bascule A/B et clair/sombre, contrastes recalculés en direct |
| 6. Composants | `components/` | `badges.html`, `carte-produit.html`, `banniere.html`, `page-produit.html`, `email-transactionnel-{a,b}.html`, `components.css`, `icones.svg`, `apercu.js` |
| 7. Réseaux sociaux | `social/a/`, `social/b/`, `social/guides/` | Couvertures 1:1, 4:5, 9:16 ; story 9:16 ; carrousel 3 slides en 4:5 et 1:1 ; zones sûres indicatives |
| 8. Packaging | `packaging/a/`, `packaging/b/`, `packaging/NOTE_CHIFFRAGE.md` | Sticker Ø 50 mm, carte A6 recto/verso, repère commande 70 × 37 mm (SVG en mm, fond perdu, découpe) + note de devis |
| Outils | `tools/` | `glyphes.py` (lettrage des logos), `icones.py` (pictogrammes), `pages_html.py` (charte et pages composants), `generer_da.py` (génération de tous les fichiers), `verifier_da.py` (contrôles), `contraste.py` (WCAG) |
| Tests | `tests/test_da.py` | `python -m pytest docs/05-da/tests -q` |

Tous les exemples de produits, prix et dates sont **FICTIFS** (marqués comme tels). Aucun EAN, aucun prix fournisseur, aucun contact réel.

## 2. Règles non négociables pour tous les agents qui utilisent ces fichiers

1. **Aucune donnée interne** dans un visuel, un email ou une page publique : uniquement titre, format, langue, état, prix public validé, statut de stock, délai, limite par foyer, photo autorisée (SPEC §0.2). `verifier_da.py` bloque les termes internes dans `components/`, `social/`, `packaging/`, `logo/`.
2. **Prix** : celui validé par le moteur au moment de publier (BP §8). Une promo repasse par le moteur ; si le stop-loss produit ou pub bloque, le visuel n'est pas publié.
3. **Stock** : « Stock local » seulement pour du stock vendable réel ; « Précommande » seulement avec allocation ferme (SPEC §0.3).
4. **Photos réelles** uniquement ; jamais d'emballage généré (BP §7).
5. **Licence** : « Pokémon » désigne les produits ; jamais de personnage, Poké Ball, police, logo ou symbole de la licence ; jamais « officiel » (BP §8).
6. **Ton** : précis, accessible, sans fausse urgence (pas de compte à rebours, « dernières pièces », promesse de carte rare ou de valeur future).

## 3. Utilisation

### Site (Shopify)
- Ajouter `tokens/tokens.css` et `components/components.css` aux assets du thème ; fixer `data-da="a"` (ou `"b"`) sur `<html>` une fois la direction choisie. Ne pas embarquer `apercu.js` (outil de démonstration).
- Polices : l'aperçu les charge depuis Google Fonts. **En production, préférer l'auto-hébergement** des fichiers (licence OFL) pour ne pas transmettre l'adresse IP des visiteurs à Google (point confidentialité à valider, nLPD).
- Reprendre le balisage de `components/carte-produit.html` et `page-produit.html` dans les sections du thème ; les classes `da-*` sont autonomes.
- Logo d'en-tête : `logo/a/logo-a-horizontal.svg` (ou PNG `logo/png/`) ; favicon : `logo/png/favicon-a-32.png`. Détails : `logo/REGLES_LOGO.md`.
- Emails : `components/email-transactionnel-{a,b}.html` = gabarit de confirmation de commande en tableaux et styles en ligne. Relier les `{{CHAMPS}}` aux variables Liquid des notifications Shopify (à vérifier dans la doc Shopify du moment) ; héberger `logo/png/logo-a-email.png` dans Shopify Fichiers.

### Figma
- Importer les SVG (logos, `social/`, `packaging/`) : vecteurs et textes restent éditables si les polices sont installées.
- Couleurs et typo : créer les styles depuis `tokens/tokens.json` (ou via un plugin d'import de tokens, après aplatissement des groupes).

### Canva / Adobe Express
- Kit de marque : couleurs hex de la direction retenue + les trois polices (disponibles dans ces bibliothèques ou à téléverser si l'offre le permet — à vérifier).
- Importer les SVG de `social/` comme base. **Selon l'outil, le texte d'un SVG importé peut devenir non éditable** : dans ce cas, garder le SVG comme calque de fond et recréer les zones texte avec le kit de marque. Remplacer chaque `ZONE_PHOTO` par une photo réelle.
- Formats et zones sûres : `social/guides/` (valeurs indicatives à revérifier sur chaque plateforme au moment de produire, BP §8).

### Impression
- `packaging/NOTE_CHIFFRAGE.md` : formats, fonds perdus, questions aux imprimeurs, tableau de devis, intégration du coût dans le paramètre logistique du moteur.

## 4. Régénérer et vérifier

```bash
cd /home/user/1
python docs/05-da/tools/generer_da.py          # tokens.css, logos, social, packaging, emails, tableaux de contrastes
python docs/05-da/tools/generer_da.py --png    # + exports PNG (nécessite cairosvg, outil local hors moteur)
python docs/05-da/tools/verifier_da.py         # contrôles (code de sortie 1 si erreur)
python -m pytest docs/05-da/tests -q           # tests
```

Les HTML (`CHARTE.html`, `components/*.html`), les SVG et `tokens.css` sont **générés** : modifier la source (`tokens.json`, `tools/*.py`, `components/components.css`) puis régénérer, jamais le fichier produit. Pour changer une couleur : modifier `tokens/tokens.json`, relancer le générateur (les tableaux de contrastes de `DIRECTION_*.md` sont réécrits), puis le vérificateur. Une couleur sous le seuil WCAG fait échouer les tests.

`verifier_da.py` contrôle : XML bien formé de chaque SVG (viewBox, dimensions, titre) ; logos sans texte ni police ni « Poké » ; dimensions des gabarits sociaux ; packaging en mm avec calque de découpe ; contrastes ≥ seuils (2 directions × 2 modes, puis chaque ambiance dans son mode unique avec ses paires propres) ; règles de marque de la mascotte écrites dans `DIRECTION_ATELIER.md` ; exactitude des ratios publiés ou cités ; synchronisation des fichiers générés ; ressources HTML relatives existantes et externes limitées à Google Fonts ; aucun terme interne ni EAN dans les fichiers publics ; champs `{{…}}` des fichiers publics déclarés (registre légal, landing ou `VARIABLES_DA`) et aucune limite « par commande » ; section finale « Validation humaine requise » dans chaque document.

## 5. Champs à remplacer (placeholders)

`{{NOM_BOUTIQUE}}`, `{{SITE}}`, `{{EXTENSION}}`, `{{PRIX_VALIDE}}`, `{{MENTION_TVA}}`, `{{DELAI_EXPEDITION}}`, `{{LIMITE_PAR_CLIENT}}` (limite par référence et par foyer, CGV ch. 4.4 : jamais « par commande »), `{{DATE_SORTIE}}`, `{{CONTENU_VALIDE}}`, `{{SKU}}`, `{{EAN_SI_EXISTANT}}`, `{{EMAIL_SUPPORT}}`, `{{URL_RETOURS}}`, `{{URL_CGV}}`, `{{DELAI_SIGNALEMENT}}`, `{{RAISON_SOCIALE}}`, `{{ADRESSE}}`, `{{NUMERO_IDE}}`, `{{N_COMMANDE}}`. La mention TVA dépend du statut fiscal (décision fiduciaire) : ne rien afficher tant qu'il n'est pas tranché.

Règle « une valeur, un endroit » : tout champ `{{MAJUSCULES}}` d'un fichier public est soit un champ du registre légal (`docs/04-legal/champs_a_remplir.yaml`) ou de la landing (`site/config/publication_landing.yaml`), soit une variable propre à un produit, une commande ou une collection de la liste fermée `VARIABLES_DA` de `tools/verifier_da.py` (jamais une règle : limite, délai, TVA). `verifier_da.py` refuse tout autre champ et toute limite exprimée « par commande ».

## 6. Ambiance « Atelier » et mascotte (renard Braise, nom provisoire)

Décision du propriétaire du 06.10.2026 : l'ambiance **Atelier** (`DIRECTION_ATELIER.md`) remplace « Nuit sur le Léman » et la loutre Lumi. Activation : `data-da="a"` + `data-ambiance="atelier"` sur `<html>`, `tokens/tokens-atelier.css` chargé après `tokens.css` (copie `site/landing/assets/da/ambiance.css` par `python site/outils/da_sync.py --direction a --ambiance atelier`). Palette mesurée sur les photos, polices, grille, motif « le fil orange », règles photo et **règles de marque du renard** (toujours quadrupède, une seule queue, jamais debout, ni gants ni vêtements, aucun trait d'Évoli ni d'un Pokémon, ne tient jamais un produit Pokémon, n'illustre jamais un produit vendu) : `DIRECTION_ATELIER.md` §8, contrôlées par `verifier_da.py`.

Visuels : 13 fichiers (10 illustrations du renard, 3 photos d'ambiance du propriétaire) déclarés dans `site/config/visuels.json` et servis **en local** (import : `python site/outils/rapatrier_visuels.py --importer <dossier>`). Étape en cours : la landing actuelle garde l'ambiance Nuit (archivée) avec les nouveaux visuels jusqu'à sa refonte en Atelier (étape 2).

## Validation humaine requise

**Une seule séance de validation de l'identité par la responsable (≈ 30 minutes, BP §8)**, à faire avec `CHARTE.html` ouvert :

- [ ] **Nom** : après vérification humaine du domaine .ch, des handles et des marques (Swissreg/IPI, EUIPO, OMPI, Zefix — check-list `NAMING.md` §6), valider « Quai des Cartes » ou la piste de repli.
- [ ] **Direction** : choisir A (Quai, orange) **ou** B (Pochette, violet). *Le propriétaire a retenu le 06.10.2026 l'ambiance Atelier, bâtie sur A : à confirmer en séance avec `DIRECTION_ATELIER.md` (palette, polices, mascotte et son nom).*
- [ ] **Logo, couleur d'accent, polices** de la direction retenue.
- [ ] **Juriste** : mention « boutique indépendante » et mention de marque en pied de page ; usage du mot « Pokémon » pour désigner les produits.
- [ ] **Confidentialité** : chargement des polices (Google Fonts ou auto-hébergement).
- [ ] **Impression** : devis réels et BAT avant toute commande (`packaging/NOTE_CHIFFRAGE.md`).

Après validation, les agents de contenu et de site n'utilisent plus que ces composants ; toute modification de l'identité sort du mandat des agents et revient à la responsable.
