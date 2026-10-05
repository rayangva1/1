#!/usr/bin/env bash
# Lance toutes les suites de tests du repo, chacune dans son propre processus
# (les suites des dossiers docs/ et site/ importent leurs outils voisins).
set -u
cd "$(dirname "$0")/.."

suites=(
  "tests"
  "docs/00-pilotage/outils"
  "docs/02-sourcing/outils"
  "docs/04-legal/outils"
  "docs/05-da/tests"
  "docs/06-contenu/outils"
  "docs/08-agents/outils"
  "site/tests"
)

failed=0
for suite in "${suites[@]}"; do
  printf '\n=== %s ===\n' "$suite"
  if ! python -m pytest -q -p no:cacheprovider "$suite"; then
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  printf '\nÉCHEC : au moins une suite est rouge.\n'
  exit 1
fi
printf '\nOK : toutes les suites sont vertes.\n'
