"""Tests du catalogue central : GTIN, normalisations, table d'extensions, rapprochement.

Tous les GTIN utilisés sont FICTIFS (plage 2xx « restricted circulation ») ou calculés.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from pokeshop import catalog as cat
from pokeshop.catalog import (
    ACCESSORY_FORMATS,
    CARD_PRODUCT_FORMATS,
    FORMAT_BUDGET_CATEGORY,
    FORMAT_LABELS_FR,
    NO_EXTENSION,
    CatalogError,
    CatalogIndex,
    CatalogProduct,
    ExtensionEntry,
    ExtensionTable,
    IdentityIssue,
    Language,
    MatchStatus,
    ProductFormat,
    SupplierLink,
    booster_count,
    clean_gtin,
    expected_language_for,
    fictitious_gtin13,
    fold,
    gtin_check_digit,
    is_accessory,
    is_case_level_gtin,
    is_fictitious_gtin,
    load_extension_table,
    match_offer_to_product,
    normalize_content,
    normalize_extension,
    normalize_format,
    normalize_gtin,
    normalize_identity,
    normalize_language,
    product_identity_key,
    product_title_fr,
    validate_gtin,
)
from pokeshop.models import ProductIdentity, SupplierOffer

ROOT = Path(__file__).resolve().parents[1]
REAL_TABLE_PATH = ROOT / "data" / "extensions_aliases.yaml"
FICTIF_TABLE_PATH = ROOT / "data" / "samples" / "FICTIF_extensions_aliases.yaml"
NOW = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)


def gtin_with_check(payload: str) -> str:
    """GTIN complet à partir de sa charge utile (calcul indépendant du module)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(payload)))
    return payload + str((10 - total % 10) % 10)


@pytest.fixture(scope="module")
def table() -> ExtensionTable:
    return ExtensionTable.load([REAL_TABLE_PATH, FICTIF_TABLE_PATH])


# ------------------------------------------------------------------------ GTIN


class TestGtin:
    def test_check_digit_matches_independent_formula(self) -> None:
        rng = random.Random(20261004)
        for length in (7, 11, 12, 13):
            for _ in range(200):
                payload = "".join(rng.choice("0123456789") for _ in range(length))
                assert payload + str(gtin_check_digit(payload)) == gtin_with_check(payload)

    @pytest.mark.parametrize("length", [8, 12, 13, 14])
    def test_valid_lengths(self, length: int) -> None:
        payload = "2" + "0" * (length - 3) + "7"
        assert validate_gtin(gtin_with_check(payload))

    @pytest.mark.parametrize("length", [1, 7, 9, 10, 11, 15, 18])
    def test_invalid_lengths(self, length: int) -> None:
        payload = "2" * (length - 1) if length > 1 else ""
        code = gtin_with_check(payload) if payload else "2"
        assert not validate_gtin(code)

    def test_every_single_digit_error_is_detected(self) -> None:
        good = fictitious_gtin13(123456)
        for pos in range(len(good)):
            for digit in "0123456789":
                if digit == good[pos]:
                    continue
                bad = good[:pos] + digit + good[pos + 1 :]
                assert not validate_gtin(bad), bad

    def test_adjacent_transpositions_detected_unless_difference_is_five(self) -> None:
        good = fictitious_gtin13(918273645)
        for pos in range(len(good) - 1):
            a, b = good[pos], good[pos + 1]
            if a == b:
                continue
            swapped = good[:pos] + b + a + good[pos + 2 :]
            assert validate_gtin(swapped) == (abs(int(a) - int(b)) == 5)

    @pytest.mark.parametrize(
        "code",
        [None, "", "   ", "abcdefghijklm", "200000000001X", "0000000000000", "00000000", True, False, "２０００００００００００１５"],
    )
    def test_rejects_garbage(self, code: object) -> None:
        assert not validate_gtin(code)  # type: ignore[arg-type]
        assert normalize_gtin(code) is None  # type: ignore[arg-type]

    def test_accepts_spaces_hyphens_and_int(self) -> None:
        good = fictitious_gtin13(42)
        assert validate_gtin(f" {good[:1]} {good[1:7]}-{good[7:]} ")
        assert validate_gtin(int(good))
        assert clean_gtin(f"{good[:6]} {good[6:]}") == good
        assert clean_gtin(None) is None
        assert clean_gtin(True) is None  # type: ignore[arg-type]

    def test_check_digit_rejects_non_digits(self) -> None:
        with pytest.raises(CatalogError):
            gtin_check_digit("12a4")

    def test_normalize_equivalent_forms(self) -> None:
        upc = gtin_with_check("02000000001")  # GTIN-12
        assert len(upc) == 12
        assert normalize_gtin(upc) == "0" + upc
        assert normalize_gtin("0" + upc) == "0" + upc
        assert normalize_gtin("00" + upc) == "0" + upc
        gtin8 = gtin_with_check("2000001")
        assert normalize_gtin(gtin8) == gtin8
        assert normalize_gtin("000000" + gtin8) == gtin8
        assert normalize_gtin("00000" + gtin8) == gtin8
        ean = fictitious_gtin13(7)
        assert normalize_gtin(ean) == ean
        assert normalize_gtin("0" + ean) == ean

    def test_normalize_is_idempotent(self) -> None:
        rng = random.Random(7)
        for _ in range(300):
            length = rng.choice([7, 11, 12, 13])
            code = gtin_with_check("".join(rng.choice("0123456789") for _ in range(length)))
            norm = normalize_gtin(code)
            if norm is not None:
                assert normalize_gtin(norm) == norm

    def test_case_level_gtin(self) -> None:
        case = gtin_with_check("1" + fictitious_gtin13(5)[:-1])
        assert len(case) == 14
        assert is_case_level_gtin(case)
        assert normalize_gtin(case) == case
        assert not is_case_level_gtin(fictitious_gtin13(5))
        assert not is_case_level_gtin("0" + fictitious_gtin13(5))
        assert not is_case_level_gtin("bad")

    def test_fictitious_gtin(self) -> None:
        codes = {fictitious_gtin13(i) for i in range(500)}
        assert len(codes) == 500
        for code in codes:
            assert len(code) == 13 and code.startswith("200")
            assert validate_gtin(code) and is_fictitious_gtin(code)
        assert fictitious_gtin13(0) == gtin_with_check("200000000000")
        assert fictitious_gtin13(999_999_999).startswith("200999999999")
        assert not is_fictitious_gtin(gtin_with_check("300000000000"))
        assert not is_fictitious_gtin(None)

    @pytest.mark.parametrize("seq", [-1, 1_000_000_000, True, "1"])
    def test_fictitious_gtin_rejects_bad_seq(self, seq: object) -> None:
        with pytest.raises(CatalogError):
            fictitious_gtin13(seq)  # type: ignore[arg-type]


