# Questionnaire en ligne — version formulaire

> Version auto-administrée du `GUIDE_ENTRETIENS.md`, mêmes codes de questions (Q1…Q23) pour agréger les réponses.
> Outil : n'importe quel outil de formulaire créé au nom de l'entité (B04). Durée cible : **6 minutes**. Ne collecte **aucun email** : l'inscription aux alertes se fait sur la landing, séparément (double opt-in).
> Publication : BL-023 (J4). Diffusion : réseau de la propriétaire et lieux partenaires, sans message non sollicité de masse.

## Paramètres du formulaire

| Paramètre | Valeur |
|---|---|
| Titre | « Votre avis compte : une boutique Pokémon JCC en français, expédiée depuis la Suisse » |
| Connexion requise | Non |
| Collecte d'email ou d'adresse IP | **Désactivée** |
| Réponses modifiables après envoi | Non |
| Message de fin | « Merci ! Pour être prévenu(e) de l'ouverture, inscrivez-vous sur {{URL_LANDING}} (inscription séparée, désinscription en un clic). » |
| Export | CSV hebdomadaire vers la grille de synthèse (code `F01`, `F02`…) |
| Suppression | Réponses supprimées au plus tard le {{date J90}} |

## Page 1 — Information et consentement

**Texte affiché :**
> Nous préparons une boutique en ligne de produits Pokémon JCC officiels en français, expédiés depuis la Suisse. Il n'y a rien à acheter. Ce questionnaire est anonyme : il ne demande ni nom ni email. Vos réponses servent uniquement à choisir notre assortiment et notre service, et seront supprimées au plus tard le {{date J90}}. Contact : {{EMAIL_DEDIE}}.

| Code | Question | Type | Options | Obligatoire |
|---|---|---|---|---|
| C0 | J'ai lu l'information ci-dessus et j'accepte de répondre. J'ai 18 ans ou plus. | Case à cocher | Oui | Oui (sinon fin) |

## Page 2 — Vous

| Code | Question | Type | Options | Obligatoire |
|---|---|---|---|---|
| Q1 | Pour qui achetez-vous des produits Pokémon JCC ? | Choix multiples | Moi, pour collectionner · Moi, pour jouer · Un enfant · Des cadeaux · Autre | Oui |
| Q2 | Depuis combien de temps ? | Choix unique | Moins d'1 an · 1 à 3 ans · Plus de 3 ans | Oui |
| Q3 | En quelle langue achetez-vous vos produits ? | Choix unique | Français uniquement · Surtout français · Anglais · Japonais · Peu importe | Oui |
| Q3b | Si français : pourquoi ? | Texte court | — | Non |
| Q4 | Canton de résidence | Liste | 26 cantons + « Hors de Suisse » | Oui |

**Logique :** si Q4 = « Hors de Suisse », afficher « Merci ! Nous livrerons uniquement en Suisse au lancement » et terminer (BP : ventes en Suisse uniquement).

## Page 3 — Ce que vous achetez

| Code | Question | Type | Options | Obligatoire |
|---|---|---|---|---|
| Q5 | Décrivez votre dernier achat : produit, lieu, prix approximatif. | Texte long | — | Non |
| Q6 | Quels formats achetez-vous le plus ? Classez vos 3 préférés. | Classement (top 3) | Booster à l'unité · Tripack · Bundle (6 boosters) · Coffret Dresseur d'Élite (ETB) · Display (36 boosters) · Coffret / collection · Accessoires | Oui |
| Q7 | Quand achetez-vous une nouvelle extension ? | Choix unique | Dès la sortie (ou en précommande) · Dans le mois · Plus tard, selon les envies · Je n'achète pas les nouveautés | Oui |
| Q8 | Quels accessoires achetez-vous ? | Choix multiples | Protège-cartes · Classeurs · Deck box · Toploaders · Tapis de jeu · Aucun | Non |

## Page 4 — Budget et fréquence

