"""Tests de la flotte d'agents (docs/08-agents/ et .claude/agents/).

Chaque contrôle est testé sur les vrais fichiers (doit passer), puis sur une copie altérée (doit échouer).
Les copies vivent dans un dépôt temporaire : ``docs/08-agents`` et ``.claude/agents`` sont copiés, le reste du
dépôt est relié par liens symboliques (lecture seule de fait).
Lancer : ``python -m pytest -q docs/08-agents/outils``.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import verifier_agents as v
import yaml

REPO = v.REPO


# ------------------------------------------------------------------------------------------- outillage
def make_root(tmp_path: Path) -> Path:
    """Dépôt temporaire : copies modifiables de la flotte, liens vers le reste."""
    root = tmp_path / "repo"
    root.mkdir()
    for entry in REPO.iterdir():
        if entry.name in {"docs", ".claude", ".git"}:
            continue
        (root / entry.name).symlink_to(entry)
    (root / "docs").mkdir()
    for entry in (REPO / "docs").iterdir():
        if entry.name != "08-agents":
            (root / "docs" / entry.name).symlink_to(entry)
    shutil.copytree(REPO / v.DOCS_DIR, root / v.DOCS_DIR)
    shutil.copytree(REPO / v.AGENTS_DIR, root / v.AGENTS_DIR)
    return root


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    """Remplace ``old`` par ``new`` (doit exister) dans une copie."""
    text = path.read_text(encoding="utf-8")
    assert old in text, f"motif absent de {path.name} : {old!r}"
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def set_frontmatter(path: Path, **changes: object) -> None:
    """Réécrit des champs du frontmatter d'un agent (``None`` supprime le champ)."""
    data, body = v.load_frontmatter(path)
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=10_000)
    path.write_text(f"---\n{dumped}---\n{body}", encoding="utf-8")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return make_root(tmp_path)


# ------------------------------------------------------------------------------------------- vrais fichiers
@pytest.mark.parametrize("check", v.ALL_CHECKS, ids=lambda c: c.__name__)
def test_real_files_pass(check):
    assert check() == []


def test_run_all_and_main(capsys):
    assert v.run_all() == []
    assert v.main() == 0
    assert "OK" in capsys.readouterr().out


def test_copy_is_faithful(root):
    """La copie temporaire passe tous les contrôles : les échecs ci-dessous viennent bien des altérations."""
    assert v.run_all(root) == []


@pytest.mark.parametrize("slug", list(v.AGENTS))
def test_each_agent_frontmatter_is_safe_yaml(slug):
    """Exigence explicite : frontmatter lisible par yaml.safe_load, avec name, description, tools."""
    text = v.agent_file(slug).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    raw = text.split("\n---\n", 1)[0].removeprefix("---\n")
    data = yaml.safe_load(raw)
    assert isinstance(data, dict)
    assert data["name"] == slug
    assert isinstance(data["description"], str) and "À utiliser" in data["description"]
    assert isinstance(data["tools"], str) and data["tools"].strip()


def test_twelve_agents_twelve_briefs():
    assert len(v.AGENTS) == 12
    assert sorted(p.stem for p in (REPO / v.AGENTS_DIR).glob("*.md")) == sorted(v.AGENTS)
    briefs = sorted(p.name for p in (REPO / v.DOCS_DIR).glob("[0-9][0-9]_*.md"))
    assert briefs == sorted(f"{num}_{slug}.md" for slug, (num, _) in v.AGENTS.items())


def test_least_privilege_invariants():
    """Invariants demandés : sourcing sans Bash, QA avec Bash mais sans écriture, seul le chef délègue."""
    tools = {
        slug: {v.tool_name(t) for t in v.split_tools(v.load_frontmatter(v.agent_file(slug))[0]["tools"])}
        for slug in v.AGENTS
    }
    assert "Bash" not in tools["sourcing"]
    assert {"Read", "Grep", "Glob", "Bash"} == tools["qa-conformite"]
    assert [slug for slug, names in tools.items() if "Agent" in names] == ["chef-de-projet"]
    assert all("Read" in names for names in tools.values())