# --------------------------------------------------------------------- langue


class TestLanguage:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("FR", "FR"), ("fr", "FR"), ("Français", "FR"), ("francais", "FR"), ("FRANÇAISE", "FR"),
            ("VF", "FR"), ("Version française", "FR"), ("fr-CH", "FR"), ("French", "FR"), ("FRA", "FR"),
            ("EN", "EN"), ("ENG", "EN"), ("Anglais", "EN"), ("english", "EN"), ("VA", "EN"),
            ("JP", "JP"), ("JAP", "JP"), ("Japonais", "JP"), ("ja", "JP"), ("Japanese", "JP"), ("JPN", "JP"),
            ("DE", "DE"), ("Allemand", "DE"), ("Deutsch", "DE"), ("GER", "DE"),
            ("IT", "IT"), ("Italien", "IT"), ("italiano", "IT"),
            ("n/a", "NA"), ("Sans objet", "NA"), ("multilingue", "NA"),
            ("Display 36 boosters – FR", "FR"), ("Booster japonais", "JP"), ("ETB (ENG)", "EN"),
            ("FR/EN", "UNKNOWN"), ("FR + JP", "UNKNOWN"), ("Français / Anglais", "UNKNOWN"),
            ("VO", "UNKNOWN"), ("", "UNKNOWN"), ("   ", "UNKNOWN"), (None, "UNKNOWN"), ("Espagnol", "UNKNOWN"),
            ("Coffret de collection", "UNKNOWN"), ("klingon", "UNKNOWN"), ("-", "UNKNOWN"),
        ],
    )
    def test_table(self, raw: str | None, expected: str) -> None:
        assert normalize_language(raw) == expected

    def test_returns_enum_comparable_to_str(self) -> None:
        assert normalize_language("Français") is Language.FR
        assert normalize_language("Français") == "FR"

    @pytest.mark.parametrize("lang", list(Language))
    def test_idempotent(self, lang: Language) -> None:
        assert normalize_language(lang.value) is lang
        assert normalize_language(lang) is lang

    def test_lowercase_two_letter_words_inside_text_are_not_codes(self) -> None:
        assert normalize_language("coffret de luxe it") == "UNKNOWN"


# --------------------------------------------------------------------- format


