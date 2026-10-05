# Dossier professionnel B2B — {{NOM_BOUTIQUE}}

> Document commun envoyé à chaque fournisseur avec la demande de devis (BP §13 « Préparer un dossier professionnel commun »). Version 1 du 4.10.2026, **à compléter** par la propriétaire : tous les champs `{{…}}`.
> Règle : aucune information inventée. Tant qu'un champ n'est pas connu, écrire « en cours » plutôt qu'une valeur supposée. Un fournisseur qui découvre une information fausse ferme la porte.
> Envoi : version PDF d'une à deux pages, générée à partir de la partie « À envoyer » ci-dessous. La partie « Notes internes » **n'est jamais envoyée**.

---

## Partie À ENVOYER

### 1. L'entreprise

| Rubrique | Valeur |
|---|---|
| Nom commercial | {{NOM_BOUTIQUE}} |
| Raison sociale et forme juridique | {{RAISON_SOCIALE}} — {{FORME_JURIDIQUE}} (raison individuelle / Sàrl / …) |
| Numéro IDE | {{IDE : CHE-xxx.xxx.xxx}} ou « inscription en cours, numéro communiqué dès réception » |
| Inscription au registre du commerce | {{oui, canton de … / non : inscription volontaire en cours / non requise}} |
| Statut TVA | {{assujetti, n° CHE-xxx.xxx.xxx TVA}} ou « non assujetti à ce jour ; examen en cours avec notre fiduciaire » |
| Siège | {{ADRESSE_SIÈGE}}, {{NPA}} {{LOCALITÉ}}, Suisse |
| Adresse de livraison des marchandises | {{ADRESSE_LIVRAISON}} (Genève, par hypothèse du BP) |
| Contact commercial | {{PRÉNOM NOM de la responsable}} — {{EMAIL_DEDIE}} — {{TÉLÉPHONE}} |
| Site | {{URL du site}} (en préparation) |
| Responsable légale | {{PRÉNOM NOM}}, {{fonction}} |

### 2. Activité

