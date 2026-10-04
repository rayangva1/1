# Packaging simple — note de chiffrage à faire

> BP §8 : « Packaging simple : sticker, carte de remerciement et repère d'identification des commandes, chiffrés au coût réel. »
> BP §3 : enveloppe « Emballages et matériel » = **300 CHF (provision)**, aucune offre prestataire confirmée.
> **Aucun prix n'est indiqué ici** : les montants viendront de devis réels (règle : pas de prix fournisseur inventé).

## 1. Fichiers prêts à imprimer

| Élément | Fichier (A / B) | Format fini | Fond perdu | Support conseillé |
|---|---|---|---|---|
| Sticker de fermeture | `a/sticker-rond-50mm.svg` · `b/…` | Ø 50 mm | 2 mm (fichier Ø 54 mm) | Vinyle ou papier adhésif blanc mat, découpe à la forme |
| Carte de remerciement recto | `a/carte-merci-a6-recto.svg` · `b/…` | A6 105 × 148 mm | 3 mm (fichier 111 × 154 mm) | Carte 300–350 g/m², mat, recto/verso quadri |
| Carte de remerciement verso | `a/carte-merci-a6-verso.svg` · `b/…` | A6 | 3 mm | idem |
| Repère d'identification commande | `a/repere-commande-70x37mm.svg` · `b/…` | 70 × 37 mm | aucun (imprimé au bureau) | Planche A4 de 24 étiquettes 70 × 37 mm, imprimante laser |

Chaque SVG contient un calque `DECOUPE_ne_pas_imprimer` (trait magenta) qui matérialise la coupe : **le supprimer ou le déclarer comme ligne de découpe** selon les consignes de l'imprimeur. Convertir les textes en contours (Inkscape : Chemin > Objet en chemin ; Illustrator : Vectoriser le texte) et exporter en PDF selon le profil demandé (souvent PDF/X-4, CMJN).

Les champs `{{SITE}}`, `{{EMAIL_SUPPORT}}`, `{{URL_RETOURS}}`, `{{DELAI_SIGNALEMENT}}`, `{{RAISON_SOCIALE}}`, `{{ADRESSE}}` sont à remplacer **après** validation du nom, des CGV et de la politique de retour (agent légal, docs/04-legal/).

## 2. Ce que fait chaque élément (et pourquoi c'est rentable)

| Élément | Rôle opérationnel | Effet attendu sur la contribution |
|---|---|---|
| Sticker | Ferme le sachet ou la boîte ; signale une ouverture | Moins de litiges « colis ouvert » |
| Carte merci (verso) | Check-list de réception, délai de signalement, conseils de protection | SAV plus rapide, moins de retours évitables |
| Repère commande | Relie colis ↔ commande ; cases « langue FR », « scellé », « quantité » cochées à la préparation | Moins d'erreurs de préparation (coût d'un renvoi) |

Le repère se remplit à la main ou s'imprime avec le numéro de commande ; la zone « code-barres » est réservée à l'outil d'étiquettes (aucun code-barres factice n'est dessiné).

## 3. Quantités à faire chiffrer

Base BP §1 : objectif de test 30 commandes payées en 60 jours (critère de test, pas une prévision). Demander **deux paliers** pour comparer le prix unitaire sans immobiliser de cash :

| Élément | Palier 1 | Palier 2 | Remarque |
|---|---|---|---|
| Sticker Ø 50 mm | 250 | 500 | 1 à 2 par colis |
| Carte A6 recto/verso | 100 | 250 | 1 par colis ; texte susceptible de changer (CGV) → petit tirage d'abord |
| Planches d'étiquettes 70 × 37 mm | 1 boîte | — | Fourniture de bureau, impression interne |

## 4. Questions à poser à chaque imprimeur

1. Prix total TTC livré en Suisse pour chaque palier, délai de production et de livraison.
2. BAT (bon à tirer) numérique inclus ? Épreuve physique possible et à quel coût ?
3. Fond perdu, marges de sécurité et profil couleur exigés (fichier PDF/X ?).
4. Découpe à la forme ronde : tracé de découpe fourni par nous ou par eux ?
5. Papier : grammage, finition mat, adhésif repositionnable ou permanent (sticker).
6. Frais de mise en route / de fichier ; frais de réimpression à l'identique.
7. Conditions de paiement (carte, facture) et de réclamation en cas de défaut.

## 5. Tableau de devis (à remplir)

| Imprimeur | Élément | Quantité | Prix total TTC livré CHF | Prix unitaire CHF | Délai | BAT | Date du devis | Lien / référence |
|---|---|---|---|---|---|---|---|---|
| | Sticker Ø 50 | 250 | | | | | | |
| | Sticker Ø 50 | 500 | | | | | | |
| | Carte A6 R/V | 100 | | | | | | |
| | Carte A6 R/V | 250 | | | | | | |
| | Étiquettes 70 × 37 | 1 boîte | | | | | | |

Pistes à consulter (imprimeries en ligne actives en Suisse, repérées par recherche web le 04.10.2026 — **non contactées, aucun tarif retenu**) :
- https://printeed.ch/impression/autocollants/
- https://www.printcesse.ch/autocollants
- https://fr.saxoprint.ch/materiel-de-pub/autocollants
- https://www.limprimeriegenerale.ch/suisse/autocollant
- Un imprimeur local à Genève (devis comparatif, retrait sur place possible).

## 6. Coût packaging par commande (à intégrer au moteur de prix)

Le coût réel par colis entre dans **L** (coût net de préparation/expédition) de la formule du prix plancher (BP §4) :

```
coût_packaging_par_commande = (prix_sticker × nb_stickers) + prix_carte + prix_etiquette
                              + part des emballages d'expédition (hors DA : boîte, calage, enveloppe)
```

- L'exemple BP §4 suppose **L = 3 CHF** (hypothèse) pour toute la préparation/expédition supportée : le packaging DA doit en rester une petite fraction. Si le devis rend le packaging significatif, supprimer d'abord la carte recto/verso imprimée (remplaçable par une impression interne N&B du verso).
- Le montant retenu est un paramètre du moteur (`logistics_cost`), validé par la responsable ; l'agent DA ne le fixe pas.

## Validation humaine requise

- [ ] Valider le nom et la direction **avant** d'imprimer quoi que ce soit.
- [ ] Valider les textes du verso avec les CGV et la politique de retour (délai de signalement, adresse, raison sociale).
- [ ] Demander au moins **deux devis réels** et remplir le tableau §5.
- [ ] Valider le BAT de chaque élément (contrôle physique recommandé pour la couleur d'accent).
- [ ] Reporter le coût par commande dans les paramètres logistiques du moteur de prix.