class TestFormat:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Display", "DISPLAY"), ("display 36 boosters", "DISPLAY"), ("Booster Box", "DISPLAY"),
            ("Boîte de 36 boosters", "DISPLAY"),
            ("Demi-display 18 boosters", "HALF_DISPLAY"), ("Half display", "HALF_DISPLAY"),
            ("ETB", "ETB"), ("Elite Trainer Box", "ETB"), ("Coffret Dresseur d'Élite", "ETB"),
            ("coffret dresseur d’élite", "ETB"), ("Coffret ETB", "ETB"), ("ETB + 65 sleeves", "ETB"),
            ("Bundle", "BUNDLE"), ("Bundle 6 boosters", "BUNDLE"), ("Lot de boosters", "BUNDLE"),
            ("Tripack", "TRIPACK"), ("Tri-pack", "TRIPACK"), ("Blister 3 boosters", "TRIPACK"),
            ("Coffret", "COLLECTION_BOX"), ("Collection Box", "COLLECTION_BOX"),
            ("Coffret Premium", "COLLECTION_BOX"), ("Collection Classeur 30e anniversaire", "COLLECTION_BOX"),
            ("Mini-Tin", "TIN"), ("Pokébox", "TIN"), ("Tin", "TIN"),
            ("Booster", "BOOSTER"), ("booster pack", "BOOSTER"), ("Sachet", "BOOSTER"),
            ("Protège-cartes", "SLEEVES"), ("Sleeves", "SLEEVES"), ("Accessoire protège-cartes", "SLEEVES"),
            ("Classeur 9 cases", "BINDER"), ("Portfolio", "BINDER"),
            ("Deck box", "DECK_BOX"), ("Boîte de rangement", "DECK_BOX"),
            ("Tapis de jeu", "PLAYMAT"), ("Playmat", "PLAYMAT"),
            ("Accessoire", "ACCESSORY"), ("Toploader", "ACCESSORY"),
            ("Blister", "UNKNOWN"), ("Pack", "UNKNOWN"), ("Pack de 6 boosters", "UNKNOWN"),
            ("Display ETB", "UNKNOWN"), ("Bundle ou tripack", "UNKNOWN"), ("Sleeves + deck box", "UNKNOWN"),
            ("", "UNKNOWN"), (None, "UNKNOWN"), ("Martin", "UNKNOWN"), ("Kit", "UNKNOWN"),
        ],
    )
    def test_table(self, raw: str | None, expected: str) -> None:
        assert normalize_format(raw) == expected

    @pytest.mark.parametrize("fmt", list(ProductFormat))
    def test_idempotent(self, fmt: ProductFormat) -> None:
        assert normalize_format(fmt.value) is fmt
        assert normalize_format(fmt) is fmt

    def test_partition_and_labels(self) -> None:
        known = set(ProductFormat) - {ProductFormat.UNKNOWN}
        assert ACCESSORY_FORMATS | CARD_PRODUCT_FORMATS == known
        assert not ACCESSORY_FORMATS & CARD_PRODUCT_FORMATS
        assert set(FORMAT_LABELS_FR) == set(ProductFormat)
        assert set(FORMAT_BUDGET_CATEGORY) == set(ProductFormat)
        # BP §1 : displays, ETB, bundles et tripacks, coffrets, accessoires.
        assert {v for v in FORMAT_BUDGET_CATEGORY.values() if v} == {
            "displays", "etb", "bundles_tripacks", "coffrets", "accessoires"
        }

    def test_budget_categories_match_pilot_basket(self) -> None:
        import csv

        path = ROOT / "docs" / "02-sourcing" / "PANIER_PILOTE.csv"
        if not path.exists():
            pytest.skip("panier pilote absent")
        with path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            fmt = normalize_format(row["designation_attendue"])
            if fmt is ProductFormat.UNKNOWN:
                continue  # ex. « Tripack ou bundle … » : volontairement ambigu
            assert FORMAT_BUDGET_CATEGORY[fmt] == row["categorie_budget"], row["designation_attendue"]

    def test_is_accessory_and_expected_language(self) -> None:
        assert is_accessory("Protège-cartes") and is_accessory(ProductFormat.BINDER) and is_accessory("DECK_BOX")
        assert not is_accessory("Display") and not is_accessory(None) and not is_accessory("??")
        assert expected_language_for("Sleeves") == "NA"
        assert expected_language_for(ProductFormat.ETB) == "FR"
        assert expected_language_for(None) == "FR"


# -------------------------------------------------------------------- contenu


class TestContent:
    @pytest.mark.parametrize(
        ("raw", "expected", "count"),
        [
            ("36 boosters", "36 BOOSTERS", 36),
            ("x36 Boosters", "36 BOOSTERS", 36),
            ("36x boosters", "36 BOOSTERS", 36),
            ("36 × booster", "36 BOOSTERS", 36),
            ("Boosters x 6", "6 BOOSTERS", 6),
            ("9 boosters + accessoires", "9 BOOSTERS", 9),
            ("2 boosters (selon annonce)", "2 BOOSTERS", 2),
            ("1 booster + carte promo", "1 BOOSTER", 1),
            ("100 protège-cartes", "100 PROTEGE CARTES", None),
            ("classeur + 5 boosters", "5 BOOSTERS", 5),
            ("Display 36 boosters (6 x 6 boosters)", "DISPLAY 36 BOOSTERS 6 X 6 BOOSTERS", None),
            ("  ", None, None),
            (None, None, None),
            ("0 booster", "0 BOOSTER", None),
        ],
    )
    def test_table(self, raw: str | None, expected: str | None, count: int | None) -> None:
        assert normalize_content(raw) == expected
        assert booster_count(raw) == count

    @pytest.mark.parametrize("raw", ["36 boosters", "9 boosters + accessoires", "100 protège-cartes", "Plateau + dés"])
    def test_idempotent(self, raw: str) -> None:
        once = normalize_content(raw)
        assert normalize_content(once) == once