| Code | Question | Type | Options | Obligatoire |
|---|---|---|---|---|
| Q9 | Montant moyen d'une commande | Choix unique | Moins de 30 CHF · 30-60 · 60-100 · 100-200 · Plus de 200 CHF | Oui |
| Q10 | Fréquence d'achat | Choix unique | Chaque semaine · Chaque mois · À chaque sortie · Quelques fois par an · Surtout pour les fêtes | Oui |
| Q11 | Budget mensuel approximatif | Choix unique | Moins de 20 CHF · 20-50 · 50-100 · 100-200 · Plus de 200 CHF | Non |
| Q12 | (Si Q1 inclut « Un enfant » ou « Des cadeaux ») Budget pour un cadeau | Choix unique | Moins de 20 CHF · 20-40 · 40-70 · 70-120 · Plus de 120 CHF | Non |

## Page 5 — Où et comment

| Code | Question | Type | Options | Obligatoire |
|---|---|---|---|---|
| Q13 | Où achetez-vous aujourd'hui ? | Choix multiples | Boutique physique · Boutique en ligne suisse · Site étranger · Grande surface · Marketplace · Particuliers | Oui |
| Q14 | Qu'est-ce qui vous ferait changer de boutique ? | Texte court | — | Non |
| Q15a | Délai de livraison acceptable | Choix unique | 1-2 jours ouvrés · 3-5 jours · Jusqu'à 10 jours · Peu importe | Oui |
| Q15b | Frais de port acceptables pour une commande de 50 CHF | Choix unique | 0 CHF · Jusqu'à 5 CHF · Jusqu'à 8 CHF · Plus de 8 CHF | Oui |
| Q15c | À partir de quel montant attendez-vous le port gratuit ? | Choix unique | 50 CHF · 80 CHF · 100 CHF · 150 CHF · Je ne m'attends pas au port gratuit | Non |
| Q16 | Moyen de paiement préféré | Choix unique | TWINT · Carte · Facture · Autre | Oui |

## Page 6 — Confiance

| Code | Question | Type | Options | Obligatoire |
|---|---|---|---|---|
| Q17 | Qu'est-ce qui vous inquiète quand vous achetez du scellé en ligne ? | Choix multiples | Contrefaçon · Produit déjà ouvert · Mauvaise langue · Emballage abîmé · Délai non tenu · Service injoignable · Rien | Oui |
| Q18 | Avez-vous déjà eu un mauvais achat ? Si oui, lequel ? | Texte court | — | Non |
| Q19 | Classez vos 3 éléments de confiance principaux | Classement (top 3) | Stock réellement disponible affiché · Photos réelles · Avis clients · Expédition depuis la Suisse · Retours clairs · Service client réactif · Prix stables | Oui |

## Page 7 — Précommandes et alertes

| Code | Question | Type | Options | Obligatoire |
|---|---|---|---|---|
| Q20a | Faites-vous des précommandes ? | Choix unique | Souvent · Parfois · Jamais | Oui |
| Q20b | Combien de temps êtes-vous prêt(e) à attendre une précommande ? | Choix unique | 1 semaine · 2-4 semaines · 1-3 mois · Je ne précommande pas | Non |
| Q21 | Une alerte « de retour en stock » vous serait-elle utile ? Par quel canal ? | Choix multiples | Email · Instagram · Autre · Pas utile | Oui |
| Q22 | Qu'est-ce qui manque aux boutiques que vous utilisez ? | Texte long | — | Non |

## Export et agrégation

- Chaque réponse reçoit un code `Fnn` et alimente la même grille de synthèse que les entretiens (`GUIDE_ENTRETIENS.md` §5).
- Les réponses textuelles ne sont jamais publiées telles quelles. Une citation dans un contenu exige un accord séparé et explicite.

## Validation humaine requise

- [ ] Valider les textes d'information et de fin (pages 1 et 7) : données personnelles (C04).
- [ ] Créer le compte de l'outil de formulaire au nom de l'entité (B04) ; l'agent 09 construit et publie ensuite le formulaire.
- [ ] Remplacer `{{EMAIL_DEDIE}}`, `{{URL_LANDING}}` et `{{date J90}}`.