# ------------------------------------------------------------------------------------------- utilitaires
def test_split_tools_keeps_agent_parentheses():
    assert v.split_tools("Agent(a, b), Read, Bash") == ["Agent(a, b)", "Read", "Bash"]
    assert v.split_tools(["Read", " Grep "]) == ["Read", "Grep"]
    assert v.split_tools(None) == []
    assert v.agent_targets("Agent(a, b)") == {"a", "b"}
    assert v.agent_targets("Agent") == set()


def test_h2_headings_ignore_code_blocks():
    text = "## A\n```markdown\n## Faux\n```\n## B\n"
    assert v.h2_headings(text) == ["## A", "## B"]


def test_split_frontmatter_none_without_header():
    assert v.split_frontmatter("pas de frontmatter") is None


# ------------------------------------------------------------------------------------------- 1. frontmatter
def test_invalid_yaml_detected(root):
    path = v.agent_file("sourcing", root)
    edit(path, "name: sourcing", "name: [sourcing")
    assert any("illisible" in e for e in v.check_agent_frontmatter(root))


def test_missing_frontmatter_detected(root):
    path = v.agent_file("catalogue", root)
    path.write_text(path.read_text(encoding="utf-8").replace("---\n", "", 1), encoding="utf-8")
    assert any("frontmatter absent" in e for e in v.check_agent_frontmatter(root))


def test_frontmatter_not_a_mapping_detected(root):
    path = v.agent_file("communication", root)
    _, body = v.load_frontmatter(path)
    path.write_text(f"---\n- name\n- tools\n---\n{body}", encoding="utf-8")
    assert any("un dictionnaire est attendu" in e for e in v.check_agent_frontmatter(root))


def test_missing_tools_field_detected(root):
    set_frontmatter(v.agent_file("acquisition", root), tools=None)
    assert any("« tools » manquant" in e for e in v.check_agent_frontmatter(root))


def test_name_mismatch_and_case_detected(root):
    set_frontmatter(v.agent_file("catalogue", root), name="Catalogue")
    set_frontmatter(v.agent_file("acquisition", root), name="acquisition-pub")
    errors = v.check_agent_frontmatter(root)
    assert any("kebab-case" in e for e in errors)
    assert any("différent du nom de fichier" in e for e in errors)


def test_description_must_say_when(root):
    set_frontmatter(v.agent_file("communication", root), description="Agent communication. " * 6)
    set_frontmatter(v.agent_file("catalogue", root), description="Court")
    errors = v.check_agent_frontmatter(root)
    assert any("communication.md : la description doit dire quand" in e for e in errors)
    assert any("catalogue.md : description absente ou trop courte" in e for e in errors)


def test_unknown_field_and_model_detected(root):
    set_frontmatter(v.agent_file("seo-redaction", root), modele="inherit", model="gpt")
    errors = v.check_agent_frontmatter(root)
    assert any("champ inconnu « modele »" in e for e in errors)
    assert any("model « gpt »" in e for e in errors)


def test_sourcing_with_bash_rejected(root):
    set_frontmatter(v.agent_file("sourcing", root), tools="Read, Grep, Glob, Write, Edit, WebSearch, WebFetch, Bash")
    errors = v.check_agent_frontmatter(root)
    assert any("sourcing.md : cet agent ne doit pas avoir Bash" in e for e in errors)


def test_qa_with_write_rejected(root):
    set_frontmatter(v.agent_file("qa-conformite", root), tools="Read, Grep, Glob, Bash, Write")
    assert any("ni Write ni Edit" in e for e in v.check_agent_frontmatter(root))


def test_agent_tool_outside_dispatcher_rejected(root):
    set_frontmatter(v.agent_file("catalogue", root), tools="Agent, Read, Grep, Glob, Write, Edit, Bash")
    assert any("seul le chef de projet peut déléguer" in e for e in v.check_agent_frontmatter(root))


def test_dispatcher_agent_list_must_be_complete(root):
    path = v.agent_file("chef-de-projet", root)
    edit(path, "Agent(sourcing, ", "Agent(")
    assert any("exactement les 11 autres agents" in e for e in v.check_agent_frontmatter(root))


