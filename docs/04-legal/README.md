# 04-legal — textes légaux (brouillons) — {{NOM_BOUTIQUE}}

> **À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION**
> Tous les textes de ce dossier sont des **brouillons** rédigés par l'agent legal-ops le 4.10.2026. Aucun n'est un avis juridique ; aucun ne doit être publié avant la relecture du juriste (BL-096) et la validation de la propriétaire (C11).
> Source métier : BP du 4.10.2026, §5 (stock, précommandes), §7 (paiement et conformité), §12 (workflows). Contrat technique : `docs/SPEC.md`.

## Contenu

| Fichier | Rôle | Publié sur le site ? |
|---|---|---|
| `CGV.md` | Conditions générales de vente : droit suisse, prix CHF TTC, Suisse uniquement, précommandes sur allocation ferme, limites par foyer, erreurs de prix, garantie art. 197 ss CO, retour volontaire, for à Genève | Oui (bloc public) |
| `LIVRAISON_RETOURS.md` | Frais, délais, suivi, colis perdu ou endommagé, retours volontaires, remboursements | Oui (bloc public) |
| `PRECOMMANDES.md` | Page client + règles internes (définition de l'allocation ferme, checklist d'ouverture, événements) | Oui (partie 1) |
| `CONFIDENTIALITE.md` | Déclaration LPD : responsable, finalités, prestataires, étranger, durées, droits, marketing, IA ; registre simplifié | Oui (bloc public) |
| `MENTIONS_LEGALES.md` | Impressum : identité, adresse, email, IDE, RC, TVA, hébergeur, non-affiliation | Oui (bloc public) |
| `COOKIES.md` | Information et refus des cookies (art. 45c LTC), mode d'emploi du relevé réel | Oui (bloc public) |
| `USAGE_MARQUES.md` | Règles internes « Pokémon désigne les produits » ; mentions de non-affiliation ; droits des images fournisseurs | Mentions seulement |
| `CHECKLIST_LCD_ECOMMERCE.md` | 25 obligations, base légale, mise en œuvre, cas de recette liés | Non (interne) |
| `champs_a_remplir.yaml` | **Registre unique** des champs `{{…}}` : description, valeur proposée, statut, décideur | Non |
| `apercu/` | Textes publics rendus avec les valeurs proposées (fichiers générés, à lire par le juriste) | Non |
| `outils/` | Vérificateur (`verifier_legal_ops.py`), rendu (`rendre_textes.py`), tests | Non |

La FAQ client (`docs/07-ops/FAQ_CLIENTS.md`) suit les mêmes règles : bloc public, champs du registre.

## Structure commune des documents

1. Bandeau « À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION », version, sources.
2. **Bloc public** entre les commentaires HTML `TEXTE_PUBLIC:DEBUT` et `TEXTE_PUBLIC:FIN` : seul ce bloc est copié sur le site.
3. Notes internes (juriste, règles internes) : jamais publiées.
4. Section finale « Validation humaine requise ».

## Les champs `{{…}}`

