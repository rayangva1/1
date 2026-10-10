# Brief créateurs TCG suisses — collaboration locale limitée

> Propriétaire (build) : agent « site-contenu ». Exécution : agent 10 Acquisition (BL-134) avec l'agent 02 pour le suivi des contacts ; contrat et paiement : **propriétaire** (C15).
> Sources : BP §9 « Pour les créateurs TCG locaux, demander audience suisse, exemples, coût et droits d'utilisation ; mesurer un code ou lien dédié et intégrer produits offerts/commissions au CAC » ; BP §2 (« Créateurs TCG suisses : partenariats après validation du stock ») ; BP §9 J46-60 (« collaboration locale limitée ») ; écart EC-17 (inclus dans les 500 CHF du test) ; `PUBLICITE_TEST.md` ; `docs/04-legal/USAGE_MARQUES.md`.
> **Aucun créateur n'est nommé ici et aucun n'a été contacté.** Aucune audience, aucun tarif n'est supposé : tout se collecte auprès du créateur, preuves datées à l'appui.

## 1. Ce que l'on cherche

| Critère | Exigence | Preuve demandée |
|---|---|---|
| Audience suisse | Part de l'audience en Suisse, et en Suisse romande, **mesurée** | Capture des statistiques natives de la plateforme (pays, villes, âges), datée de moins de 30 jours |
| Audience adulte | Majorité de l'audience adulte ; si l'audience compte beaucoup de mineurs, pas de contenu promotionnel ciblé | Répartition par âge (capture) |
| Sujet | Contenus réguliers sur le JCC Pokémon, idéalement en français | 3 liens de contenus récents |
| Ton | Compatible avec `TON_EDITORIAL.md` : pas de promesse de rareté, pas d'« investissement », pas de fausse urgence, pas de vente de « mystery packs » pondérés | Lecture de 10 contenus récents par l'agent 10 |
| Transparence | Partenariats déjà signalés comme tels (« partenariat rémunéré », « produit offert ») | Exemples de contenus sponsorisés passés |
| Fiabilité | Livraison des contenus aux dates convenues ; pas de contenu retiré ou litigieux | Références si possible |

## 2. Trouver des créateurs (sans les inventer)

1. Recherche publique sur Instagram, TikTok et YouTube avec des mots-clés français (« cartes Pokémon », « JCC Pokémon », « ouverture booster ») et des lieux suisses (Genève, Lausanne, Fribourg, Neuchâtel, Valais).
2. Créateurs vus lors d'événements de clubs locaux (information donnée par la propriétaire, qui fréquente ces lieux).
3. Pour chaque piste : une ligne dans `docs/02-sourcing/TRACKER_CONTACTS.csv` (catégorie « créateur »), avec l'URL publique, la date de consultation et le contact **affiché pour les partenariats**.
4. Interdits : contacter un mineur ; écrire en masse ; utiliser une adresse privée trouvée ailleurs que dans la rubrique « contact professionnel » ; promettre une rémunération avant la décision de la propriétaire.

## 3. Message de premier contact (depuis la boîte dédiée, dans le mandat)