def test_unknown_and_duplicate_tools_rejected(root):
    set_frontmatter(v.agent_file("acquisition", root), tools="Read, Read, Grep, Glob, Write, Edit, Bash, mcp__paypal")
    errors = v.check_agent_frontmatter(root)
    assert any("outil non autorisé « mcp__paypal »" in e for e in errors)
    assert any("outil en double" in e for e in errors)


def test_tools_as_yaml_list_accepted(root):
    set_frontmatter(v.agent_file("acquisition", root), tools=["Read", "Grep", "Glob", "Write", "Edit", "Bash"])
    assert v.check_agent_frontmatter(root) == []


def test_missing_and_extra_agent_files(root):
    v.agent_file("operations-sav", root).unlink()
    (root / v.AGENTS_DIR / "intrus.md").write_text("---\nname: intrus\n---\n", encoding="utf-8")
    errors = v.check_agent_frontmatter(root)
    assert any("operations-sav.md : fichier manquant" in e for e in errors)
    assert any("intrus.md : agent inconnu" in e for e in errors)


# ------------------------------------------------------------------------------------------- 2. prompts
def test_prompt_missing_section_detected(root):
    edit(v.agent_file("finance-pricing", root), "## Interdits", "## Limites")
    assert any("« ## Interdits » manquante" in e for e in v.check_agent_prompts(root))


def test_prompt_key_rule_detected(root):
    path = v.agent_file("communication", root)
    text = path.read_text(encoding="utf-8").replace("Aucun coût public", "Discrétion")
    path.write_text(text, encoding="utf-8")
    assert any("règle clé absente « Aucun coût public »" in e for e in v.check_agent_prompts(root))


def test_prompt_brief_reference_detected(root):
    path = v.agent_file("catalogue", root)
    text = path.read_text(encoding="utf-8").replace("docs/08-agents/04_catalogue.md", "brief")
    path.write_text(text, encoding="utf-8")
    assert any("renvoi manquant vers docs/08-agents/04_catalogue.md" in e for e in v.check_agent_prompts(root))


# ------------------------------------------------------------------------------------------- 3. briefs
def test_brief_missing_rubric_detected(root):
    edit(v.brief_file("sourcing", root), "## 7. Plafond de dépense", "## 7. Budget")
    assert any("« ## 7. Plafond de dépense » manquante" in e for e in v.check_briefs(root))


def test_brief_tools_must_match_agent(root):
    edit(
        v.brief_file("qa-conformite", root),
        "Claude Code : Read, Grep, Glob, Bash",
        "Claude Code : Read, Grep, Glob, Bash, Write",
    )
    errors = v.check_briefs(root)
    assert any("12_qa-conformite.md : outils du brief" in e for e in errors)


def test_brief_missing_file_and_links(root):
    v.brief_file("acquisition", root).unlink()
    path = v.brief_file("catalogue", root)
    text = path.read_text(encoding="utf-8").replace(".claude/agents/catalogue.md", "agent")
    path.write_text(text, encoding="utf-8")
    errors = v.check_briefs(root)
    assert any("10_acquisition.md : brief manquant" in e for e in errors)
    assert any("renvoi manquant vers .claude/agents/catalogue.md" in e for e in errors)


# ------------------------------------------------------------------------------------------- 4. README
def test_readme_tools_must_match(root):
    edit(
        root / v.DOCS_DIR / "README.md",
        "| 12 | `qa-conformite` | `docs/08-agents/12_qa-conformite.md` | Read, Grep, Glob, Bash |",
        "| 12 | `qa-conformite` | `docs/08-agents/12_qa-conformite.md` | Read, Grep, Glob, Bash, Write |",
    )
    assert any("outils de qa-conformite" in e for e in v.check_readme_tools(root))


# ------------------------------------------------------------------------------------------- 5. validation
def test_validation_section_must_be_last(root):
    path = root / v.DOCS_DIR / "RUNBOOK.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n## Annexe\n\nTexte.\n", encoding="utf-8")
    assert any("RUNBOOK.md : la dernière section" in e for e in v.check_validation_sections(root=root))