- **Ce que nous faisons :** boutique en ligne de produits Pokémon JCC **officiels, scellés, en français**, avec quelques accessoires. Ventes **en Suisse uniquement**, expédiées depuis notre stock local à {{ville}}.
- **Ce que nous ne faisons pas :** pas de revente à d'autres professionnels, pas de vente sur des marketplaces étrangères, pas de cartes à l'unité ni de grading au lancement, pas de produits non officiels.
- **Clientèle visée :** collectionneurs francophones, parents et acheteurs de cadeaux, joueurs (Suisse romande d'abord).
- **Canal :** site marchand propre (Shopify), paiement carte et TWINT, livraison par transporteur suisse avec suivi.
- **Engagements envers nos fournisseurs :**
  - respect des dates de sortie et des embargos ;
  - aucune précommande ouverte sans allocation ferme confirmée par écrit ;
  - stock affiché = stock réellement détenu ;
  - photos et textes utilisés seulement avec votre accord ;
  - conservation des justificatifs d'origine pour la traçabilité.

### 3. Volumes prévisionnels (hypothèses de démarrage, non contractuelles)

| Élément | Valeur indicative | Nature |
|---|---|---|
| Première commande (assortiment pilote) | Environ **3 000 CHF** rendu Suisse, répartis sur **8 à 12 références achetées en stock** (catalogue de 15 à 25 références, les autres en alerte de réassort ou en précommande sur allocation ferme) | Budget de lancement décidé ; montant final selon vos conditions |
| Réassorts | Hebdomadaires ou bimensuels selon les ventes réelles | Pas d'engagement de volume à ce stade |
| Croissance visée après le pilote | Réassorts mensuels de plusieurs milliers de francs si les ventes le confirment | Hypothèse de plan, non garantie |
| Mode de commande souhaité | Fichier de prix et de stock régulier, commande par email ou électronique (EDI/API si disponible) | Voir la demande technique |

> Ces chiffres sont des hypothèses de gestion. Ils ne constituent ni une commande ni une promesse d'achat.

### 4. Références et documents disponibles sur demande

| Document | Disponibilité |
|---|---|
| Extrait du registre du commerce ou attestation IDE | {{à joindre dès réception}} |
| Attestation d'assujettissement TVA (si assujetti) | {{à joindre / non applicable}} |
| Pièce d'identité de la responsable (KYC) | Fournie via votre formulaire sécurisé uniquement, pas par email |
| Coordonnées bancaires (IBAN au nom de l'entreprise) | {{après ouverture du compte}} |
| Références commerciales | Nouvelle activité : pas encore de références fournisseurs. Contact de notre fiduciaire possible sur demande : {{FIDUCIAIRE}} |

### 5. Ce que nous vous demandons

La liste détaillée figure dans notre email (conditions commerciales, demande technique et exemple de fichier de prix et de stock). Nous joignons notre **panier pilote** : la même liste est envoyée à chaque fournisseur interrogé, pour comparer des offres équivalentes.

---

## Partie NOTES INTERNES (ne jamais envoyer)

### A. Champs à compléter et source de l'information

| Champ | Qui le fournit | Quand | Bloque |
|---|---|---|---|
| Raison sociale, forme juridique | Propriétaire + fiduciaire (B07) | J7 | Version définitive |
| IDE, registre du commerce | Propriétaire (B09) | J10 | Comptes revendeurs chez la plupart des fournisseurs |
| Statut TVA | Fiduciaire (B10) | J10 | Facturation HT ou TTC, prix |
| Adresse de livraison | Propriétaire | J2 | Devis de port |
| Contact commercial et téléphone | Propriétaire | J2 | Envoi |
| Nom de boutique, URL | Propriétaire (C06), agent 06 | J7-J8 | Crédibilité ; « en préparation » accepté en version provisoire |

### B. Version provisoire

Si l'IDE n'est pas encore attribué à J3, envoyer la version avec « inscription en cours ». Le BP §2 prévoit déjà la question « accès sans numéro TVA si non assujetti » pour OtakuWorld. Ne jamais indiquer un numéro supposé.

### C. Ce qui ne doit jamais apparaître dans ce dossier

Marges visées, prix de vente prévus, budget total de 8 000 CHF, comparaison entre fournisseurs, noms des autres fournisseurs contactés, données personnelles autres que le contact commercial.

### D. Brief pour la fiduciaire (envoyé avec la demande d'offre, BL-008)

> Nous lançons une boutique en ligne de produits Pokémon JCC scellés en français, vendus en Suisse uniquement, avec un stock à Genève importé en partie de France. Nous cherchons une fiduciaire pour :
> 1. choisir la forme d'exploitation, en tenant compte de l'ensemble des activités de la responsable ;
> 2. établir le statut TVA (méthode effective ou non assujettissement), avec un examen anticipé du seuil de 100 000 CHF ;
> 3. valider notre traitement des importations (TVA à l'importation, frais du transporteur, justificatifs) ;
> 4. tenir la comptabilité, avec la valorisation du stock au coût d'acquisition ;
> 5. le cas échéant, l'inscription au registre du commerce et l'affiliation AVS.
>
> Merci de nous indiquer vos honoraires (forfait annuel et prestations ponctuelles), vos délais et vos disponibilités pour un premier rendez-vous avant le {{J10}}.

## Validation humaine requise

- [ ] Remplir tous les champs `{{…}}` de la partie « À envoyer » (C02) ; à défaut, écrire « en cours ».
- [ ] Valider les engagements envers les fournisseurs (§2) et le tableau des volumes (§3).
- [ ] Choisir le canal de transmission des pièces KYC : jamais par email non chiffré.
- [ ] Relire le brief fiduciaire (§D) avant envoi.