# ----------------------------------------------------------------- extensions


class TestExtensionTable:
    def test_real_table_loads_with_dated_https_sources(self) -> None:
        tbl = ExtensionTable.load(REAL_TABLE_PATH)
        assert tbl.codes == {"ME02.5", "ME03", "ME04", "ME05", "ME06", "ANNIV30"}
        for entry in tbl.entries:
            assert not entry.fictif
            assert entry.sources, entry.code
            for src in entry.sources:
                assert src.url.startswith("https://")
                assert src.consulte_le.isoformat() == "2026-10-04"
            assert entry.release_date_fr is not None

    def test_real_table_has_no_fictitious_entry(self) -> None:
        text = REAL_TABLE_PATH.read_text(encoding="utf-8")
        assert "fictif: true" not in text
        assert "FICTIF_" not in yaml.safe_load(text).__repr__()

    def test_default_table_is_real_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(cat.EXTENSIONS_ENV_VAR, raising=False)
        assert load_extension_table().codes == ExtensionTable.load(REAL_TABLE_PATH).codes
        assert cat.DEFAULT_EXTENSIONS_PATH == REAL_TABLE_PATH

    @pytest.mark.parametrize(
        ("raw", "code"),
        [
            ("Nuit Noire", "ME05"), ("NUIT-NOIRE", "ME05"), ("Méga-Évolution – Nuit Noire", "ME05"),
            ("Display Méga-Évolution Nuit Noire FR", "ME05"), ("ME05", "ME05"), ("me05", "ME05"),
            ("Règne Delta", "ME06"), ("regne delta", "ME06"), ("Chaos Ascendant", "ME04"), ("Chaos Rising", "ME04"),
            ("Équilibre Parfait", "ME03"), ("Héros Transcendants", "ME02.5"), ("ME02.5", "ME02.5"),
            ("30ᵉ Anniversaire", "ANNIV30"), ("30e anniversaire", "ANNIV30"), ("30ème Anniversaire", "ANNIV30"),
            ("Coffret 30ᵉ Anniversaire Nymphali-ex", "ANNIV30"),
            ("Extension Fictive Alpha", "FICTIF_ALPHA"), ("FICT-B", "FICTIF_BETA"),
        ],
    )
    def test_known_aliases(self, table: ExtensionTable, raw: str, code: str) -> None:
        assert table.normalize(raw) == code
        assert table.normalize(code) == code  # le code est toujours un alias

    @pytest.mark.parametrize("raw", ["Méga-Évolution", "Mega Evolution", "Ecarlate et Violet", "", None, "Nuit", "Noire"])
    def test_unknown_or_partial_is_none(self, table: ExtensionTable, raw: str | None) -> None:
        assert table.normalize(raw) is None

    def test_two_extensions_in_label_is_ambiguous(self, table: ExtensionTable) -> None:
        match = table.match("Lot Nuit Noire / Règne Delta")
        assert match.code is None and match.ambiguous
        assert set(match.candidates) == {"ME05", "ME06"}

    def test_name_and_get(self, table: ExtensionTable) -> None:
        assert table.name_fr("ME05") == "Méga-Évolution – Nuit Noire"
        assert table.name_fr("NOPE") is None
        assert table.get("ME06") is not None and table.get("X") is None
        assert len(table.sources) == 2

    def test_merged(self) -> None:
        real = ExtensionTable.load(REAL_TABLE_PATH)
        fictif = ExtensionTable.load(FICTIF_TABLE_PATH)
        merged = real.merged(fictif)
        assert merged.codes == real.codes | fictif.codes
        with pytest.raises(CatalogError, match="code en double"):
            real.merged(real)

    @pytest.mark.parametrize(
        ("entries", "message"),
        [
            ([{"code": "FICTIF_A", "name_fr": "A", "fictif": True}, {"code": "FICTIF_A", "name_fr": "B", "fictif": True}],
             "code en double"),
            ([{"code": "FICTIF_A", "name_fr": "Même", "fictif": True}, {"code": "FICTIF_B", "name_fr": "même", "fictif": True}],
             "partagé"),
            ([{"code": "REAL1", "name_fr": "Réelle sans source"}], "sans source"),
            ([{"code": "ALPHA", "name_fr": "Fictive", "fictif": True}], "FICTIF_"),
            ([{"code": "FICTIF_X", "name_fr": "X", "sources": [{"url": "https://exemple.invalid/x", "consulte_le": "2026-10-04"}]}],
             "réservé aux entrées fictives"),
            ([{"code": "FICTIF_X", "name_fr": "X", "fictif": True, "aliases": ["Aucune"]}], "alias réservé"),
            ([{"code": NO_EXTENSION, "name_fr": "X", "fictif": True}], "réservé"),
        ],
    )
    def test_invalid_tables(self, entries: list[dict[str, object]], message: str) -> None:
        with pytest.raises(CatalogError, match=message):
            ExtensionTable.from_data({"extensions": entries})

    @pytest.mark.parametrize(
        "data",
        [
            None,
            {"extensions": "x"},
            {"extensions": [{"code": "bad code!", "name_fr": "x", "fictif": True}]},
            {"extensions": [{"code": "R1", "name_fr": "x", "sources": [{"url": "http://insecure", "consulte_le": "2026-10-04"}]}]},
            {"extensions": [{"code": "R1", "name_fr": "x", "unexpected": 1}]},
        ],
    )
    def test_invalid_documents(self, data: object) -> None:
        with pytest.raises(CatalogError):
            ExtensionTable.from_data(data)

    def test_load_errors(self, tmp_path: Path) -> None:
        with pytest.raises(CatalogError, match="lecture impossible"):
            ExtensionTable.load(tmp_path / "absent.yaml")
        bad = tmp_path / "bad.yaml"
        bad.write_text("extensions: [\n", encoding="utf-8")
        with pytest.raises(CatalogError):
            ExtensionTable.load(bad)
        with pytest.raises(CatalogError, match="introuvable"):
            load_extension_table(tmp_path / "absent.yaml")

    def test_env_var_and_cache_invalidation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        path = tmp_path / "ext.yaml"
        path.write_text(
            yaml.safe_dump({"extensions": [{"code": "FICTIF_ONE", "name_fr": "Une", "fictif": True}]}), encoding="utf-8"
        )
        monkeypatch.setenv(cat.EXTENSIONS_ENV_VAR, f"{path}{__import__('os').pathsep}{FICTIF_TABLE_PATH}")
        first = load_extension_table()
        assert "FICTIF_ONE" in first.codes and "FICTIF_ALPHA" in first.codes
        assert load_extension_table() is first  # cache
        import os
        import time

        path.write_text(
            yaml.safe_dump({"extensions": [{"code": "FICTIF_TWO", "name_fr": "Deux", "fictif": True}]}), encoding="utf-8"
        )
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
        time.sleep(0)
        second = load_extension_table()
        assert "FICTIF_TWO" in second.codes and "FICTIF_ONE" not in second.codes

    def test_entry_folded_aliases_deduplicated(self) -> None:
        entry = ExtensionEntry(code="FICTIF_Z", name_fr="Zêta", aliases=("zeta", "ZÊTA", "Z-ETA"), fictif=True)
        assert entry.folded_aliases() == ("fictif z", "zeta", "z eta")

    def test_normalize_extension_accessory_rules(self, table: ExtensionTable) -> None:
        assert normalize_extension(None, table, fmt="Sleeves") == NO_EXTENSION
        assert normalize_extension("", table, fmt=ProductFormat.BINDER) == NO_EXTENSION
        assert normalize_extension("Aucune", table, fmt="Deck box") == NO_EXTENSION
        assert normalize_extension(NO_EXTENSION, table, fmt="Sleeves") == NO_EXTENSION
        assert normalize_extension("Nuit Noire", table, fmt="Classeur") == "ME05"
        assert normalize_extension(None, table, fmt="Display") is None
        assert normalize_extension(NO_EXTENSION, table, fmt="Display") is None
        assert normalize_extension("Aucune", table, fmt="ETB") is None

    def test_fold(self) -> None:
        assert fold("Méga-Évolution – Nuit Noire") == "mega evolution nuit noire"
        assert fold("30ᵉ Anniversaire") == "30e anniversaire"
        assert fold("  --  ") == ""