def test_validation_section_needs_checkbox(root):
    path = root / v.DOCS_DIR / "rapports" / "README.md"
    text = path.read_text(encoding="utf-8")
    head, _ = text.rsplit("## Validation humaine requise", 1)
    path.write_text(head + "## Validation humaine requise\n\nRien.\n", encoding="utf-8")
    assert any("aucune case à cocher" in e for e in v.check_validation_sections(root=root))


def test_validation_heading_in_code_block_does_not_count(root):
    path = root / v.DOCS_DIR / "CARTE_REPO.md"
    text = path.read_text(encoding="utf-8")
    head, tail = text.rsplit("## Validation humaine requise", 1)
    path.write_text(head + "```\n## Validation humaine requise" + tail + "```\n", encoding="utf-8")
    assert any("CARTE_REPO.md : la dernière section" in e for e in v.check_validation_sections(root=root))


# ------------------------------------------------------------------------------------------- 6. RACI
def _raci_path(root: Path) -> Path:
    return root / v.DOCS_DIR / "ORGANIGRAMME.md"


def test_raci_two_accountables_detected(root):
    edit(
        _raci_path(root),
        "| L13 | Tracker des contacts | §2 |  | A | R |",
        "| L13 | Tracker des contacts | §2 | A | A | R |",
    )
    errors = v.check_raci(root)
    assert any("L13 a 2 « A »" in e for e in errors)


def test_raci_no_responsible_detected(root):
    edit(
        _raci_path(root),
        "| L13 | Tracker des contacts | §2 |  | A | R |",
        "| L13 | Tracker des contacts | §2 |  | A | C |",
    )
    assert any("L13 n'a aucun « R »" in e for e in v.check_raci(root))


def test_raci_invalid_code_and_sequence(root):
    edit(
        _raci_path(root),
        "| L13 | Tracker des contacts | §2 |  | A | R |",
        "| L13 | Tracker des contacts | §2 | X | A | R |",
    )
    edit(_raci_path(root), "| L14 |", "| L99 |")
    errors = v.check_raci(root)
    assert any("code invalide « X »" in e for e in errors)
    assert any("L99 hors séquence" in e for e in errors)


def test_raci_owner_count_must_match_text(root):
    edit(
        _raci_path(root),
        "| L13 | Tracker des contacts | §2 |  | A | R |",
        "| L13 | Tracker des contacts | §2 | A | C | R |",
    )
    assert any("les 33 lignes où la propriétaire est **A**" in e for e in v.check_raci(root))


def test_raci_readme_count_must_match(root):
    edit(root / v.DOCS_DIR / "README.md", "RACI agents × 61 livrables", "RACI agents × 60 livrables")
    assert any("RACI agents × 61 livrables" in e for e in v.check_raci(root))


def test_raci_columns_checked(root):
    edit(_raci_path(root), "| # | Livrable | BP | P | 01 |", "| # | Livrable | BP | PROP | 01 |")
    assert any("colonnes RACI" in e for e in v.check_raci(root))


def test_raci_cell_count_checked(root):
    edit(
        _raci_path(root),
        "| L13 | Tracker des contacts | §2 |  | A | R |",
        "| L13 | Tracker des contacts | §2 |  | A | R | R |",
    )
    assert any("L13 a 17 cellules" in e for e in v.check_raci(root))


# ------------------------------------------------------------------------------------------- 7. autonomie
def test_matrix_missing_label_detected(root):
    path = root / v.DOCS_DIR / "MATRICE_AUTONOMIE.md"
    text = path.read_text(encoding="utf-8")
    section_start = text.index("### A-12")
    patched = text[:section_start] + text[section_start:].replace("**Interdit**", "**Hors limites**", 1)
    path.write_text(patched, encoding="utf-8")
    assert any("fiche A-12 sans **Interdit**" in e for e in v.check_autonomy_matrix(root))


def test_matrix_missing_agent_detected(root):
    path = root / v.DOCS_DIR / "MATRICE_AUTONOMIE.md"
    edit(path, "### A-07 — Site et intégrations", "### Site et intégrations")
    edit(path, "| A-07 Site et intégrations |", "| Site et intégrations |")
    errors = v.check_autonomy_matrix(root)
    assert any("fiche A-07" in e for e in errors)
    assert any("A-07 absent du tableau" in e for e in errors)


