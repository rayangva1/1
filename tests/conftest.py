"""Isolation des tests : chaque test a son propre dossier d'état (journaux JSON Lines).

Sans ``POKESHOP_STATE_DIR``, les états de sécurité sont persistés dans
:func:`pokeshop.settings.default_state_dir` (``$XDG_STATE_HOME/pokeshop``) : on le fait pointer
vers un dossier temporaire propre à chaque test, pour qu'aucun test n'hérite du gel, du registre
ou des incidents d'un autre (ni d'une exécution précédente) et que rien ne s'écrive hors de ``tmp``.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state_home = tmp_path / "xdg-state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    monkeypatch.delenv("POKESHOP_STATE_DIR", raising=False)
    return state_home / "pokeshop"
