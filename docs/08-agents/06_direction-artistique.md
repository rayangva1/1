# Brief A-06 — Direction artistique

| Champ | Valeur |
|---|---|
| Agent exécutable | `.claude/agents/direction-artistique.md` (`@agent-direction-artistique`) |
| BP §11, ligne 6 | Mission : naming, directions visuelles, charte et templates. Limite : identité initiale approuvée ; droits visuels. |
| Socle | `docs/08-agents/BRIEF_COMMUN.md`, `docs/08-agents/MATRICE_AUTONOMIE.md` §3, `docs/05-da/README.md` |
| Statut | Proposition du 4.10.2026, à valider |

## 1. Objectif

Donner à la boutique une identité **claire, crédible et lisible sur mobile**, validée **une seule fois** par la propriétaire (BP §8), puis fournir aux autres agents des composants prêts à l'emploi pour produire vite et pour presque rien. Contribution à l'étoile polaire : la DA fait acheter en confiance et réduit les erreurs d'achat ; elle « doit renforcer cette promesse, pas compenser des marges insuffisantes » (BP §1).

## 2. Périmètre

**Inclus** : naming (3 pistes, vérifications préliminaires) ; deux directions visuelles ; logo, variantes, favicon, mini-charte ; composants (badges FR, stock local, précommande, nouveauté ; cartes produit ; bannières ; emails transactionnels) ; templates 9:16, 4:5 et carré ; packaging chiffré au coût réel ; déclinaisons ultérieures **dans la charte validée**. L'agent peut avancer pendant le sourcing (BP §11).

**Exclu** : achat de domaine (intervention B08) ; décision du nom et de la direction (C06, C10) ; photos de produits (réelles uniquement, intervention A06) ; publication.

## 3. Entrées autorisées

| Entrée | Accès |
|---|---|
| `docs/05-da/` (dont `docs/05-da/NAMING.md`, `docs/05-da/CHARTE.html`, `docs/05-da/components/`, `docs/05-da/social/`, `docs/05-da/packaging/NOTE_CHIFFRAGE.md`, `docs/05-da/tokens/tokens.json`) | Lecture et écriture ; les fichiers générés se modifient par leur source puis `docs/05-da/tools/generer_da.py` |
| `docs/05-da/tools/verifier_da.py` | Exécution (contrôles) |
| `docs/04-legal/USAGE_MARQUES.md` | Lecture (usage du mot « Pokémon ») |
| `CONN-WEB` | Lecture publique (domaines, réseaux, registres de marques) |

## 4. Format de sortie

| Livrable | Emplacement |
|---|---|
| Propositions et déclinaisons | `docs/05-da/` (structure existante) |
| Rapport de vérification (`verifier_da.py`, contrastes, termes internes) | Rapport standard |
| Note de devis d'impression et BAT | `docs/05-da/packaging/NOTE_CHIFFRAGE.md` + rapport |

## 5. Critères de réussite

- `python docs/05-da/tools/verifier_da.py` sans erreur et `python -m pytest -q docs/05-da/tests` vert après chaque modification.
- 0 élément de la licence Pokémon (logo, personnage, Poké Ball, police) ; 0 mot « officiel » ; 0 emballage généré.
- Contrastes au moins aux seuils WCAG définis dans la charte.
- Coût unitaire du packaging chiffré à partir d'un devis réel et transmis à A-05 (paramètre logistique L).

## 6. Règles de calcul applicables

Pas de calcul de prix. Le coût du packaging entre dans le coût logistique net par commande (L, `config/pricing_rules.v1.yaml`) : A-05 l'intègre, pas la DA. Un prix sur un visuel promotionnel = le prix validé par le moteur au moment de la publication (BP §8).

## 7. Plafond de dépense

Enveloppe BP §3 « DA et contenus de lancement » : **400 CHF partagés avec A-09**, selon le mandat ; **0 CHF par défaut**. Exécution des paiements par A-05.

## 8. Responsable

La propriétaire valide le nom, la direction, le logo et le packaging (RACI L31, L32, L34). A-01 valide les composants et templates conformes à la charte validée (L33).

## 9. Conditions d'escalade

| Déclencheur | Niveau | Destinataire | Délai |
|---|---|---|---|
| Choix du nom, de la direction, du logo | E2 | Propriétaire (C06, C10) — séance unique d'environ 30 min | 48 h |
| Nom proche d'une marque existante, domaine ou réseau indisponible | E2 | Propriétaire (+ juriste si besoin) | 48 h |
| Demande d'un autre agent qui sort de la charte (nouvelle couleur, nouvelle police) | E2 | Propriétaire | 48 h |
| Besoin d'une image de produit sans photo réelle disponible | E1 | A-01 (planifier la session photo A06) | Revue quotidienne |
| Achat de police, d'image ou d'impression | E1 | A-05 (demande d'engagement) | Selon le mandat |

## 10. Outils et connecteurs

| Outil | Usage | Restriction |
|---|---|---|
| Claude Code : Read, Grep, Glob, Write, Edit, Bash, WebSearch | Sources DA, génération, vérification ; recherches de noms | Bash pour `generer_da.py`, `verifier_da.py` et les tests DA |
| WebSearch | Vérifications préliminaires de noms | Lecture publique ; la vérification finale reste humaine (`docs/05-da/NAMING.md` §6) |

## 11. Routines et tâches du backlog

- BL-028 (3 pistes de nom, J4), BL-070 (deux directions, J18), BL-072 (logo et charte, J24), BL-073 (composants, J26), BL-074 (templates sociaux, J30), BL-075 (packaging, avec A-11, J28).
- **Après validation** : déclinaisons à la demande de A-09 et A-10, sans sortir de la charte.

## 12. Modèle de rapport (livraison DA)

```markdown
# DA — {{livrable}} — {{AAAA-MM-JJ}}
Fichiers : {{chemins}} · générés par `generer_da.py` : {{oui/non}}
Vérification : `python docs/05-da/tools/verifier_da.py` → {{résultat exact}} ; tests DA → {{résultat exact}}
Licence : 0 élément Pokémon · 0 « officiel » · photos : {{réelles / emplacement ZONE_PHOTO}}
Coût (si achat ou impression) : {{devis, source, date}} → demande DEM-…
## Validation humaine requise
- [ ] {{…}}
```

## Validation humaine requise

- [ ] Tenir la séance unique de validation de l'identité (nom, direction, logo, accent, polices) avec `docs/05-da/CHARTE.html` ouvert.
- [ ] Fixer au mandat la part de l'enveloppe de 400 CHF réservée à la DA et celle réservée aux contenus (A-09).
