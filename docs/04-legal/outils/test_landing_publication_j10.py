"""Landing publiable à J10, message sans JavaScript exact, IP effacée (revue round 2 : CON-06, NEW-04, NEW-05).

Les contrôles vivent dans ``site/outils/verifier_site.py`` (contrôles 13 à 15) ; ces tests vérifient qu'ils
passent sur le dépôt et qu'ils détectent les défauts relevés par la revue.
Lancer : ``python -m pytest -q docs/04-legal/outils``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import registre_champs as rc

SITE_OUTILS = rc.REPO / "site" / "outils"
sys.path.insert(0, str(SITE_OUTILS))

import publication  # noqa: E402
import verifier_site as vs  # noqa: E402


def test_every_landing_field_is_provided_by_j10() -> None:
    """CON-06 : chaque champ exigé vient d'un acte planifié au plus tard à J10."""
    assert vs.verifier_champs_landing_planifies() == []


def test_landing_field_depending_on_full_hosting_is_detected() -> None:
    """CON-06 : l'URL du webhook dépendait de l'hébergement complet (B23, J26) et l'IA du seul mandat."""
    champs = dict(publication.CHAMPS_LANDING)
    champs["WEBHOOK_INSCRIPTION"] = (publication.DEFINITIF, "B23 (J26) et workflow n8n testé")
    champs["ST_IA"] = (publication.DEFINITIF, "mandat")
    erreurs = vs.verifier_champs_landing_planifies(champs=champs)
    assert "WEBHOOK_INSCRIPTION : B23 planifié à J26, après la publication de la landing (J10)" in erreurs
    assert any(e.startswith("ST_IA : acte sans intervention") for e in erreurs)


def test_landing_acts_for_hosting_ai_and_retention_are_owner_interventions() -> None:
    """CON-06 : hébergement de n8n (B27), IA et durées (C26) sont des interventions datées avant J10."""
    acts = {nom: acte for nom, (_n, acte) in publication.CHAMPS_LANDING.items()}
    assert "B27" in acts["WEBHOOK_INSCRIPTION"] and "BL-187" in acts["WEBHOOK_INSCRIPTION"]
    assert "B27" in acts["ST_BASE"] and "C26" in acts["ST_IA"]
    assert "C26" in acts["DUREE_CONSERVATION_ALERTES"] and "C26" in acts["DUREE_CONSERVATION_SAV"]


def test_published_page_says_the_form_works_without_javascript(tmp_path: Path) -> None:
    """NEW-04 : en publication, le message sans JavaScript ne dit plus « nécessite JavaScript »."""
    source = (rc.REPO / "site" / "landing" / "index.html").read_text(encoding="utf-8")
    assert vs.verifier_noscript(source, publication_mode=False) == []
    publie = source.replace("<!-- PUBLICATION:NOSCRIPT -->", publication.NOSCRIPT_PUBLICATION).replace(
        'method="post" action=""', 'method="post" action="https://n8n.exemple.invalid/webhook/inscription"'
    )
    publie = publication.APERCU_RE.sub("", publie)
    assert vs.verifier_noscript(publie, publication_mode=True) == []
    ancien = publie.replace(
        publication.NOSCRIPT_PUBLICATION,
        '<noscript><p class="lp-statut">Le formulaire nécessite JavaScript.</p></noscript>',
    )
    assert any("message sans JavaScript faux" in e for e in vs.verifier_noscript(ancien, publication_mode=True))


def test_inscription_workflow_must_not_keep_executions(tmp_path: Path) -> None:
    """NEW-05 : une exécution conservée garderait l'IP (x-forwarded-for) : l'export doit tout désactiver."""
    assert vs.verifier_workflow_inscription() == []
    export = {"name": "09 Inscription aux alertes", "nodes": [], "connections": {},
              "settings": {"saveDataSuccessExecution": "none", "saveDataErrorExecution": "all"}}  # fmt: skip
    (tmp_path / "09_inscription_alertes.json").write_text(json.dumps(export), encoding="utf-8")
    erreurs = vs.verifier_workflow_inscription(tmp_path)
    assert erreurs == ["09_inscription_alertes.json : saveDataErrorExecution = 'all' (attendu « none » : aucune "
                       "exécution conservée)"]  # fmt: skip
    export["settings"].update(saveDataErrorExecution="none", saveManualExecutions=False)
    (tmp_path / "09_inscription_alertes.json").write_text(json.dumps(export), encoding="utf-8")
    assert vs.verifier_workflow_inscription(tmp_path) == []


def test_notice_and_contract_state_the_ip_erasure_terms() -> None:
    """NEW-05 : la promesse publiée et le contrat imposé au workflow disent la même chose."""
    notice = "\n".join(rc.public_blocks((rc.LEGAL_DIR / "CONFIDENTIALITE_LANDING.md").read_text(encoding="utf-8")))
    assert "effacées après le contrôle (au plus 1 heure)" in notice and "au plus 24 heures" in notice
    contrat = (rc.REPO / "site" / "landing" / "README.md").read_text(encoding="utf-8")
    for terme in ("saveDataSuccessExecution", "saveDataErrorExecution", "1 heure", "24 h", "sans** IP"):
        assert terme in contrat, terme
