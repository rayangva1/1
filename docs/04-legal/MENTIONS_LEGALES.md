# Mentions légales (impressum) — {{NOM_BOUTIQUE}}

> **À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION**
> Brouillon v0.1 du 4.10.2026, rédigé par l'agent legal-ops. Ce texte n'est pas un avis juridique.
> Base : LCD art. 3 al. 1 let. s ch. 1 (identité et adresse de contact, y compris l'adresse email, indiquées clairement et complètement) [L1][L2][L3]. Un formulaire de contact ne remplace pas une adresse email [L2].
> Tous les champs d'identité sont des placeholders : aucune donnée réelle n'est connue de l'agent.

<!-- TEXTE_PUBLIC:DEBUT -->
## Mentions légales

### Exploitant de la boutique

| | |
|---|---|
| Raison sociale | {{RAISON_SOCIALE}} |
| Forme juridique | {{FORME_JURIDIQUE}} |
| Personne responsable | {{NOM_RESPONSABLE}} |
| Adresse | {{ADRESSE_POSTALE}}, Suisse |
| Email | {{EMAIL_SUPPORT}} |
| Numéro IDE | {{NUMERO_IDE}} |
| Registre du commerce | {{INSCRIPTION_RC}} |
| TVA | {{MENTION_TVA}} |

Nous répondons aux emails dans un délai de {{DELAI_REPONSE_SUPPORT}}.

### Hébergement

La boutique est hébergée par {{HEBERGEUR}}.

### Boutique indépendante

{{NOM_BOUTIQUE}} est une boutique indépendante. Elle n'est ni affiliée, ni sponsorisée, ni approuvée par The Pokémon Company, Nintendo, Creatures Inc. ou GAME FREAK inc. Pokémon et les noms associés sont des marques de leurs titulaires respectifs ; nous les utilisons uniquement pour désigner les produits authentiques que nous revendons.

### Propriété intellectuelle

Les textes, photos propres, logo et éléments graphiques de {{NOM_BOUTIQUE}} nous appartiennent. Les visuels de produits fournis par des tiers sont utilisés avec leur autorisation. Toute reproduction sans accord écrit préalable est interdite.

### Liens vers d'autres sites

Nous ne contrôlons pas le contenu des sites tiers vers lesquels nous renvoyons et déclinons toute responsabilité à leur sujet.

### Documents de référence

- Conditions générales de vente : {{URL_CGV}}
- Livraison et retours : {{URL_RETOURS}}
- Précommandes : {{URL_PRECOMMANDES}}
- Déclaration de confidentialité : {{URL_CONFIDENTIALITE}}
- Cookies : {{URL_COOKIES}}
- Questions fréquentes : {{URL_FAQ}}
<!-- TEXTE_PUBLIC:FIN -->

## Notes pour le juriste (ne pas publier)

| # | Point | Question |
|---|---|---|
| M1 | Raison individuelle | La raison de commerce doit contenir le nom de famille de la titulaire (art. 945 CO) : vérifier que `RAISON_SOCIALE` respecte la règle et qu'elle est utilisée telle quelle dans les correspondances (art. 954a CO). |
| M2 | Numéro IDE et RC | Afficher l'IDE si l'entité n'est pas inscrite au RC ? Proposition : oui, il identifie l'entreprise sans ambiguïté. |
| M3 | Numéro de téléphone | Non exigé par la LCD ; non publié (support par email uniquement, choix du modèle d'opération). |
| M4 | Liste des titulaires de la marque | Formulation de la non-affiliation et des titulaires à confirmer (voir `USAGE_MARQUES.md`). |
| M5 | Adresse | Une case postale seule ne suffit probablement pas pour « l'adresse de contact » : vérifier si une adresse de domiciliation est acceptable si la propriétaire ne veut pas publier son adresse privée. |

## Validation humaine requise

- [ ] Propriétaire : fournir raison sociale, forme juridique, personne responsable, adresse, IDE, mention RC (B07, B09).
- [ ] Propriétaire : décider si son adresse privée peut être publiée ou s'il faut une adresse de domiciliation (M5).
- [ ] Fiduciaire : fournir la mention TVA exacte (B10).
- [ ] Juriste : valider la non-affiliation et les points M1 à M5.