# ------------------------------------------------------------------- identité


def ident(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "gtin": fictitious_gtin13(1),
        "language": "Français",
        "extension": "Fictive Alpha",
        "format": "Display",
        "content": "36 boosters",
        "sealed": True,
    }
    base.update(kw)
    return base


class TestIdentity:
    def test_complete_identity_key(self, table: ExtensionTable) -> None:
        norm = normalize_identity(**ident(), table=table)  # type: ignore[arg-type]
        assert norm.is_complete and not norm.issues
        assert norm.key == f"{fictitious_gtin13(1)}|FR|FICTIF_ALPHA|DISPLAY|36 BOOSTERS|SEALED"
        assert norm.format is ProductFormat.DISPLAY

    @pytest.mark.parametrize(
        ("change", "issue"),
        [
            ({"gtin": None}, IdentityIssue.MISSING_GTIN),
            ({"gtin": "  "}, IdentityIssue.MISSING_GTIN),
            ({"gtin": "2000000000009"}, IdentityIssue.INVALID_GTIN),
            ({"language": "VO"}, IdentityIssue.UNKNOWN_LANGUAGE),
            ({"language": None}, IdentityIssue.UNKNOWN_LANGUAGE),
            ({"language": "n/a"}, IdentityIssue.LANGUAGE_NOT_APPLICABLE),
            ({"extension": "Inconnue"}, IdentityIssue.UNKNOWN_EXTENSION),
            ({"extension": None}, IdentityIssue.UNKNOWN_EXTENSION),
            ({"extension": "Fictive Alpha / Fictive Bêta"}, IdentityIssue.AMBIGUOUS_EXTENSION),
            ({"format": "Blister"}, IdentityIssue.UNKNOWN_FORMAT),
            ({"content": None}, IdentityIssue.MISSING_CONTENT),
            ({"sealed": None}, IdentityIssue.UNKNOWN_SEALED),
            ({"sealed": False}, IdentityIssue.NOT_SEALED),
        ],
    )
    def test_issues(self, table: ExtensionTable, change: dict[str, object], issue: IdentityIssue) -> None:
        norm = normalize_identity(**ident(**change), table=table)  # type: ignore[arg-type]
        assert issue in norm.issues
        assert not norm.is_complete
        assert issue in cat.IDENTITY_ISSUE_LABELS_FR

    def test_case_level_gtin_is_an_issue(self, table: ExtensionTable) -> None:
        case = gtin_with_check("1" + fictitious_gtin13(1)[:-1])
        norm = normalize_identity(**ident(gtin=case), table=table)  # type: ignore[arg-type]
        assert norm.issues == (IdentityIssue.CASE_LEVEL_GTIN,)

    def test_accessory_language_is_always_na(self, table: ExtensionTable) -> None:
        keys = {
            normalize_identity(
                gtin=fictitious_gtin13(9), language=lang, extension=None, format="Protège-cartes",
                content="100 protège-cartes", sealed=True, table=table,
            ).key
            for lang in ("FR", "multilingue", None, "Anglais", "VO")
        }
        assert keys == {f"{fictitious_gtin13(9)}|NA|SANS_EXTENSION|SLEEVES|100 PROTEGE CARTES|SEALED"}

    def test_key_is_stable_across_spellings(self, table: ExtensionTable) -> None:
        a = product_identity_key(ident(), table)  # type: ignore[arg-type]
        b = product_identity_key(
            ident(gtin="0" + fictitious_gtin13(1), language="VF", extension="FICT-A", format="Booster Box", content="x36 Boosters"),
            table,  # type: ignore[arg-type]
        )
        assert a == b

    def test_key_differs_on_each_element(self, table: ExtensionTable) -> None:
        base = product_identity_key(ident(), table)  # type: ignore[arg-type]
        for change in (
            {"gtin": fictitious_gtin13(2)}, {"language": "JP"}, {"extension": "Fictive Bêta"},
            {"format": "ETB"}, {"content": "18 boosters"}, {"sealed": False},
        ):
            assert product_identity_key(ident(**change), table) != base, change  # type: ignore[arg-type]

    def test_key_from_offer_and_identity(self, table: ExtensionTable) -> None:
        offer = SupplierOffer(
            supplier_id="FICTIF_GROSSISTE_A", supplier_sku="FICTIF-1", source_ts=NOW, raw_ref="t#1",
            gtin=fictitious_gtin13(1), language="fr", extension="FICTIF_ALPHA", format="DISPLAY",
            content="36 BOOSTERS", sealed=True,
        )
        assert product_identity_key(offer, table) == product_identity_key(ident(), table)  # type: ignore[arg-type]
        assert product_identity_key(offer.identity(), table) == product_identity_key(offer, table)

    def test_normalized_key_is_fixed_point(self, table: ExtensionTable) -> None:
        norm = normalize_identity(**ident(language="VF", format="Booster Box"), table=table)  # type: ignore[arg-type]
        assert product_identity_key(norm.identity, table) == norm.key

    def test_key_rejects_unknown_fields_and_types(self, table: ExtensionTable) -> None:
        with pytest.raises(CatalogError):
            product_identity_key({"gtin": "x", "price": 3}, table)
        with pytest.raises(TypeError):
            product_identity_key(42, table)  # type: ignore[arg-type]

    def test_title(self, table: ExtensionTable) -> None:
        norm = normalize_identity(**ident(), table=table)  # type: ignore[arg-type]
        assert product_title_fr(norm.identity, table) == "Display Extension Fictive Alpha – FR"
        etb = normalize_identity(**ident(format="ETB", content="9 boosters"), table=table)  # type: ignore[arg-type]
        assert product_title_fr(etb.identity, table) == "Coffret Dresseur d'Élite (ETB) Extension Fictive Alpha – FR"
        sleeves = normalize_identity(
            gtin=fictitious_gtin13(3), language=None, extension=None, format="Sleeves", content="65", sealed=True, table=table
        )
        assert product_title_fr(sleeves.identity, table) == "Protège-cartes"
        incomplete = normalize_identity(**ident(gtin=None), table=table)  # type: ignore[arg-type]
        assert product_title_fr(incomplete.identity, table) is None
        orphan = ProductIdentity(
            gtin=fictitious_gtin13(1), language="FR", extension="NOT_IN_TABLE", format="DISPLAY", content="X", sealed=True
        )
        assert product_title_fr(orphan, table) is None


