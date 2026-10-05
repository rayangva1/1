"""Régénère les blocs « règles de prix » du jeu FICTIF ``db/seeds/fictif_seed.sql``.

Traçabilité exigée par SPEC §2.1 : chaque décision porte le ``rules_version`` des règles qui l'ont
calculée, et ces règles doivent figurer **en entier** dans ``pokeshop.pricing_rules`` (contenu et
sha256 du fichier). Ce script lit ``config/pricing_rules.v1.yaml``, recalcule avec le moteur
(:func:`pokeshop.pricing.decide_price`, :func:`pokeshop.pricing.basket_contribution`) les décisions
et la contribution de la commande FICTIVES, puis réécrit les blocs balisés
``-- >>> genere:<nom>`` … ``-- <<< genere:<nom>`` du seed. Rien d'autre n'est modifié.

Usage ::

    python db/seeds/regles_seed.py           # réécrit les blocs
    python db/seeds/regles_seed.py --check   # échoue si le seed n'est plus aligné sur les règles

``tests/test_seed_fictif.py`` exécute ``--check`` : toute modification des règles impose de relancer
ce script (sinon le jeu d'essai mentirait sur la version appliquée).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from pokeshop.models import BasketLine, VatMode  # noqa: E402
from pokeshop.pricing import basket_contribution, decide_price  # noqa: E402
from pokeshop.rules import load_rules  # noqa: E402

RULES_FILE = ROOT / "config" / "pricing_rules.v1.yaml"
RULES_SOURCE = "config/pricing_rules.v1.yaml"
SEED = ROOT / "db" / "seeds" / "fictif_seed.sql"
PROFILE = VatMode.EFFECTIVE

# Entrées FICTIVES des décisions de prix (coût rendu des lots FICTIFS, référence marché inventée).
DECISIONS = (
    ("FICTIF-DSP-ALPHA", Decimal("101.2345"), None),
    ("FICTIF-ETB-ALPHA", Decimal("41.1000"), Decimal("63.90")),
)
# Commande FICTIVE FICTIF-#1001 : 1 display à 154.90, port facturé 7.00.
ORDER = {"sku": "FICTIF-DSP-ALPHA", "price": Decimal("154.90"), "cost": Decimal("101.2345"), "shipping": Decimal("7.00")}

_BLOCK = re.compile(r"(-- >>> genere:(?P<name>[a-z_]+)[^\n]*\n)(?P<body>.*?)(-- <<< genere:(?P=name)\n)", re.S)


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def blocks() -> dict[str, str]:
    """Contenu SQL de chaque bloc généré (nom -> texte)."""
    raw = RULES_FILE.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    content = json.dumps(yaml.safe_load(raw.decode("utf-8")), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    rules = load_rules(RULES_FILE, PROFILE)
    if rules.content_sha256 != sha:  # pragma: no cover - garde-fou
        raise SystemExit("sha256 du fichier de règles incohérent avec le moteur")
    version = rules.rules_version
    out: dict[str, str] = {}
    out["regles"] = (
        "-- Règles appliquées par le moteur aux décisions FICTIVES ci-dessous : contenu COMPLET du fichier\n"
        f"-- {RULES_SOURCE} (JSON) et sha256 du fichier brut (même valeur que RuleSet.content_sha256).\n"
        "INSERT INTO pokeshop.pricing_rules (rules_version, status, vat_mode, effective_date, content_sha256, content, "
        "source_path, fictif)\n"
        f"VALUES ({_sql_text(version)}, 'PROPOSITION', NULL, {_sql_text(str(rules.effective_date))}, {_sql_text(sha)},\n"
        f"        {_sql_text(content)}::jsonb,\n"
        f"        {_sql_text(RULES_SOURCE)}, true);\n"
    )
    rows = []
    for key, cost, market in DECISIONS:
        d = decide_price(cost, rules.pricing, market, None, [])
        reasons = "{" + ",".join(r.value if hasattr(r, "value") else str(r) for r in d.reasons) + "}"
        note = "sans référence marché" if market is None else f"référence marché FICTIVE {market}"
        rows.append(
            f"          -- {key} : coût rendu {cost}, {note}.\n"
            f"          ({_sql_text(key)}, {_sql_text(d.inputs_hash)}, {_sql_text(d.status.value)}, "
            f"{_sql_text(reasons)}::text[],\n"
            f"           {cost}::numeric, {d.floor_price}::numeric, {d.recommended_price}::numeric, "
            f"{d.contribution_chf}::numeric, {d.contribution_pct}::numeric)"
        )
    out["decisions"] = (
        "INSERT INTO pokeshop.replacement_costs (product_id, supplier_id, offer_id, unit_cost_chf, source_ts, rules_version, fictif)\n"
        f"SELECT p.product_id, 'fictif_grossiste_a', o.offer_id, 99.8000, '2026-10-04 06:00+02', {_sql_text(version)}, true\n"
        "  FROM pokeshop.products p JOIN pokeshop.supplier_offers o ON o.supplier_sku = 'FICTIF-A-001'\n"
        " WHERE p.public_sku = 'FICTIF-DSP-ALPHA';\n"
        "\n"
        "INSERT INTO pokeshop.price_decisions (product_id, rules_version, inputs_hash, status, reasons, landed_cost_chf, "
        "floor_price_chf,\n"
        "    profitable_price_chf, recommended_price_chf, evaluated_price_chf, contribution_chf, contribution_pct, fictif)\n"
        f"SELECT p.product_id, {_sql_text(version)}, v.h, v.status::pokeshop.decision_status, v.reasons, v.cost, v.floor, "
        "v.floor, v.reco, v.reco,\n"
        "       v.contrib, v.pct, true\n"
        "  FROM (VALUES\n"
        f"          -- pokeshop.pricing.decide_price(coût, règles {version} profil {PROFILE.value}, marché) : coûts et "
        "marché FICTIFS.\n" + ",\n".join(rows) + "\n"
        "       ) AS v(public_sku, h, status, reasons, cost, floor, reco, contrib, pct)\n"
        "  JOIN pokeshop.products p ON p.public_sku = v.public_sku;\n"
    )
    basket = basket_contribution(
        [BasketLine(sku=ORDER["sku"], qty=1, unit_price_ttc=ORDER["price"], unit_cost=ORDER["cost"])],
        rules.pricing,
        ORDER["shipping"],
    )
    total = ORDER["price"] + ORDER["shipping"]
    out["commande"] = (
        "INSERT INTO pokeshop.orders (shop_order_ref, status, paid_at, goods_ttc_chf, discount_ttc_chf, shipping_charged_ttc_chf,\n"
        "                             total_paid_ttc_chf, customer_ref, contribution_chf, rules_version, inputs_hash, fictif) VALUES\n"
        f"    -- pokeshop.pricing.basket_contribution (règles {version}, port facturé {ORDER['shipping']}, coût FICTIF).\n"
        f"    ('FICTIF-#1001', 'PAYEE', '2026-10-04 12:00+02', {ORDER['price']}, 0, {ORDER['shipping']}, {total}, "
        f"'FICTIF-client-0001', {basket.contribution_chf}, {_sql_text(version)},\n"
        f"     {_sql_text(basket.inputs_hash)}, true);\n"
    )
    out["proposition"] = (
        "INSERT INTO pokeshop.purchase_proposals (generated_at, status, supplier_id, total_cost_chf, budget_available_chf, "
        "budget_remaining_chf,\n"
        "                                         rules_version, inputs_hash, skipped, fictif)\n"
        "-- inputs_hash : identifiant FICTIF de la proposition (candidats d'essai non conservés).\n"
        f"VALUES ('2026-10-04 07:00+02', 'PROPOSITION_A_VALIDER', 'fictif_grossiste_a', 607.41, 2400.00, 1792.59, "
        f"{_sql_text(version)},\n"
        "        '4768b8ca1ca1b7322c1eeffa45acce7668922227efb5764b17c807a95add8a91',\n"
        "        '[{\"product_key\": \"FICTIF-ETB-BETA\", \"reason\": \"IDENTITY_INCOMPLETE\"}]', true);\n"
    )
    return out


def render(text: str) -> str:
    """Seed avec les blocs régénérés (erreur si un bloc attendu manque)."""
    generated = blocks()
    seen: set[str] = set()

    def repl(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in generated:
            raise SystemExit(f"bloc inconnu dans le seed : {name}")
        seen.add(name)
        return match.group(1) + generated[name] + match.group(4)

    result = _BLOCK.sub(repl, text)
    missing = set(generated) - seen
    if missing:
        raise SystemExit(f"blocs absents du seed : {', '.join(sorted(missing))}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blocs « règles de prix » du seed FICTIF.")
    parser.add_argument("--check", action="store_true", help="échoue si le seed n'est pas à jour")
    args = parser.parse_args(argv)
    current = SEED.read_text(encoding="utf-8")
    expected = render(current)
    if args.check:
        if current != expected:
            print("db/seeds/fictif_seed.sql n'est plus aligné sur config/pricing_rules.v1.yaml : "
                  "relancer python db/seeds/regles_seed.py")
            return 1
        print("seed FICTIF aligné sur les règles.")
        return 0
    SEED.write_text(expected, encoding="utf-8")
    print(f"blocs régénérés dans {SEED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