> Objet : Proposition de collaboration — boutique de cartes Pokémon en français à Genève
>
> Bonjour [prénom ou pseudonyme],
>
> Nous sommes {{NOM_BOUTIQUE}}, une boutique indépendante de produits JCC Pokémon en français, expédiés depuis Genève. Nous aimons votre façon de présenter [élément précis d'un contenu récent].
>
> Nous envisageons une collaboration limitée en [mois]. Avant toute proposition, pourriez-vous nous transmettre :
> 1. les statistiques de votre audience (pays, villes, âges), sous forme de capture datée ;
> 2. deux ou trois exemples de contenus sponsorisés déjà réalisés ;
> 3. vos conditions : tarifs, livrables, délais ;
> 4. les droits d'utilisation que vous accordez (republication sur nos comptes, en publicité, durée).
>
> Nous ne demandons aucun discours sur la rareté ou la valeur des cartes : notre ligne est l'information exacte sur les produits et le service.
>
> Meilleures salutations,
> {{NOM_BOUTIQUE}} — {{EMAIL_SUPPORT}}

Une seule relance après 7 jours, puis on classe la piste.

## 4. Grille d'évaluation (agent 10, puis dossier à la propriétaire)

| Critère | Poids | Note 0-3 | Commentaire |
|---|---:|---:|---|
| Part d'audience en Suisse romande (mesurée) | 3 | | |
| Audience adulte | 2 | | |
| Qualité et exactitude des contenus | 2 | | |
| Transparence des partenariats passés | 1 | | |
| Coût total rapporté au test (≤ part du budget prévue) | 2 | | |
| Droits d'utilisation obtenus | 1 | | |
| **Total pondéré / 33** | | | Seuil proposé pour présenter le dossier : 22 (**hypothèse**) |

## 5. Offre type et coût dans le CAC

| Élément | Proposition | Traitement |
|---|---|---|
| Rémunération | Montant fixe convenu **ou** commission sur ventes nettes attribuées, ou les deux, dans l'enveloppe du test | Comptée en dépense d'acquisition le jour de la publication (fixe) ou du paiement (commission) |
| Produit offert | Un produit en stock local, choisi par la boutique | Compté au **coût historique** (pas au prix public) dans la dépense d'acquisition ; sortie de stock journalisée |
| Plafond | Part de la collaboration dans les 500 CHF du test fixée par la propriétaire (proposition : 150 CHF au plus, **hypothèse**) | Le total test pub + créateur ne dépasse jamais 500 CHF |
| Attribution | Lien dédié `?utm_source=createur&utm_medium=partenariat&utm_campaign=crea-[pseudonyme]` ; code dédié seulement s'il est validé par le moteur (remise ⇒ contribution ≥ 12 % et ≥ 8 CHF par commande) | `campaign_id` = `crea-[pseudonyme]` dans le stop-loss pub |
| CAC créateur | (rémunération + produits offerts au coût + frais) ÷ commandes payées nettes attribuées | Même règle d'arrêt et même lecture G5 que la publicité |

**Exemple FICTIF** : 60 CHF de rémunération + un produit offert au coût historique de 40 CHF = 100 CHF ; 6 commandes payées attribuées, dont 1 remboursée ⇒ 5 nettes ⇒ CAC = 20.00 CHF. Avec une contribution avant acquisition de 19.33 CHF par commande : **ROUGE** (CAC > contribution), collaboration non reconduite.

## 6. Contrat minimal (à faire valider par la propriétaire ; juriste si montant ou droits importants)

- Parties, livrables (nombre et format de contenus), dates de publication, durée.
- Mention claire du partenariat dans chaque contenu (« partenariat rémunéré » ou « produit offert »).
- Contenu exact : nom des produits, langue, disponibilité **au moment de la publication** ; aucun prix si non relu sur la page publique le jour même ; aucune promesse de carte rare, de valeur ou de revente ; aucune fausse urgence ; aucun personnage ou logo de la licence hors de la photo du produit.
- Relecture de la boutique avant publication (factuelle uniquement).
- Droits d'utilisation : supports (comptes de la boutique, publicité), durée, territoire (Suisse), retrait sur demande.
- Rémunération, échéance (après publication), facture ; statut TVA du créateur à sa charge.
- Données : aucune liste d'abonnés transmise ; statistiques de résultats agrégées seulement.
- Résiliation si une clause de contenu n'est pas respectée ; retrait du contenu.

## 7. Suivi pendant la collaboration

| Moment | Action | Qui |
|---|---|---|
| Avant publication | Relecture factuelle, contrôle du lien et du code | A-10, A-12 |
| Jour J | Contrôle prix et stock publics ; produit promu en stock local | A-10 |
| J+1 à J+7 | Commandes attribuées nettes, CAC, stop-loss pub | A-10, moteur |
| J+7 | Bilan (même format que le rapport du test pub) | A-10 → propriétaire |

## Validation humaine requise

- [ ] Fixer la part des 500 CHF réservée à la collaboration (proposée : 150 CHF au plus).
- [ ] Valider le message de premier contact et le seuil de la grille (22/33, hypothèse).
- [ ] Choisir le créateur sur dossier et signer le contrat (C15) ; aucun agent ne s'engage.
- [ ] Décider si un code de réduction est accordé (seulement après calcul du moteur).
