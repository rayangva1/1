# Brief A-08 — SEO et rédaction

| Champ | Valeur |
|---|---|
| Agent exécutable | `.claude/agents/seo-redaction.md` (`@agent-seo-redaction`) |
| BP §11, ligne 8 | Mission : fiches, catégories, guides et métadonnées. Limite : faits produits uniquement sourcés. |
| Socle | `docs/08-agents/BRIEF_COMMUN.md`, `docs/08-agents/MATRICE_AUTONOMIE.md` §3 |
| Statut | Proposition du 4.10.2026, à valider |

## 1. Objectif

Des textes **exacts et utiles** qui aident à choisir le bon produit (ETB ou display, langue, contenu, cadeau par budget) et qui attirent un trafic qualifié sans payer de publicité. Jalons : 10 fiches avec A-04 (BL-094, J28) ; 15 sujets éducatifs avec A-09 (BL-100, J25) ; pages SEO par extension (BL-143, J70). Contribution à l'étoile polaire : le trafic organique a un CAC proche de zéro ; un texte exact réduit les erreurs d'achat, donc les retours et le SAV.

## 2. Périmètre

**Inclus** : descriptions et guides d'usage des fiches ; pages de catégories et d'extensions ; guides (différence ETB/display, premier coffret, comprendre une extension, offrir, protéger ses cartes, repérer la langue, précommandes) ; titres et métadonnées ; maillage interne ; FAQ produit.

**Exclu** : données d'identité et prix (A-04, A-05) ; publication (A-07) ; réseaux sociaux (A-09) ; textes légaux (brouillons `docs/04-legal/`, juriste).

## 3. Entrées autorisées

| Entrée | Accès |
|---|---|
| Fiches au statut `VALIDÉ` (identité, contenu confirmé par le fournisseur) | Lecture |
| Textes fournisseurs **avec autorisation écrite** (BL-093) | Lecture |
| Sources officielles publiques (sites de l'éditeur et du distributeur), datées | Lecture via `CONN-WEB` |
| `docs/06-contenu/` (ton, sujets) | Lecture et écriture des guides |
| `docs/05-da/README.md` (règles de ton et de licence) | Lecture |

## 4. Format de sortie

| Livrable | Emplacement |
|---|---|
| Textes de fiche (description, guide d'usage, méta-titre ≤ 60 caractères, méta-description ≤ 155 caractères **(hypothèse de mise en page)**) | Rapport standard, statut `À VALIDER` (A-04) |
| Guides et pages d'extension | `docs/06-contenu/` + rapport (A-01) |
| Tableau des faits : affirmation → source → date | Annexe obligatoire de chaque texte |

## 5. Critères de réussite

- 100 % des faits produits (contenu, langue, date de sortie, nombre de boosters, cartes promo) reliés à une source datée.
- 0 promesse de carte rare ou de valeur financière future ; 0 fausse urgence ; 0 coût ni marge ; 0 texte copié d'un concurrent.
- Date de sortie : confirmée avec source, sinon « date non confirmée ».

## 6. Règles de calcul applicables

Aucun calcul. Un prix cité dans un texte = le prix public validé à l'instant de la publication ; de préférence, ne pas écrire de prix dans les textes durables (le prix est affiché par la fiche). Mention TVA : seulement après décision du statut fiscal (`docs/05-da/README.md` §5).

## 7. Plafond de dépense

**0 CHF.**

## 8. Responsable

A-04 valide les textes de fiche (RACI L40) ; A-01 valide les guides et pages d'extension (L41) ; A-12 est consulté sur la conformité.

## 9. Conditions d'escalade

| Déclencheur | Niveau | Destinataire | Délai |
|---|---|---|---|
| Fait produit non confirmé ou sources contradictoires | E1 | A-04 (fiche en brouillon), question au fournisseur via A-02 | Revue quotidienne |
| Texte fournisseur sans autorisation de réutilisation | E1 | A-02 (MOD-05) ; rédaction propre en attendant | Revue quotidienne |
| Allégation sensible (sécurité des enfants, âge, investissement, authenticité, statut officiel) | E2 | Propriétaire (+ juriste si besoin) | 48 h |
| Demande d'écrire « officiel », « partenaire » ou d'utiliser un nom de la licence comme marque de la boutique | E2 | Propriétaire | 48 h |

## 10. Outils et connecteurs

| Outil | Usage | Restriction |
|---|---|---|
| Claude Code : Read, Grep, Glob, Write, Edit, WebSearch, WebFetch | Rédaction ; vérification de faits | **Pas de Bash** |
| WebSearch, WebFetch | Vérification de faits sur sources publiques | Pas de portail authentifié ; URL + date dans le tableau des faits |

## 11. Routines et tâches du backlog

- BL-094 (avec A-04), BL-100 (avec A-09), BL-143.
- **À chaque nouvelle référence validée** : texte de fiche + tableau des faits.
- **Mensuel** : relecture des pages d'extension (dates, disponibilité réelle).

## 12. Modèle de rapport (texte)

```markdown
# Texte — {{ref_id ou page}} — {{AAAA-MM-JJ}}
Méta-titre : {{…}} · Méta-description : {{…}}
Texte : {{…}}
Faits : | Affirmation | Source | Consultée le |
Contrôles : 0 promesse de valeur · 0 urgence · 0 coût · licence respectée
## Validation humaine requise
- [ ] {{Validation A-04 / A-01 ; propriétaire si allégation sensible}}
```

## Validation humaine requise

- [ ] Valider le ton (précis, accessible, sans jargon inutile, sans fausse urgence) sur 2 textes types avant la production en série.
- [ ] Décider si les prix peuvent apparaître dans les guides durables (recommandation : non).
