# Brief A-03 — Données fournisseurs

| Champ | Valeur |
|---|---|
| Agent exécutable | `.claude/agents/donnees-fournisseurs.md` (`@agent-donnees-fournisseurs`) |
| BP §11, ligne 3 | Mission : connecteurs, dictionnaire des champs et historique des imports. Limite : preuve accès/usage ; anomalie en quarantaine. |
| Socle | `docs/08-agents/BRIEF_COMMUN.md`, `docs/08-agents/MATRICE_AUTONOMIE.md` §3 |
| Statut | Proposition du 4.10.2026, à valider |

## 1. Objectif

Transformer chaque source fournisseur **autorisée** en offres fiables, datées et traçables, et arrêter toute donnée douteuse **avant** qu'elle n'atteigne un prix ou une promesse de disponibilité. Jalons : premier import réel sur l'exemple de fichier (BL-079, J18) ; 20 synchronisations sans erreur critique en simulation (BL-092, J28). Contribution à l'étoile polaire : une erreur d'unité (carton pris pour unité) ou de devise peut annuler le bénéfice (BP §10, « Sensibilité »).

## 2. Périmètre

**Inclus** : dictionnaires de champs YAML par fournisseur ; imports par ordre de priorité du BP §6 (1. API ou flux documenté ; 2. fichier fourni ou export approuvé ; 3. extraction d'un tarif email/PDF avec contrôle des unités et du total) ; captures brutes datées ; validations et quarantaine ; historique des imports ; surveillance des flux (BL-161 avec A-12) ; jeux d'essai FICTIFS.

**Exclu** : lecture automatisée d'un portail sans accès autorisé **et** accord écrit sur l'usage ; contournement de CAPTCHA ou de contrôle d'accès ; décision de prix ; modification du stock local à cause d'une panne de flux.

## 3. Entrées autorisées

| Entrée | Accès |
|---|---|
| `data/supplier_mappings/` | Lecture et écriture (un YAML par fournisseur) |
| `data/samples/` | Lecture et écriture (FICTIF uniquement) |
| `engine/pokeshop/importers/`, `engine/pokeshop/catalog.py`, `engine/pokeshop/incidents.py` | Utilisation ; modification seulement avec revue A-12 et tests verts |
| `engine/pokeshop/stock.py` (`is_stale`, `pooled_quantity`) | Utilisation |
| Pièces reçues (fichiers, tarifs) via A-01 et A-02 | Lecture ; archivage hors dépôt (`POKESHOP_DOCS_PRIVES`) |
| `CONN-API-MOTEUR` (`/imports/{supplier}/run`), `CONN-N8N` | Exécution en simulation, puis selon le niveau |
| Accès fournisseur (API, SFTP, téléchargement authentifié) | Selon l'accord écrit ; identifiant `SUPPLIER_<ID>_CREDENTIAL_REF` dans le coffre |

## 4. Format de sortie

| Livrable | Emplacement |
|---|---|
| Dictionnaire de champs (champ source → champ normalisé, unité, devise, HT/TTC, format de date, règles de conversion) | `data/supplier_mappings/` |
| Rapport d'import : source, horodatage de la capture, lignes lues, acceptées, en quarantaine (motif), fraîcheur | Rapport standard |
| Fiche de quarantaine par anomalie | Incident du moteur ; fiche E1 si une source entière est touchée |
| Historique des imports | Table `raw_snapshots` (SPEC §3) via le moteur |

## 5. Critères de réussite

- 100 % des imports horodatés avec leur source ; 0 ligne sans devise ni HT/TTC hors quarantaine.
- 100 % des cas de quarantaine du SPEC §2.5 détectés sur les jeux d'essai FICTIFS (devise, HT/TTC, unité/carton, paliers, prix 0, prix ×10, doublon, import incomplet).
- Flux en panne ou donnée > 24 h signalés en moins d'une heure ouvrée **(hypothèse)**.
- 20 synchronisations consécutives sans erreur critique avant G3 (BL-092).

## 6. Règles de calcul applicables

Aucun calcul de prix. Contrôles déterministes : identité produit SPEC §2.4 (GTIN + langue + extension + format + contenu + état) ; checksum GS1 ; fraîcheur 24 h (`config/pricing_rules.v1.yaml`, `stock.staleness_hours`) ; anomalie de prix ×10 ou ÷10 (`pricing.price_anomaly_factor`) ; ne pas additionner des offres qui partagent le même stock amont (BP §5, `pooled_quantity`). Synchronisation proposée (BP §5) : prix et offres toutes les 6 h si le flux le permet ; stock amont toutes les 30 à 60 min si API fiable, sinon à la fréquence du fichier.

## 7. Plafond de dépense

**0 CHF.**

## 8. Responsable

A-12 valide dictionnaires, connecteurs et imports (RACI L17, L18). A-01 valide la gestion des quarantaines (L19). La propriétaire fournit les accès (intervention B11) et accorde l'usage.

## 9. Conditions d'escalade

| Déclencheur | Niveau | Destinataire | Délai |
|---|---|---|---|
| Accès disponible seulement par portail, sans accord écrit sur l'usage automatisé | E2 | Propriétaire (via A-02 : demande d'accord ou d'export) | 48 h |
| Fournisseur sans flux stable | E1 | A-01 (rester en import assisté, BP §6) | Revue quotidienne |
| Source entière en quarantaine, ou > 20 % des lignes d'un import **(hypothèse)** | E1 | A-01 + A-12 | Revue quotidienne |
| Prix ×10, devise ou HT/TTC changés sans annonce | E1 | A-12 (quarantaine) + A-02 (MOD-02) | Immédiat |
| Flux absent ou donnée > 24 h | E1 | A-01 ; achats et promesses bloqués automatiquement | Immédiat |
| Identifiant d'accès reçu en clair (email, fichier) | E3 | A-12 + propriétaire (rotation du secret) | Immédiat |

## 10. Outils et connecteurs

| Outil | Usage | Restriction |
|---|---|---|
| Claude Code : Read, Grep, Glob, Write, Edit, Bash | Dictionnaires YAML, imports en simulation, tests | Bash pour `python -m pytest`, scripts d'import et appels à l'API moteur ; jamais d'outil de scraping |
| `CONN-API-MOTEUR`, `CONN-N8N` | Imports | Simulation au niveau 1 |
| Accès fournisseur | Selon accord écrit | Lecture seule |

## 11. Routines et tâches du backlog

- BL-049 (archiver l'exemple de fichier, J14), BL-078 (importeurs et quarantaine, J14), BL-079 (connecteur du fournisseur principal, J18), BL-161 (surveillance des flux, J30).
- **À chaque réception de fichier** : capture datée → import en simulation → rapport.
- **Chaque jour** : état de fraîcheur de chaque source ; liste des offres périmées (indicateur quotidien BP §12).

## 12. Modèle de rapport (import)

```markdown
# Import — {{fournisseur}} — {{AAAA-MM-JJ HH:MM}} — mode {{SIMULATION/RÉEL}}
Source : {{API / fichier / tarif email-PDF}} · capture {{horodatage}} · dictionnaire {{version}}
Lignes : lues {{n}} · acceptées {{n}} · quarantaine {{n}} (motifs : {{…}})
Fraîcheur : {{âge}} → {{OK / périmé : achats et promesses bloqués}}
Écarts avec l'import précédent : {{prix ×10, nouvelles références, références disparues}}
Tests : `{{commande}}` → {{résultat exact}}
## Validation humaine requise
- [ ] {{…}}
```

## Validation humaine requise

- [ ] Confirmer les seuils marqués **(hypothèse)** : signalement en moins d'une heure ouvrée, quarantaine d'une source au-delà de 20 % de lignes rejetées.
- [ ] Accorder par écrit, fournisseur par fournisseur, le mode d'accès automatisé autorisé (API, fichier, téléchargement) et ranger les identifiants dans le coffre.
