#!/usr/bin/env bash
# Lance toutes les suites de tests du repo, chacune dans son propre processus
# (les suites des dossiers docs/ et site/ importent leurs outils voisins),
# puis les tests navigateur de la landing (Node + Playwright + Chromium) quand ils sont disponibles.
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

# Garde-fous navigateur (pause, mouvement réduit, contrastes sur images noire et blanche, fil orange, formulaire…) :
# site/tests/e2e/atelier.mjs. S'ils ne peuvent pas tourner, le lanceur le dit en toutes lettres (jamais en silence).
e2e_ignores=0
printf '\n=== site/tests/e2e (navigateur : Node + Playwright + Chromium) ===\n'
if command -v node >/dev/null 2>&1 && node site/tests/e2e/atelier.mjs --disponible >/dev/null 2>&1; then
  if ! node site/tests/e2e/atelier.mjs; then
    failed=1
  fi
else
  e2e_ignores=1
  printf 'IGNORÉS : Node.js, Playwright ou Chromium absent : les tests navigateur de la landing ne sont PAS exécutés.\n'
  printf 'Pour les lancer : installer Node.js et Playwright (Chromium), puis « node site/tests/e2e/atelier.mjs » (site/README.md).\n'
fi

if [ "$failed" -ne 0 ]; then
  printf '\nÉCHEC : au moins une suite est rouge.\n'
  exit 1
fi
if [ "$e2e_ignores" -ne 0 ]; then
  printf '\nOK pour les suites Python ; ATTENTION : tests navigateur IGNORÉS (voir ci-dessus).\n'
else
  printf '\nOK : toutes les suites sont vertes (tests navigateur compris).\n'
fi
