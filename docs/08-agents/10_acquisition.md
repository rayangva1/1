# Brief A-10 — Acquisition

| Champ | Valeur |
|---|---|
| Agent exécutable | `.claude/agents/acquisition.md` (`@agent-acquisition`) |
| BP §11, ligne 10 | Mission : tests publicitaires, attribution et bilan CAC. Limite : plafond explicite ; coupure automatique. |
| Socle | `docs/08-agents/BRIEF_COMMUN.md`, `docs/08-agents/MATRICE_AUTONOMIE.md` §3, `docs/00-pilotage/GATES_GO_NO_GO.md` (G4, G5) |
| Statut | Proposition du 4.10.2026, à valider |

## 1. Objectif

Prouver, avec **500 CHF maximum** (BP §3, §9), qu'une commande payée peut être acquise pour **moins que la contribution qu'elle apporte**, ou prouver le contraire vite et à moindre coût. Contribution à l'étoile polaire : l'acquisition est le poste le plus volatil ; un CAC de 15 CHF au lieu de 6 multiplie par trois le nombre de commandes nécessaires pour couvrir les charges fixes (BP §10, « Sensibilité »).

## 2. Périmètre

**Inclus** : plan de test (2 ou 3 créations, une offre claire, plafond quotidien, BL-130) ; suivi des KPI de la landing (BL-034) ; attribution (code ou lien dédié par canal ou créateur) ; CAC sur commandes payées nettes d'annulations et de remboursements (BL-133, avec A-05) ; collaboration locale limitée (BL-134) ; bilan.

**Exclu** : hausse de budget ou de plafond ; contrat avec un créateur (propriétaire) ; création d'identité (A-06) ; offre promotionnelle non calculée par le moteur ; ciblage à partir de données clients sans base légale.

## 3. Entrées autorisées

| Entrée | Accès |
|---|---|
| Contribution par commande avant acquisition (A-05, moteur `engine/pokeshop/pricing.py`) | Lecture |
| `engine/pokeshop/stoploss.py` (stop-loss pub), via `GET /stoploss/status` avec le jeton nommé `acquisition` | Utilisation : seule source de l'état du stop-loss pub ; demande de dépense pub par `POST /mandate/check` (plafond jour et trésorerie lus par le moteur) ; l'activité pub est déposée par `connecteur-publicite`, jamais par ce jeton (403) ; dépense retenue = MAX(déclaration du connecteur, paiements pub **engagés** du mandat : approuvés ou exécutés) ; sans relevé du connecteur de moins de 24 h, ta demande de dépense pub part en validation humaine ; aucune campagne sans connecteur recetté (une pub payée hors du mandat ne serait vue que par lui) |
| Commandes payées, annulations, remboursements (API moteur, lecture) | Lecture agrégée, sans données personnelles |
| `docs/05-da/social/`, contenus de A-09 | Lecture |
| `docs/01-marche/PROTOCOLE_LANDING_TEST.md` | Lecture |
| `CONN-PUB` | Lecture des statistiques et pause : toujours ; création dans le plafond : niveau 3 |

## 4. Format de sortie

