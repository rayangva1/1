# 07-ops — procédures opérationnelles (SOP), recette et FAQ — {{NOM_BOUTIQUE}}

> Version v0.1 du 4.10.2026, rédigée par l'agent legal-ops. Toutes les SOP sont prêtes à imprimer (checklists, formulaires) et à tester à blanc par la propriétaire (BL-104).
> Source métier : BP du 4.10.2026, §5 (stock, précommandes), §7 (recette, paiement), §11 (agent 11 Opérations et SAV), §12 (workflows, tableau de bord, « ce qui demande encore une personne »).

## Contenu

| Fichier | Rôle | Utilisé par | Quand |
|---|---|---|---|
| `SOP_RECEPTION_STOCK.md` | Contrôle des quantités, scellés, langue FR, authenticité, dommages → stock endommagé, quarantaine, saisie du lot de coût ; bon de réception à imprimer ; modèle de réclamation | Propriétaire (physique), agents 11 et 05 | Chaque livraison fournisseur |
| `SOP_PREPARATION_COLIS.md` | Bon de préparation, scan GTIN, photo, emballage protégé, étiquette, dépôt, suivi ; fiche de session | Propriétaire (physique), agent 11 | Jours de dépôt |
| `SOP_SAV_RETOURS.md` | Matrice de 26 cas (colis perdu, endommagé, erreur, retour volontaire, garantie, fraude, litige, données…), qui décide, 14 modèles de réponse, journal SAV | Agent 11 (dans le mandat), propriétaire (escalades) | Quotidien |
| `SOP_INCIDENTS.md` | Gravités S1-S3, workflow BP §12 en 6 étapes, catalogue INC-01 à INC-16, stop-loss, violation de données | Tous les agents, propriétaire | Dès qu'un incident survient |
| `ROUTINES_PILOTAGE.md` | Étoile polaire, budget temps (6 à 10 h/semaine), digest quotidien, revue hebdomadaire et mensuelle, dictionnaire des indicateurs du tableau de bord | Agent 01, propriétaire, agent 07 (dashboard) | Jour, semaine, mois |
| `RECETTE_AVANT_OUVERTURE.md` | 76 cas de test (69 bloquants) : parcours mobile/ordinateur, stock simultané, remise, port gratuit, rupture pendant paiement, commande mixte, paiements, versements, emails, conformité | Agent 12 QA, propriétaire | Avant le gate G3 et le niveau 2, puis à chaque changement |
| `FAQ_CLIENTS.md` | FAQ publique (bloc public), alignée sur les CGV | Site | Après validation |

Les champs `{{…}}` sont définis dans `docs/04-legal/champs_a_remplir.yaml` (registre unique). Contrôle de cohérence de ce dossier et de `docs/04-legal/` :

```bash
python docs/04-legal/outils/verifier_legal_ops.py
python -m pytest -q docs/04-legal/outils
```

## Répartition des rôles (rappel du modèle d'opération)

| Qui | Fait quoi dans ces SOP |
|---|---|
| Flotte d'agents (dans le mandat écrit) | Prépare les listes, bons, étiquettes et réclamations ; répond aux clients selon la matrice ; détecte et confine les incidents ; produit le digest et les rapports |
| Propriétaire — physique | Réception, authenticité, colis, contrôle des retours, inventaire, photos et vidéos réelles |
| Propriétaire — décisions | Escalades SAV (au-delà du plafond, fraude, garantie refusée, litiges), levée des quarantaines d'authenticité, réarmement du stop-loss global, validation des réassorts |

## Validation humaine requise

- [ ] Propriétaire : tester à blanc la réception et la préparation d'un colis (BL-104, BL-105), puis valider les SOP.
- [ ] Propriétaire : valider les champs opérationnels du registre (jours de dépôt, délais, plafond de remboursement autonome, heure du digest).
- [ ] Agent gouvernance : confirmer que les seuils de stop-loss repris dans `SOP_INCIDENTS.md` §6 sont identiques à `STOP_LOSS.md`.