def test_matrix_missing_level_detected(root):
    edit(root / v.DOCS_DIR / "MATRICE_AUTONOMIE.md", "| **4** |", "| 4 |")
    assert any("niveau **4**" in e for e in v.check_autonomy_matrix(root))


# ------------------------------------------------------------------------------------------- 8. chemins
def test_unknown_path_detected(root):
    path = root / v.DOCS_DIR / "RUNBOOK.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "## Validation humaine requise", "Voir `engine/pokeshop/inexistant.py`.\n\n## Validation humaine requise"
        ),
        encoding="utf-8",
    )
    assert any("engine/pokeshop/inexistant.py" in e for e in v.check_repo_paths(root))


def test_expected_path_and_subpath_accepted(root):
    path = root / v.DOCS_DIR / "RUNBOOK.md"
    extra = (
        "Voir `engine/pokeshop/stoploss.py` et `engine/pokeshop/importers/base.py`.\n\n## Validation humaine requise"
    )
    path.write_text(path.read_text(encoding="utf-8").replace("## Validation humaine requise", extra), encoding="utf-8")
    assert v.check_repo_paths(root) == []


def test_present_entry_must_exist(root):
    carte = root / v.DOCS_DIR / "CARTE_REPO.md"
    edit(carte, "| `docs/08-agents/RUNBOOK.md` |", "| `docs/08-agents/RUNBOOK_ABSENT.md` |")
    assert any("RUNBOOK_ABSENT.md » marqué présent" in e for e in v.check_repo_paths(root))


def test_empty_repo_map_detected(root):
    (root / v.DOCS_DIR / "CARTE_REPO.md").unlink()
    assert v.check_repo_paths(root) == ["CARTE_REPO.md : carte absente ou vide"]


def test_stale_expected_reported(root, capsys):
    carte = root / v.DOCS_DIR / "CARTE_REPO.md"
    edit(
        carte,
        "| `docs/08-agents/RUNBOOK.md` | Utilisation quotidienne | flotte-agents | propriétaire, 01 | présent |",
        "| `docs/08-agents/RUNBOOK.md` | Utilisation quotidienne | flotte-agents | propriétaire, 01 | attendu |",
    )
    assert "docs/08-agents/RUNBOOK.md" in v.stale_expected(root)
    assert v.main(root) == 0
    assert "désormais présent" in capsys.readouterr().out


def test_cited_paths_skip_patterns_and_commands(tmp_path):
    doc = tmp_path / "x.md"
    doc.write_text(
        "`docs/08-agents/rapports/AAAA-MM-JJ_x.md` `python docs/a.py` `config/pricing_rules.vN.yaml` `docs/ok.md`",
        encoding="utf-8",
    )
    assert set(v.cited_paths([doc])) == {"docs/ok.md"}


# ------------------------------------------------------------------------------------------- 9. secrets, données
@pytest.mark.parametrize(
    "leak",
    [
        "shpat_0123456789abcdef0123",
        "sk-ABCDEFGHIJKLMNOPQRSTUV",
        "AKIAABCDEFGHIJKLMNOP",
        "token = abcdefgh12345678",
        "CH93 0076 2011 6238 5295 7",
        "-----BEGIN RSA PRIVATE KEY-----",
    ],
)
def test_secret_patterns_detected(root, leak):
    path = v.agent_file("finance-pricing", root)
    path.write_text(path.read_text(encoding="utf-8") + f"\n{leak}\n", encoding="utf-8")
    assert any("finance-pricing.md : motif de secret" in e for e in v.check_no_secrets(root))


def test_env_variable_names_are_not_secrets():
    text = (REPO / v.DOCS_DIR / "BRIEF_COMMUN.md").read_text(encoding="utf-8")
    assert "SHOPIFY_ADMIN_TOKEN" in text
    assert v.check_no_secrets() == []


def test_real_ean_detected(root):
    path = root / v.DOCS_DIR / "RUNBOOK.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n3760000000000\n", encoding="utf-8")
    assert any("EAN-13 « 3760000000000 »" in e for e in v.check_no_fake_identifiers(root))


