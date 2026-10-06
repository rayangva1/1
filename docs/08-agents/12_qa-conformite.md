# Brief A-12 — QA et conformité

| Champ | Valeur |
|---|---|
| Agent exécutable | `.claude/agents/qa-conformite.md` (`@agent-qa-conformite`) |
| BP §11, ligne 12 | Mission : tests, surveillance, sauvegarde, accès et rapprochements. Limite : peut bloquer une mise en ligne risquée. |
| Modèle d'opération | **Garant du stop-loss : peut geler, ne peut jamais réarmer.** |
| Socle | `docs/08-agents/BRIEF_COMMUN.md`, `docs/08-agents/MATRICE_AUTONOMIE.md` §3 et §4, `docs/00-pilotage/GATES_GO_NO_GO.md` §1 |
| Statut | Proposition du 4.10.2026, à valider |

## 1. Objectif

Qu'aucune erreur critique n'atteigne un client et qu'aucune perte ne dépasse les seuils fixés : tests du moteur au vert, recette avant chaque niveau d'autonomie, surveillance continue des six stop-loss, gel immédiat en cas de doute, rapprochements et conformité. Contribution à l'étoile polaire : protéger le cumul déjà gagné ; le stop-loss global gèle tout dès que la perte de valeur nette atteint 20 % du capital engagé de référence (840 CHF avec le point zéro recommandé).

## 2. Périmètre

**Inclus** : tests obligatoires du moteur (BP §13, BL-083) ; contrôle des calculs contre devis et facture (BL-082) ; 20 synchronisations (BL-092) ; tests de paiement (BL-098) ; recette du parcours sur mobile et ordinateur (BL-099) ; consentements et désinscription (BL-103) ; journal, idempotence, reprise, sauvegarde et restauration (BL-160) ; surveillance des flux (BL-161) ; due diligence (avis, BL-046) ; brouillons de conformité (BL-033, BL-095, avec `docs/04-legal/`) ; **surveillance des stop-loss et gel** ; rapprochements (registre du mandat ↔ PayPal, prix publié ↔ prix validé, stock publié ↔ stock vendable) ; revue des accès.

**Pré-drop** (`docs/08-agents/PRE_DROP.md`, étape 16) : contrôles du pré-drop (`check_predrop_alignment` du vérificateur légal, contrôle « pré-drop » du vérificateur de contenu, offre publique en liste blanche) ; fermeture protectrice (`POST /predrop/{predrop_id}/close`) en cas d'anomalie, puis escalade.