# -------------------------------------------------------------- rapprochement


def product(pid: str, links: tuple[tuple[str, str], ...] = (), **kw: object) -> CatalogProduct:
    norm_input = ident(**kw)
    return CatalogProduct(
        product_id=pid,
        identity=ProductIdentity(**norm_input),  # type: ignore[arg-type]
        supplier_links=tuple(SupplierLink(supplier_id=s, supplier_sku=k) for s, k in links),
    )


def offer(sku: str = "FICTIF-1", supplier: str = "FICTIF_GROSSISTE_A", **kw: object) -> SupplierOffer:
    data = ident(**kw)
    return SupplierOffer(
        supplier_id=supplier, supplier_sku=sku, source_ts=NOW, raw_ref=f"test#{sku}",
        **data,  # type: ignore[arg-type]
    )


class TestMatching:
    @pytest.fixture
    def catalog(self, table: ExtensionTable) -> CatalogIndex:
        return CatalogIndex(
            [
                product("P-DISPLAY", links=(("FICTIF_GROSSISTE_A", "FICTIF-1"),)),
                product("P-ETB", gtin=fictitious_gtin13(2), format="ETB", content="9 boosters + accessoires"),
                product("P-SLEEVES", gtin=fictitious_gtin13(3), language=None, extension=None, format="Sleeves",
                        content="100 protège-cartes"),
                product("P-COFFRET-1", gtin=fictitious_gtin13(4), format="Coffret", content="4 boosters + promo"),
            ],
            table,
        )

    def test_exact_match_with_confirmed_link(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(), catalog)
        assert res.status is MatchStatus.MATCHED
        assert res.product_id == "P-DISPLAY"
        assert res.reasons == ("EXACT_IDENTITY", "SUPPLIER_LINK_CONFIRMED")
        assert not res.is_draft and res.can_update_existing

    def test_exact_match_other_supplier_spelling(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(
            offer(sku="X9", supplier="FICTIF_GROSSISTE_B", language="VF", format="Booster box", content="x36 boosters"),
            catalog,
        )
        assert res.status is MatchStatus.MATCHED and res.product_id == "P-DISPLAY"
        assert res.reasons == ("EXACT_IDENTITY",)

    def test_accessory_matches_whatever_language_label(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(
            offer(sku="SLV-100", gtin=fictitious_gtin13(3), language="multilingue", extension="",
                  format="Protège-cartes", content="100 protège-cartes"),
            catalog,
        )
        assert res.status is MatchStatus.MATCHED and res.product_id == "P-SLEEVES"

    def test_new_complete_reference_is_draft(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(sku="NEW", gtin=fictitious_gtin13(50), extension="Fictive Gamma"), catalog)
        assert res.status is MatchStatus.NEW_DRAFT and res.is_draft and not res.can_update_existing
        assert res.reasons == ("NEW_REFERENCE",) and res.product_id is None

    def test_same_variant_family_different_gtin_is_new_draft(self, catalog: CatalogIndex) -> None:
        # Coffret jumeau (autre GTIN, même contenu) : nouvelle référence, pas une ambiguïté.
        res = match_offer_to_product(
            offer(sku="TWIN", gtin=fictitious_gtin13(5), format="Coffret", content="4 boosters + carte"), catalog
        )
        assert res.status is MatchStatus.NEW_DRAFT

    def test_same_name_different_content_is_ambiguous(self, catalog: CatalogIndex) -> None:
        # ex. ETB « Pokémon Center » à 11 boosters vs ETB standard à 9 boosters.
        res = match_offer_to_product(
            offer(sku="ETB-PC", gtin=fictitious_gtin13(60), format="ETB", content="11 boosters"), catalog
        )
        assert res.status is MatchStatus.AMBIGUOUS
        assert "SAME_NAME_DIFFERENT_CONTENT" in res.reasons and "P-ETB" in res.candidates

    def test_same_gtin_other_language_is_ambiguous(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(sku="JP", language="Japonais"), catalog)
        assert res.status is MatchStatus.AMBIGUOUS
        assert "GTIN_CONFLICT" in res.reasons and "P-DISPLAY" in res.candidates

    def test_same_gtin_other_content_is_ambiguous(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(sku="HALF", content="18 boosters"), catalog)
        assert res.status is MatchStatus.AMBIGUOUS
        assert {"GTIN_CONFLICT", "SAME_NAME_DIFFERENT_CONTENT"} <= set(res.reasons)

    def test_missing_gtin_with_candidate_is_ambiguous(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(sku="NOGTIN", gtin=None), catalog)
        assert res.status is MatchStatus.AMBIGUOUS
        assert "MISSING_GTIN" in res.reasons and "PARTIAL_IDENTITY_MATCH" in res.reasons
        assert res.candidates == ("P-DISPLAY",)
        assert res.issues == (IdentityIssue.MISSING_GTIN,)

    def test_missing_gtin_without_candidate_is_new_draft(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(sku="NOGTIN2", gtin=None, extension="Fictive Gamma"), catalog)
        assert res.status is MatchStatus.NEW_DRAFT and "MISSING_GTIN" in res.reasons

    def test_unknown_language_never_matched(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(language="VO"), catalog)
        assert res.status is MatchStatus.AMBIGUOUS
        assert "UNKNOWN_LANGUAGE" in res.reasons and "P-DISPLAY" in res.candidates

    def test_not_sealed_never_matched(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(sealed=False), catalog)
        assert res.status is MatchStatus.AMBIGUOUS and "NOT_SEALED" in res.reasons

    def test_supplier_link_conflict(self, catalog: CatalogIndex) -> None:
        # Le SKU FICTIF-1 du fournisseur A est lié au display ; il annonce maintenant un ETB.
        res = match_offer_to_product(offer(gtin=fictitious_gtin13(2), format="ETB", content="9 boosters"), catalog)
        assert res.status is MatchStatus.AMBIGUOUS
        assert "SUPPLIER_LINK_CONFLICT" in res.reasons
        assert set(res.candidates) == {"P-ETB", "P-DISPLAY"}

    def test_link_conflict_on_new_reference(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(gtin=fictitious_gtin13(70), extension="Fictive Gamma"), catalog)
        assert res.status is MatchStatus.AMBIGUOUS and res.reasons == ("SUPPLIER_LINK_CONFLICT",)

    def test_incomplete_with_link_to_agreeing_product(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(gtin=None), catalog)
        assert res.status is MatchStatus.AMBIGUOUS
        assert "SUPPLIER_LINK_CONFLICT" not in res.reasons

    def test_incomplete_with_link_to_other_product(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(gtin=None, extension="Fictive Gamma"), catalog)
        assert res.status is MatchStatus.AMBIGUOUS and "SUPPLIER_LINK_CONFLICT" in res.reasons

    def test_incomplete_gtin_conflict(self, catalog: CatalogIndex) -> None:
        res = match_offer_to_product(offer(sku="Z", language="VO", format="ETB", content=None), catalog)
        assert res.status is MatchStatus.AMBIGUOUS and "GTIN_CONFLICT" in res.reasons

    def test_duplicate_identity_in_catalog_is_ambiguous(self, table: ExtensionTable) -> None:
        index = CatalogIndex([product("A"), product("B", language="VF")], table)
        res = match_offer_to_product(offer(sku="Q"), index)
        assert res.status is MatchStatus.AMBIGUOUS and res.reasons == ("MULTIPLE_CANDIDATES",)
        assert set(res.candidates) == {"A", "B"}

    def test_duplicate_product_id_rejected(self, table: ExtensionTable) -> None:
        with pytest.raises(CatalogError):
            CatalogIndex([product("A"), product("A", gtin=fictitious_gtin13(8))], table)

    def test_accepts_plain_iterable_and_identity(self, table: ExtensionTable) -> None:
        products = [product("P1")]
        res = match_offer_to_product(ProductIdentity(**ident()), products, table=table)  # type: ignore[arg-type]
        assert res.status is MatchStatus.MATCHED and res.product_id == "P1"

    def test_empty_catalog(self, table: ExtensionTable) -> None:
        res = match_offer_to_product(offer(), [], table=table)
        assert res.status is MatchStatus.NEW_DRAFT

    def test_index_accessors(self, catalog: CatalogIndex) -> None:
        assert len(catalog) == 4
        assert catalog.product("P-ETB").product_id == "P-ETB"
        assert catalog.normalized("P-ETB").identity.content == "9 BOOSTERS"
        assert catalog.by_link("FICTIF_GROSSISTE_A", "FICTIF-1") == ("P-DISPLAY",)
        assert catalog.by_gtin(fictitious_gtin13(2)) == ("P-ETB",)
        assert catalog.agreeing(ProductIdentity(format="DISPLAY")) == ()

    def test_property_matched_implies_complete_identity(self, catalog: CatalogIndex) -> None:
        rng = random.Random(11)
        options = {
            "gtin": [fictitious_gtin13(1), fictitious_gtin13(2), None, "2000000000009"],
            "language": ["FR", "VF", "JP", "VO", None],
            "extension": ["Fictive Alpha", "FICT-B", "Inconnue", None],
            "format": ["Display", "ETB", "Blister", None],
            "content": ["36 boosters", "9 boosters", None],
            "sealed": [True, False, None],
        }
        for i in range(400):
            choice = {k: rng.choice(v) for k, v in options.items()}
            res = match_offer_to_product(offer(sku=f"R{i}", **choice), catalog)
            if res.status is MatchStatus.MATCHED:
                assert not res.issues
                assert res.product_id is not None
                assert catalog.normalized(res.product_id).key == res.identity_key
            else:
                assert res.is_draft and res.product_id is None