def test_test_gtin_accepted(root):
    path = root / v.DOCS_DIR / "RUNBOOK.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n2000000000008\n", encoding="utf-8")
    assert v.check_no_fake_identifiers(root) == []


def test_real_email_detected(root):
    path = root / v.DOCS_DIR / "modeles" / "MODELES_EMAILS_AGENTS.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nContact : jean.dupont@fournisseur.fr\n", encoding="utf-8")
    errors = v.check_no_fake_identifiers(root)
    assert any("jean.dupont@fournisseur.fr" in e for e in errors)


def test_example_email_and_agent_mention_accepted(root):
    path = root / v.DOCS_DIR / "RUNBOOK.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\ncontact@boutique.example.ch `@agent-sourcing`\n", encoding="utf-8"
    )
    assert v.check_no_fake_identifiers(root) == []


# ------------------------------------------------------------------------------------------- 10. stop-loss
def test_stoploss_threshold_removed_detected(root):
    path = root / v.DOCS_DIR / "BRIEF_COMMUN.md"
    text = path.read_text(encoding="utf-8").replace("45 j", "quarante-cinq jours")
    path.write_text(text, encoding="utf-8")
    assert any("« 45 j » absent" in e for e in v.check_stoploss_thresholds(root))


def test_stoploss_rearm_rule_required(root):
    path = v.agent_file("qa-conformite", root)
    text = re.sub(r"(?i)réarm", "relanc", path.read_text(encoding="utf-8"))
    path.write_text(text, encoding="utf-8")
    assert any("réarmement" in e for e in v.check_stoploss_thresholds(root))


def test_stoploss_missing_file_detected(root):
    (root / v.DOCS_DIR / "12_qa-conformite.md").unlink()
    assert any("12_qa-conformite.md : fichier manquant" in e for e in v.check_stoploss_thresholds(root))


# ------------------------------------------------------------------------------------------- 11. gabarits
def test_report_template_section_detected(root):
    edit(root / v.DOCS_DIR / "modeles" / "RAPPORT_AGENT.md", "## Sources datées", "## Sources")
    assert any("« ## Sources datées » manquante" in e for e in v.check_templates(root))


def test_registry_real_row_detected(root):
    path = root / v.DOCS_DIR / "modeles" / "REGISTRE_MANDAT.csv"
    header = path.read_text(encoding="utf-8").splitlines()[0]
    row = ",".join("x" for _ in header.split(","))
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")
    assert any("non marquée fictif=true" in e for e in v.check_templates(root))


def test_registry_missing_column_detected(root):
    path = root / v.DOCS_DIR / "modeles" / "REGISTRE_MANDAT.csv"
    path.write_text(path.read_text(encoding="utf-8").replace(",cle_idempotence", ""), encoding="utf-8")
    assert any("« cle_idempotence » manquante" in e for e in v.check_templates(root))


def test_email_model_without_non_engagement_detected(root):
    path = root / v.DOCS_DIR / "modeles" / "MODELES_EMAILS_AGENTS.md"
    text = path.read_text(encoding="utf-8")
    start = text.index("### MOD-04")
    end = text.index("### MOD-05")
    path.write_text(
        text[:start] + text[start:end].replace("{{PHRASE_NON_ENGAGEMENT}}", "") + text[end:], encoding="utf-8"
    )
    assert any("MOD-04 sans phrase de non-engagement" in e for e in v.check_templates(root))


def test_missing_templates_detected(root):
    for name in ("RAPPORT_AGENT.md", "PLAN_DISPATCH.md", "REGISTRE_MANDAT.csv"):
        (root / v.DOCS_DIR / "modeles" / name).unlink()
    errors = v.check_templates(root)
    assert any("RAPPORT_AGENT.md : fichier manquant" in e for e in errors)
    assert any("PLAN_DISPATCH.md : fichier manquant" in e for e in errors)
    assert any("REGISTRE_MANDAT.csv : fichier manquant" in e for e in errors)


# ------------------------------------------------------------------------------------------- main
def test_main_reports_errors(root, capsys):
    set_frontmatter(v.agent_file("sourcing", root), tools="Read, Bash")
    assert v.main(root) == 1
    out = capsys.readouterr().out
    assert "ERREUR" in out and "erreur(s)" in out
