"""Rend les outils de site/ importables dans les tests."""

import sys
from pathlib import Path

OUTILS = Path(__file__).resolve().parents[1] / "outils"
if str(OUTILS) not in sys.path:
    sys.path.insert(0, str(OUTILS))
