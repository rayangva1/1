# 08-agents — la flotte d'agents

Dossier de la flotte de 12 agents du BP §11, adaptée au modèle d'opération de la propriétaire : les agents gèrent tout **dans un mandat écrit** ; la propriétaire n'intervient que pour le physique, le légal une fois, et les validations hors mandat (dont le réarmement du stop-loss global).

**Étoile polaire :** contribution nette cumulée (ventes nettes HT − coût historique − paiement − logistique − SAV − acquisition − charges fixes). Ni CA ni followers.

## Contenu

| Fichier | Rôle |
|---|---|
| `docs/08-agents/BRIEF_COMMUN.md` | Socle commun : règles non négociables, 9 rubriques, statuts, rapport standard, escalade, plafonds, stop-loss, connecteurs |
| `docs/08-agents/ORGANIGRAMME.md` | Dépendances et gates, flux des exceptions, RACI agents × 61 livrables, passations |
| `docs/08-agents/MATRICE_AUTONOMIE.md` | Niveaux 1 à 4 (BP §13), ce que chaque agent fait seul, prépare, s'interdit ; connecteurs et plafonds |
| `docs/08-agents/RUNBOOK.md` | Utilisation quotidienne dans Claude Code : lancer, demander, décider, routines, connecteurs |
| `docs/08-agents/CARTE_REPO.md` | Fichiers du dépôt utilisés par la flotte, présents ou attendus |
| `docs/08-agents/01_chef-de-projet.md` … `docs/08-agents/12_qa-conformite.md` | 12 briefs de mission (9 rubriques du BP + outils, routines, modèle de rapport) |
| `docs/08-agents/modeles/` | Gabarits : rapport, fiche d'exception, plan de dispatch, demande d'engagement, modèles d'emails, registre du mandat |
| `docs/08-agents/rapports/`, `docs/08-agents/exceptions/` | Sorties des agents en exploitation (vides au 4.10.2026) |
| `docs/08-agents/outils/verifier_agents.py` | Vérificateur (frontmatter YAML, outils minimaux, sections, RACI, chemins, secrets) |
| `.claude/agents/` | Les 12 agents exécutables par Claude Code |

## Les 12 agents

| # | Agent (Claude Code) | Brief | Outils |
|---|---|---|---|
| 01 | `chef-de-projet` | `docs/08-agents/01_chef-de-projet.md` | Agent (vers les 11), Read, Grep, Glob, Write, Edit |
| 02 | `sourcing` | `docs/08-agents/02_sourcing.md` | Read, Grep, Glob, Write, Edit, WebSearch, WebFetch |
| 03 | `donnees-fournisseurs` | `docs/08-agents/03_donnees-fournisseurs.md` | Read, Grep, Glob, Write, Edit, Bash |
| 04 | `catalogue` | `docs/08-agents/04_catalogue.md` | Read, Grep, Glob, Write, Edit, Bash |
| 05 | `finance-pricing` | `docs/08-agents/05_finance-pricing.md` | Read, Grep, Glob, Write, Edit, Bash |
| 06 | `direction-artistique` | `docs/08-agents/06_direction-artistique.md` | Read, Grep, Glob, Write, Edit, Bash, WebSearch |
| 07 | `site-integrations` | `docs/08-agents/07_site-integrations.md` | Read, Grep, Glob, Write, Edit, Bash |
| 08 | `seo-redaction` | `docs/08-agents/08_seo-redaction.md` | Read, Grep, Glob, Write, Edit, WebSearch, WebFetch |
| 09 | `communication` | `docs/08-agents/09_communication.md` | Read, Grep, Glob, Write, Edit, WebFetch |
| 10 | `acquisition` | `docs/08-agents/10_acquisition.md` | Read, Grep, Glob, Write, Edit, Bash |
| 11 | `operations-sav` | `docs/08-agents/11_operations-sav.md` | Read, Grep, Glob, Write, Edit, Bash |
| 12 | `qa-conformite` | `docs/08-agents/12_qa-conformite.md` | Read, Grep, Glob, Bash |

Choix de moindre privilège : seul le chef de projet délègue ; sourcing, SEO et communication n'ont pas de Bash ; le QA n'a ni Write ni Edit (il ne peut pas « réparer » un test pour le faire passer). Aucun connecteur externe n'est branché : ils s'ajoutent un par un après recette (`docs/08-agents/RUNBOOK.md` §8).

## Vérifier

```bash
python docs/08-agents/outils/verifier_agents.py      # contrôles de cohérence (code de sortie 1 si erreur)
python -m pytest -q docs/08-agents/outils            # tests du vérificateur
```

## Validation humaine requise

- [ ] Relire le brief commun, la matrice d'autonomie et le RACI, puis les 12 agents exécutables, avant la première utilisation.
- [ ] Signer le mandat (`docs/00-pilotage/DELEGATION_AUTONOMIE.md`) : sans lui, la flotte reste en préparation, à 0 CHF.
