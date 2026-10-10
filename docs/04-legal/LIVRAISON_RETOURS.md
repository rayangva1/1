# Livraison et retours — {{NOM_BOUTIQUE}}

> **À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION**
> Brouillon v0.1 du 4.10.2026, rédigé par l'agent legal-ops. Ce texte n'est pas un avis juridique.
> Sources : BP §3 (frais de livraison comparés au coût réel), §7 (frais transparents, livraison Suisse uniquement, politique volontaire sans supprimer la garantie), §12 (workflow commande → livraison). Doit rester identique, sur le fond, aux CGV ch. 6, 8, 9 et 10.
> Aucun tarif ni délai de transporteur n'est inventé : `FRAIS_LIVRAISON`, `MODE_LIVRAISON` et `DELAI_ACHEMINEMENT` attendent le tarif écrit (BL-053).

<!-- TEXTE_PUBLIC:DEBUT -->
## Livraison et retours

### Où livrons-nous ?

Uniquement en Suisse. Nous ne livrons pas à l'étranger ni vers des services de réexpédition à l'étranger.

### Frais et modes de livraison

| Mode | Frais | Suivi |
|---|---|---|
| {{MODE_LIVRAISON}} | {{FRAIS_LIVRAISON}} | Oui, numéro envoyé par email |

Livraison offerte : {{SEUIL_PORT_OFFERT}}. Les frais exacts s'affichent dans le panier avant le paiement.

### Délais

- **Stock local** : remise au transporteur dans un délai de {{DELAI_EXPEDITION}} après la validation du paiement. Jours de dépôt des colis : {{JOURS_EXPEDITION}}.
- **Acheminement** : {{DELAI_ACHEMINEMENT}} après le dépôt, selon le transporteur ({{TRANSPORTEUR}}).
- **Précommande** : expédiée dès sa réception chez nous ; voir la page Précommandes ({{URL_PRECOMMANDES}}).
- **Commande mixte** (stock local et précommande) : deux envois séparés, frais de livraison facturés une seule fois.

Ces délais sont des estimations. En cas de retard connu, nous vous écrivons.

### Suivi de votre colis

Vous recevez un email avec le numéro de suivi au moment de l'expédition. Si le suivi n'évolue plus pendant {{SEUIL_COLIS_BLOQUE}}, écrivez-nous : nous ouvrons une recherche auprès du transporteur.

### À réception : vérifiez votre colis

1. L'emballage extérieur est-il intact ? S'il est visiblement abîmé, photographiez-le avant de l'ouvrir.
2. Pour chaque article : langue (FR), extension, format, quantité et scellé intact.
3. Un problème ? Écrivez-nous dans un délai de {{DELAI_SIGNALEMENT}} à {{EMAIL_SUPPORT}}, avec votre numéro de commande et des photos. Gardez l'emballage jusqu'à la fin du traitement.

### Colis perdu ou endommagé pendant le transport

Nous supportons le risque de transport jusqu'à la remise du colis à votre adresse. Si le transporteur confirme la perte, ou si un article est arrivé endommagé et que vous nous l'avez signalé dans le délai, nous vous proposons, au choix, un nouvel envoi de l'article (s'il est disponible) ou le remboursement intégral de l'article et des frais de livraison correspondants.

### Erreur de notre part

Mauvais article, mauvaise langue ou quantité incorrecte : nous vous envoyons le bon article à nos frais et vous fournissons une étiquette de retour prépayée pour l'article reçu par erreur.

### Défaut d'un produit

La garantie légale pour les défauts s'applique (art. 197 ss du Code des obligations), pendant deux ans à compter de la livraison. Écrivez-nous dès que vous constatez le défaut, avec photos. Nous vous proposons en priorité un remplacement par un article identique ; vos autres droits légaux (réduction du prix ou annulation de l'achat) restent entiers.

Le contenu aléatoire des boosters n'est pas un défaut : aucune carte précise, aucune rareté et aucune valeur ne sont garanties.

### Retour volontaire (changement d'avis)

Le droit suisse ne prévoit pas de droit général de rétractation pour les achats en ligne. Nous acceptons néanmoins, de manière volontaire, les retours aux conditions suivantes :

| Condition | Détail |
|---|---|
| Délai | {{DELAI_RETOUR_VOLONTAIRE}} |
| État | Article complet, dans son emballage d'origine, **non ouvert**, film et scellé intacts |
| Exclus | Article ouvert ou au film ou scellé endommagé ; accessoire sorti de son emballage ; article endommagé après la livraison |
| Démarche | Écrivez-nous d'abord à {{EMAIL_SUPPORT}} avec votre numéro de commande ; nous vous envoyons l'adresse de retour |
| Frais de retour | À votre charge ; envoi avec suivi recommandé (le colis voyage à vos risques) |
| Remboursement | Prix de l'article, dans un délai de {{DELAI_REMBOURSEMENT}} après réception et contrôle ; frais de livraison initiaux non remboursés |

Nous ne faisons pas d'échange direct : retournez l'article et passez une nouvelle commande.

### Colis non retiré ou refusé

Si un colis nous revient (non retiré, refusé, adresse incomplète ou erronée), nous vous contactons. Vous choisissez un nouvel envoi, aux frais de livraison en vigueur, ou le remboursement des articles, déduction faite des frais d'envoi et de retour effectivement supportés.

### Remboursements

Les remboursements sont faits sur le moyen de paiement utilisé lors de la commande. Le délai de crédit sur votre compte dépend ensuite de votre banque ou de votre émetteur de carte.

### Contact

{{EMAIL_SUPPORT}} — réponse dans un délai de {{DELAI_REPONSE_SUPPORT}}. Adresse de retour : communiquée par email avec les instructions de retour.
<!-- TEXTE_PUBLIC:FIN -->

## Notes internes (ne pas publier)

- L'adresse de retour (`ADRESSE_RETOURS`) n'est envoyée qu'avec les instructions de retour : elle peut correspondre au lieu de stockage, qui n'est pas publié.
- La politique « nous supportons le risque de transport » (CGV ch. 6.5) est un **choix** à valider (note J4 des CGV) : il transforme chaque perte en coût SAV. Les remboursements versés sont ensuite réclamés au transporteur selon ses conditions (délais et plafonds d'indemnisation à lire dans le contrat, B17). Si l'envoi d'une commande dépasse `SEUIL_ENVOI_SIGNATURE`, utiliser un envoi contre signature ou assuré (`docs/07-ops/SOP_PREPARATION_COLIS.md`).
- Une commande mixte coûte deux envois pour un seul port facturé ; le moteur doit compter deux fois le coût logistique L pour ces commandes (voir le rapport de l'agent legal-ops, écarts BP).
- Matrice de décision détaillée et modèles de réponses : `docs/07-ops/SOP_SAV_RETOURS.md`.

## Validation humaine requise

- [ ] Juriste : relire la page publique (cohérence avec les CGV ch. 6, 8, 9, 10).
- [ ] Propriétaire : remplir `MODE_LIVRAISON`, `FRAIS_LIVRAISON`, `DELAI_ACHEMINEMENT`, `TRANSPORTEUR` à partir du tarif écrit du transporteur (BL-053, B17).
- [ ] Propriétaire : décider `SEUIL_PORT_OFFERT` après simulation du moteur de prix (le port offert est un coût réel au panier).
- [ ] Propriétaire : valider la prise en charge du risque de transport et la politique de retour volontaire.