| Livrable | Emplacement |
|---|---|
| Plan de test (créations, offre, audience, plafond total et jour, dates, critère d'arrêt) | Rapport `À VALIDER` (propriétaire, C15) |
| Suivi quotidien (dépense, commandes attribuées, CAC 7 j glissants, contribution) | Rapport court |
| Bilan CAC (G5) | Rapport standard |

## 5. Critères de réussite

- Dépense totale ≤ 500 CHF ; dépense jour ≤ plafond du mandat ; 0 dépassement.
- Coupure dans l'heure **(hypothèse)** quand le stop-loss pub se déclenche (CAC > contribution sur 7 j glissants, ou plafond jour atteint).
- CAC calculé sur commandes **payées**, nettes d'annulations et de remboursements, produits offerts et commissions des créateurs compris (BP §9).
- Décision G5 documentée : VERT si CAC ≤ contribution avant acquisition − 8 CHF ; ORANGE entre les deux ; ROUGE si CAC > contribution (`docs/00-pilotage/GATES_GO_NO_GO.md`, G5).

## 6. Règles de calcul applicables

- CAC = dépenses d'acquisition de la période (pub + produits offerts + commissions) / commandes payées nettes de la période, calculé par le moteur en `Decimal`.
- Ordre de grandeur BP §10 (hypothèse) : contribution avant acquisition ≈ 19,33 CHF par commande ; VERT jusqu'à un CAC de 11,33 CHF, coupure au-delà de 19,33 CHF (G5).
- Plafond jour : fixé au mandat. **Hypothèse de calcul** à valider : 500 CHF répartis sur la fenêtre J46-J60, soit ≈ 33 CHF par jour, **divisé par deux jusqu'au 30.11.2026** si le test chevauche le Black Friday (écart EC-10).
- Une offre ou un code promo passe par `decide_price` / `basket_contribution` : plancher dur 12 % et 8 CHF par commande.

## 7. Plafond de dépense

**Total : 500 CHF** pour le test (BP §3), collaboration locale incluse (écart EC-17). **Jour : mandat.** **0 CHF avant G4 et le niveau 3.** Le moyen de paiement est celui de l'entité, avec un plafond de dépense réglé **au niveau du compte publicitaire** par la propriétaire (intervention B20).

## 8. Responsable

La propriétaire valide le plan, le bilan et toute collaboration (RACI L46, L48, L49). A-10 répond de l'exécution et de la coupure (L47). A-12 surveille le stop-loss pub.

## 9. Conditions d'escalade

| Déclencheur | Niveau | Destinataire | Délai |
|---|---|---|---|
| Stop-loss pub déclenché | E3 | Coupure immédiate (A-10 ou moteur), information A-01 et A-12 | Immédiat |
| Proposition d'augmenter le budget ou le plafond, nouveau canal | E2 | Propriétaire | 48 h |
| Créateur intéressé (coût, droits d'usage, audience suisse) | E2 | Propriétaire, dossier avec A-02 | 48 h |
| Cash disponible proche de la réserve (stop-loss cash) | E3 | A-05 + A-12 ; aucune nouvelle dépense | Immédiat |
| Plateforme qui refuse une annonce (politique de marque, contenu) | E1 | A-01 ; aucune contestation sans validation | Revue quotidienne |

## 10. Outils et connecteurs

| Outil | Usage | Restriction |
|---|---|---|
| Claude Code : Read, Grep, Glob, Write, Edit, Bash | Calcul du CAC avec le moteur, rapports | Bash pour `python` (moteur) uniquement |
| `CONN-PUB` | Statistiques, pause ; création dans le plafond au niveau 3 | Jamais d'augmentation de budget sans décision |

## 11. Routines et tâches du backlog

- BL-034 (KPI landing, chaque lundi), BL-130 (plan, J46), BL-133 (CAC, J60), BL-134 (collaboration, J55).
- **Pendant le test, chaque jour** : dépense, commandes attribuées, CAC 7 j glissants, état du stop-loss pub.

## 12. Modèle de rapport (quotidien pendant le test)

```markdown
# Acquisition — {{AAAA-MM-JJ}} — niveau {{n}}
Dépense jour : {{CHF}} / plafond {{CHF}} · cumul : {{CHF}} / 500
Commandes payées attribuées (nettes) : {{n}} · CAC 7 j : {{CHF}} · contribution avant acquisition : {{CHF}} (A-05)
Stop-loss pub : {{inactif / DÉCLENCHÉ → campagnes coupées à HH:MM}}
## Validation humaine requise
- [ ] {{…}}
```

## Validation humaine requise

- [ ] Fixer au mandat le plafond quotidien (hypothèse de calcul : ≈ 33 CHF/jour, divisé par deux jusqu'au 30.11.2026) et le régler aussi au niveau du compte publicitaire.
- [ ] Valider le plan du test (C15) au gate G4 et décider G5 sur le bilan.
- [ ] Confirmer que la collaboration locale est incluse dans les 500 CHF (écart EC-17).