- Chaque champ est déclaré **une fois** dans `champs_a_remplir.yaml` avec un statut : `a_remplir` (fait à obtenir), `a_valider` (valeur proposée), `valide`.
- Pour changer une valeur : modifier le YAML, puis régénérer les aperçus. Ne jamais remplacer un champ à la main dans un document.
- Les variables entre crochets (`[NUMERO_COMMANDE]`) sont propres à un cas (modèles d'emails SAV) et ne sont pas dans le registre.

## Commandes

```bash
python docs/04-legal/outils/verifier_legal_ops.py                 # contrôles de cohérence (04-legal + 07-ops)
python docs/04-legal/outils/rendre_textes.py                      # régénère apercu/ (valeurs proposées signalées)
python docs/04-legal/outils/rendre_textes.py --publication --sortie /tmp/textes   # refuse tant qu'un champ n'est pas « valide »
python -m pytest -q docs/04-legal/outils
```

Le mode `--publication` est le seul à produire des textes sans marque « à valider » : il échoue (code 1) tant qu'un champ utilisé n'a pas le statut `valide`. C'est la traduction du principe « tout en simulation par défaut » (SPEC §0.6).

## Sources juridiques

Consultées le **4.10.2026**. Les domaines officiels (admin.ch, fedlex, kmu, help.shopify.com, post.ch) sont **bloqués par le proxy de sortie** de l'environnement de build : les contenus ont été vérifiés par **index de recherche** (titres et extraits), pages non ouvertes. Statut de chaque source : « indexée, page non ouverte ». À relire à la source avant la validation finale.

| Réf. | Source | URL | Utilisée pour |
|---|---|---|---|
| L1 | Portail PME — obligations légales e-commerce (= BP [S11]) | https://www.kmu.admin.ch/fr/obligations-legales-les-lois-suisses-et-europeennes-sur-le-e-commerce | LCD art. 3 al. 1 let. s, pas de droit de rétractation |
| L2 | Guide e-commerce de la Confédération — obligations du vendeur | https://www.e-commerce-guide.admin.ch/ecommerce/fr/home/vertragsabschluss/pflichten.html | Email obligatoire (un formulaire ne suffit pas), étapes techniques |
| L3 | Loi contre la concurrence déloyale (LCD, RS 241) | https://www.fedlex.admin.ch/eli/cc/1988/223_223_223/fr | Art. 3 al. 1 let. d, o, s ; art. 8 |
| L4 | Code des obligations (CO, RS 220) ; art. 210 indexé : https://www.swissrights.ch/gesetze/Artikel-210-OR-2025-FR.php | https://www.fedlex.admin.ch/eli/cc/27/317_321_377/fr | Art. 185, 197 ss, 201, 205-206, 210 (2 ans, clause abrégée nulle pour un consommateur) |
| L5 | Loi sur la protection des données (LPD, RS 235.1), en vigueur depuis le 1.9.2023 ; https://www.kmu.admin.ch/fr/nouvelle-loi-sur-la-protection-des-donnees-nlpd | https://www.fedlex.admin.ch/eli/cc/2022/491/fr | Art. 6, 9, 12, 16-17, 19, 21, 24, 25, 28 |
| L6 | Ordonnance sur la protection des données (OPDo, RS 235.11) ; PFPDT, droit d'accès : https://www.edoeb.admin.ch/fr/droit-dacces | https://www.fedlex.admin.ch/eli/cc/2022/568/fr | Réponse au droit d'accès en 30 jours, gratuité |
| L7 | Swiss-US Data Privacy Framework, effectif le 15.9.2024 (États-Unis ajoutés à l'annexe 1 OPDo pour les entreprises certifiées) | https://www.edoeb.admin.ch/fr/nsb?id=102054 | Transferts vers des prestataires américains |
| L8 | Loi sur les télécommunications (LTC), art. 45c ; analyse : https://www.sidd.swiss/fr/perspectives/bandeau-de-cookies-en-suisse-configuration-conforme-a-la-nlpd-modeles/ | https://www.fedlex.admin.ch/eli/cc/1997/2187_2187_2187/fr | Cookies : information et refus |
| L9 | Ordonnance sur l'indication des prix (OIP, RS 942.211) ; SECO : https://www.seco.admin.ch/fr/brochures-oip ; auto-comparaison : https://handelsverband.swiss/fr/news/indication-des-prix-simplification-des-dispositions-relatives-a-lautocomparaison/ | https://www.fedlex.admin.ch/eli/cc/1978/2081_2081_2081/fr | Prix en CHF taxes comprises, frais, prix barrés |
| L10 | Loi sur la TVA (LTVA), art. 27 ; index : https://www.lexfind.ch/tolv/233939/fr | https://www.fedlex.admin.ch/eli/cc/2009/615/fr | Interdiction d'afficher la TVA sans être inscrit |
| L11 | Code de procédure civile (CPC), art. 32 et 35 ; https://app.zpo-cpc.ch/fr/articles/32/contrats-conclus-avec-des-consommateurs | https://www.fedlex.admin.ch/eli/cc/2010/262/fr | For du consommateur |
| L12 | OFCOM — Quand les envois en masse sont-ils autorisés ? | https://www.bakom.admin.ch/fr/quand-les-envois-en-masse-sont-ils-autorises | Consentement, clients existants, désinscription |
| L13 | Ordonnance sur la sécurité des jouets (OSJo) ; OSAV : https://www.blv.admin.ch/fr/jouets | https://www.fedlex.admin.ch/eli/cc/2012/573/fr | Avertissements visibles avant l'achat en ligne ; langues **non vérifiées** |
| L14 | Shopify — TWINT et éligibilité (= BP [S10]) | https://help.shopify.com/fr/manual/payments/shopify-payments/local-payment-methods/twint | Conditions TWINT (Shopify Payments requis, CHF, type d'activité éligible) |
| L15 | Révision du CO sur les défauts de construction, en vigueur le 1.1.2026 | https://www.admin.ch/fr/newnsb/VsBnhpbj-jkYJm1JmZZA8 | Avis de 60 jours limité aux constructions : **non applicable** à nos produits |
| L16 | La Poste — CG « Prestations du service postal » | https://www.post.ch/-/media/post/agb/agb-postdienstleistungen-pk.pdf?la=fr | Réclamations colis : délais et plafonds **non vérifiés**, à lire dans le contrat retenu |
| L17 | FRC — garantie légale ; produit qui ne convient pas | https://www.frc.ch/dossiers/la-garantie-legale-pour-les-defauts | Lecture consommateur de la garantie et du retour |
| L18 | Droit des marques : épuisement international et usage par un revendeur ; LPM : https://www.fedlex.admin.ch/eli/cc/1993/274_274_274/fr | https://www.promarca.ch/fr/aenean-leo-ligula-porttitor-copy/ | Revente de produits authentiques ; pas de fausse impression de lien |

## Validation humaine requise

- [ ] Propriétaire : mandater le juriste (B12/BL-057) et lui transmettre ce dossier (lire en priorité `apercu/` et les notes « juriste » de chaque document).
- [ ] Juriste : relire chaque bloc public et trancher les notes ; dater la version validée (`DATE_VERSION`).
- [ ] Propriétaire : passer chaque champ de `champs_a_remplir.yaml` au statut `valide` (identité, contrats, délais), puis lancer le rendu `--publication`.
- [ ] Propriétaire ou agent avec accès web : relire à la source les références L1 à L18 marquées « indexée, page non ouverte ».