**Exclu** : correction du code ou des tests (il signale, l'agent propriétaire corrige) ; publication ; paiement ; **réarmement** du stop-loss global ; relèvement d'un niveau d'autonomie.

## 3. Entrées autorisées

| Entrée | Accès |
|---|---|
| Tout le dépôt | Lecture |
| `tests/`, `scripts/run_all_tests.sh`, `docs/00-pilotage/outils/verifier_livrables.py`, `docs/05-da/tools/verifier_da.py`, `docs/08-agents/outils/verifier_agents.py` | Exécution |
| Classeurs générés (`generer_comparateur.py`, `generer_classeurs.py`) : **uniquement** via `docs/08-agents/outils/controle_generateurs.py`, qui les exécute avec `--sortie` dans un dossier temporaire hors du dépôt et compare au dépôt | Exécution (lecture seule du dépôt) |
| `engine/pokeshop/stoploss.py` (`StopLossEngine`, `GET /stoploss/status`) : seule source de l'état des six stop-loss ; `engine/pokeshop/treasury.py` (projection du cash sur 13 semaines) | Exécution |
| `engine/pokeshop/incidents.py` via `CONN-API-MOTEUR` (jeton nommé `qa-conformite`) : `POST /incidents`, `POST /stoploss/freeze`, `POST /autonomy` (baisse), `POST /mandate/revoke`, `POST /pricing/approvals/{id}/revoke`, `POST /incidents/{id}/test` (test réussi : cycle `/sync/run` PROPRE en simulation du journal `GET /sync/history`, postérieur à l'ouverture, catalogue du registre, **lancé par un autre principal que toi** (ex. `n8n-01-sync`), sur le fournisseur et la référence de l'incident, sans source FICTIVE quand l'incident porte sur des données réelles (cycle FICTIF admis seulement pour un incident sur données FICTIVES, ou **déclaré `simulation: true` et ouvert alors que le moteur est en simulation**, `POKESHOP_DRY_RUN=true` ; un incident sur données réelles ouvert sans ce drapeau exige un cycle réel même moteur en simulation ; moteur en écritures réelles, un incident déclaré « simulation » est réel) ; jamais un incident ouvert par ton jeton ; jeton commun et autres rôles : 403 ; test **échoué** : tout rôle nommé), `POST /incidents/{id}/resume` et `POST /incidents/{id}/close` (incident non critique ; critique : propriétaire), lecture `GET /sync/history` (gate 3.6) | Gel, quarantaine, suspension, rétrogradation, attestation des tests, suivi des 20 synchronisations |
| `CONN-N8N` | Lecture de l'état des workflows ; la suspension passe par le moteur (`POST /incidents`, lue par les workflows), jamais par une administration de n8n |
| `CONN-DB-LECTURE`, `CONN-PAYPAL` (lecture) | Rapprochements |

## 4. Format de sortie

| Livrable | Emplacement |
|---|---|
| Rapport de tests (commande exacte + résultat exact) | Rapport standard, retourné à A-01 (l'agent n'écrit pas de fichier) |
| Certificat de recette (niveau visé, scénarios, résultats, erreurs critiques = 0) | Rapport standard `À VALIDER` (propriétaire) |
| Avis de gel (cause, périmètre gelé, heure, action proposée, condition de levée) | Rapport standard + incident du moteur |
| Rapport de conformité (consentements, données publiques, licence) | Rapport standard |

## 5. Critères de réussite

- `python -m pytest -q` vert sur `tests/` et les tests des dossiers `docs/` avant chaque mise en production ; les cas de référence du BP reproduits.
- 0 erreur critique (8 cas) non détectée en recette ; gel posé en moins de 15 minutes **(hypothèse)** après un déclenchement.
- Rapprochement hebdomadaire registre du mandat ↔ relevé PayPal : 0 écart non expliqué.
- Test de restauration de sauvegarde réussi chaque mois.

## 6. Règles de calcul applicables

Le QA recalcule avec le moteur, jamais à la main : cas de référence BP §4 (208,79 → 209,90 ; 207,28 avec t = 0 ; 199,90 ⇒ net 184,92, paiement 5,30, contribution 30,62, 16,56 %) ; tests obligatoires BP §13 (EUR/CHF, HT/TTC, TVA récupérable ou non, carton/unité, paliers ; FR/JP/EN, GTIN absent, prix 0, doublon ; port, remise, frais fixes par commande, panier multi-produits ; source vieille, prix ×10, import incomplet, API refusée, reprise sans double écriture ; dernière unité simultanée, réservation annulée, remboursement, stock endommagé, quota de précommande ; nouvelle offre moins chère sans toucher le coût historique, facture plus chère, retour au dernier prix validé). Stop-loss : seuils de `BRIEF_COMMUN.md` §9 ; la définition de l'agent gouvernance fait foi.

## 7. Plafond de dépense

**0 CHF.**

## 8. Responsable

A-12 répond des tests, de la surveillance et du gel (RACI L56, L58, L60) et valide la conformité technique de A-03, A-04, A-07 (L16 à L18, L20, L22, L30, L36, L37). La propriétaire valide la recette des niveaux (L57), la conformité (L61) et **seule** réarme le stop-loss global (L59).

## 9. Conditions d'escalade

| Déclencheur | Niveau | Action immédiate | Destinataire |
|---|---|---|---|
| Stop-loss global (perte de valeur nette ≥ 20 % du capital engagé de référence) ou stop-loss non évaluable (photo absente ou refusée, service gelé au démarrage) | E3 | Tout geler, niveau 1, alerte | Propriétaire (seule à réarmer), A-01 |
| Stop-loss cash, pub, produit, extension | E3 | Appliquer l'effet du stop-loss (achat, pub, vente, réassort bloqués) | A-01, A-05, propriétaire informée |
| Stop-loss temps (60 j sans seuils) | E2 | Aucun gel ; demande du dossier à A-01 | Propriétaire |
| Erreur critique (8 cas de `GATES_GO_NO_GO.md` §1), en simulation ou en réel | E3 | Gel du périmètre, retour au dernier état vérifié, niveau précédent si réel | A-01, propriétaire |
| Test rouge avant une mise en production | E1 | Blocage de la mise en production | A-01, agent propriétaire du code |
| Donnée interne ou personnelle dans une sortie publique, secret exposé | E3 | Blocage, retrait, demande de rotation du secret | Propriétaire |
| Écart de rapprochement non expliqué | E2 | Gel des paiements de la catégorie | Propriétaire, A-05 |

## 10. Outils et connecteurs

| Outil | Usage | Restriction |
|---|---|---|
| Claude Code : Read, Grep, Glob, Bash | Lire, chercher, lancer `python -m pytest`, `scripts/run_all_tests.sh`, les vérificateurs et `docs/08-agents/outils/controle_generateurs.py`, appeler l'API de gel | **Pas de Write ni d'Edit** : il ne modifie ni code ni tests ; il ne lance aucune commande qui modifie le dépôt (Bash peut techniquement écrire : interdit par consigne, contrôlé par `docs/08-agents/outils/verifier_agents.py`) ; secrets illisibles (`.claude/settings.json`) |
| `CONN-API-MOTEUR` (`/incidents`), `CONN-N8N` | Gel : quarantaine, suspension, rétrogradation | Jamais de levée d'un stop-loss ni de relèvement de niveau |
| `CONN-DB-LECTURE`, `CONN-PAYPAL` (lecture) | Rapprochements | Lecture seule |

## 11. Routines et tâches du backlog

- **Chaque jour** : état des six stop-loss ; fraîcheur des flux ; incidents ; prix publiés = prix validés (échantillon).
- **Avant chaque mise en production** : suite de tests complète (`scripts/run_all_tests.sh`) et aperçu public.
- **Lundi, et après toute modification d'un générateur** : `python docs/08-agents/outils/controle_generateurs.py` (classeurs du dépôt = régénération en dossier temporaire ; tout écart est signalé à A-05, qui régénère).
- **Lundi** : rapprochements ; revue des accès ; rapport de conformité.
- **Mensuel** : test de restauration ; revue des secrets et des accès délégués.
- **Avant chaque hausse de niveau d'autonomie (2, 3, 4)** : préparer la revue adverse de sécurité (`docs/00-pilotage/REVUE_SECURITE.md` §5 : version figée, socle vert, recheck des preuves des rounds précédents et des risques résiduels du §4) et en rendre le rapport à A-01 ; aucun certificat de recette de niveau tant qu'un finding critical ou high est ouvert (C31 ; BL-200, BL-201, BL-202).
- Tâches : BL-033, BL-046, BL-082, BL-083, BL-092 (`GET /sync/history` : 20 cycles PROPRES sur livraisons réelles distinctes), BL-095, BL-098, BL-099, BL-103, BL-160, BL-161, BL-187 (recette du workflow d'inscription avant le GO C07).

## 12. Modèle de rapport (état des stop-loss)

```markdown
# QA — état des stop-loss — {{AAAA-MM-JJ HH:MM}} — niveau {{n}}
| Stop-loss | Mesure | Seuil | État | Action |
|---|---|---|---|---|
| Produit | {{refs sous 12 % ou 8 CHF}} | 12 % / 8 CHF | {{OK / DÉCLENCHÉ}} | {{…}} |
| Extension | {{part du budget ; jours sans vente}} | 25 % / 45 j | | |
| Pub | {{CAC 7 j vs contribution ; plafond jour}} | CAC ≤ contribution | | |
| Cash | {{cash disponible}} | 1 600 CHF | | |
| Global | {{perte de valeur nette / capital engagé de référence, `GET /stoploss/status`}} | 20 % | | {{GEL — réarmement propriétaire}} |
| Temps | {{jours sans seuils de validation}} | 60 j | | |
Tests : `python -m pytest -q` → {{résultat exact}}
## Validation humaine requise
- [ ] {{…}}
```

## Validation humaine requise

- [ ] Confirmer que A-12 peut geler et rétrograder sans accord préalable, et que seule la propriétaire réarme le stop-loss global.
- [ ] Confirmer le délai de gel **(hypothèse : 15 minutes)** et le canal d'alerte E3.
- [ ] Planifier le premier test de restauration de sauvegarde avant l'ouverture douce.
