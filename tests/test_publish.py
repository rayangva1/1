"""Tests de la publication : liste blanche stricte, fuite de champs sensibles, règles BP §5-§7.

Références, GTIN (200…), extensions et prix FICTIFS. Aucune donnée fournisseur réelle.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from typing import Any

import pytest
from pokeshop.audit import InMemoryStateJournal
from pokeshop.catalog import DEFAULT_EXTENSIONS_PATH, load_extension_table, normalize_identity, product_title_fr
from pokeshop.models import AvailabilityPromise, PromiseKind
from pokeshop.pricing import decide_price
from pokeshop.publish import (
    PRODUCT_INPUT_SCHEMA,
    PUBLIC_METAFIELD_NAMESPACE,
    PUBLIC_METAFIELDS,
    CatalogListing,
    ImageRights,
    SMALL_PRODUCT_TAG,
    PlanOutcome,
    PriceApprovalBook,
    PriceValidation,
    PublicImage,
    PublishBlocker,
    PublishError,
    ReleaseDateStatus,
    SensitiveFieldError,
    ShopStatus,
    StockStatus,
    assert_metafields_public,
    assert_no_sensitive_fields,
    assert_protective_payload,
    build_publication,
    forbidden_claims,
    sensitive_violations,
    slugify,
    stock_status_for,
    stock_status_from_promise,
)
from pokeshop.rules import load_rules

FICTIF_TABLE = DEFAULT_EXTENSIONS_PATH.parents[1] / "data" / "samples" / "FICTIF_extensions_aliases.yaml"
TABLE = load_extension_table([DEFAULT_EXTENSIONS_PATH, FICTIF_TABLE])
PARAMS = load_rules().pricing
CAP = PARAMS.max_daily_price_change
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
COST = D("100.00")
DECISION = decide_price(COST, PARAMS)
ENGINE_PRICE = DECISION.recommended_price
IDENTITY = normalize_identity(
    gtin="2000000001012", language="Français", extension="Fictive Alpha", format="Display", content="36 boosters",
    sealed=True, table=TABLE,
).identity
DESCRIPTION = (
    "<p>Display de l'extension Extension Fictive Alpha, en français, neuf et scellé.</p>"
    "<p>Rappel : le contenu des boosters est aléatoire ; aucune carte précise ni rareté n'est garantie.</p>"
)
OWN = PublicImage(url="https://cdn.example.org/fictif/display-alpha.jpg", alt="Display face avant", rights=ImageRights.OWN_PHOTO)


def listing(**kw: Any) -> CatalogListing:
    base: dict[str, Any] = dict(
        product_key="FICTIF-P1",
        identity=IDENTITY,
        public_sku="DSP-FICTIF_ALPHA-FR",
        description_html=DESCRIPTION,
        images=(OWN,),
        stock_status=StockStatus.STOCK_LOCAL,
        content_text="36 boosters",
        content_validated=True,
        fictif=True,
    )
    base.update(kw)
    return CatalogListing(**base)


def existing(**kw: Any) -> CatalogListing:
    base: dict[str, Any] = dict(
        shopify_product_id="gid://shopify/Product/7", shopify_status=ShopStatus.ACTIVE, approved=True,
        current_price_chf=ENGINE_PRICE,
    )
    base.update(kw)
    return listing(**base)


def plan(item: CatalogListing, decision: Any = DECISION, **kw: Any):
    kw.setdefault("params", PARAMS)
    kw.setdefault("now", NOW)
    return build_publication(item, decision, max_daily_change=CAP, table=TABLE, **kw)


def approval(price: D, *, product_key: str = "FICTIF-P1", **kw: Any) -> PriceValidation:
    """Approbation de la propriétaire telle que l'enregistre la route ``POST /pricing/approvals``."""
    return PriceValidation.new(product_key=product_key, price=price, reason="FICTIF approbation propriétaire", now=NOW, **kw)


# --------------------------------------------------------------------- nouvelles références


def test_engine_reference_prices() -> None:
    assert DECISION.is_publishable and ENGINE_PRICE is not None and str(ENGINE_PRICE).endswith(".90")


def test_new_reference_goes_to_draft_without_validated_category_rule() -> None:
    p = plan(listing())
    assert p.outcome is PlanOutcome.SEND_DRAFT and p.target_status is ShopStatus.DRAFT
    assert p.action == "SAVE_DRAFT_PRODUCT"
    assert PublishBlocker.CATEGORY_RULE_NOT_VALIDATED.value in p.reviews
    assert p.product_input is not None and p.product_input["status"] == "DRAFT"
    assert p.identifier == {"handle": p.handle}


def test_new_reference_auto_published_when_rule_fields_and_rights_present() -> None:
    p = plan(listing(category_rule_validated=True))
    assert p.outcome is PlanOutcome.SEND_ACTIVE and p.action == "PUBLISH_NEW_PRODUCT"
    assert p.price_chf == ENGINE_PRICE and p.price_source == "ENGINE"
    assert p.blockers == () and p.reviews == ()


@pytest.mark.parametrize(
    ("changes", "blocker"),
    [
        ({"description_html": None}, PublishBlocker.DESCRIPTION_MISSING),
        ({"images": ()}, PublishBlocker.NO_AUTHORIZED_IMAGE),
        ({"images": (OWN, PublicImage(url="https://cdn.example.org/x.jpg", alt="Vue de côté"))}, PublishBlocker.IMAGE_RIGHTS_MISSING),
        ({"images": (PublicImage(url="https://cdn.example.org/y.jpg", alt="Visuel",
                                 rights=ImageRights.SUPPLIER_WRITTEN_AUTHORIZATION),)}, PublishBlocker.NO_AUTHORIZED_IMAGE),
        ({"content_validated": False}, PublishBlocker.CONTENT_NOT_VALIDATED),
        ({"content_text": None}, PublishBlocker.CONTENT_NOT_VALIDATED),
        ({"new_arrival": True}, PublishBlocker.MAX_QTY_MISSING),
    ],
)
def test_new_reference_with_missing_field_or_rights_stays_draft(changes: dict[str, Any], blocker: PublishBlocker) -> None:
    p = plan(listing(category_rule_validated=True, **changes))
    assert p.outcome is PlanOutcome.SEND_DRAFT, p
    assert blocker.value in p.reviews


def test_unauthorized_images_never_reach_the_payload() -> None:
    unknown = PublicImage(url="https://cdn.example.org/sans-droit.jpg", alt="Vue sans droit")
    supplier_ok = PublicImage(url="https://cdn.example.org/autorisee.jpg", alt="Visuel autorisé",
                              rights=ImageRights.SUPPLIER_WRITTEN_AUTHORIZATION, rights_ref="email 2026-10-01 FICTIF")
    p = plan(listing(images=(OWN, unknown, supplier_ok)))
    urls = [f["originalSource"] for f in p.product_input["files"]]
    assert urls == [OWN.url, supplier_ok.url]
    with pytest.raises(ValueError):
        PublicImage(url="http://cdn.example.org/a.jpg", alt="x")


def test_new_reference_without_publishable_price_is_not_sent() -> None:
    for decision in (None, decide_price(COST, PARAMS, unknown_fields=["vat_rate"]),
                     decide_price(COST, PARAMS, market_ref=D("10"))):
        p = plan(listing(category_rule_validated=True), decision)
        assert p.outcome is PlanOutcome.NOT_SENT and p.product_input is None and p.price_chf is None


def test_review_decision_with_human_validation_publishes_validated_price() -> None:
    review = decide_price(COST, PARAMS, market_ref=D("120"))
    assert review.status.value == "REVIEW"
    validation = approval(D("149.90"))
    p = plan(listing(category_rule_validated=True), review, price_validation=validation)
    assert p.outcome is PlanOutcome.SEND_ACTIVE and p.price_chf == D("149.90") and p.price_source == "HUMAN_VALIDATED"
    assert p.price_approval_id == validation.approval_id


# ---------------------------------------------------------------------- fiches existantes


def test_existing_approved_reference_synchronised_at_level_two() -> None:
    p = plan(existing(current_price_chf=D("149.90")), reference_price_24h=D("149.90"))
    assert p.outcome is PlanOutcome.SEND_ACTIVE and p.action == "UPDATE_APPROVED_PRODUCT"
    assert p.identifier == {"id": "gid://shopify/Product/7"}
    assert p.price_chf == ENGINE_PRICE and p.price_changed


def test_price_change_above_daily_cap_needs_validation() -> None:
    reference = (ENGINE_PRICE * D("1.10")).quantize(D("0.01"))
    p = plan(existing(current_price_chf=reference), reference_price_24h=reference)
    assert PublishBlocker.PRICE_CHANGE_ABOVE_CAP.value in p.reviews
    assert p.price_chf == reference and p.price_source == "UNCHANGED"
    validated = approval(ENGINE_PRICE)
    p2 = plan(existing(current_price_chf=reference), reference_price_24h=reference, price_validation=validated)
    assert p2.price_chf == ENGINE_PRICE and p2.price_source == "HUMAN_VALIDATED"


def test_change_within_cap_is_published_without_validation() -> None:
    reference = (ENGINE_PRICE * D("1.04")).quantize(D("0.01"))
    p = plan(existing(current_price_chf=reference), reference_price_24h=reference)
    assert p.price_chf == ENGINE_PRICE and p.price_source == "ENGINE"


def test_price_anomaly_is_blocked_even_when_validated() -> None:
    validated = approval(D("2000.00"))
    p = plan(existing(current_price_chf=D("149.90")), reference_price_24h=D("149.90"), price_validation=validated)
    assert PublishBlocker.PRICE_ANOMALY.value in p.reviews and p.price_chf == D("149.90")


@pytest.mark.parametrize(
    "decision",
    [
        decide_price(COST, PARAMS, unknown_fields=["customs_and_fees"]),
        decide_price(COST, PARAMS, candidate_price=D("101.00")),
        None,
    ],
)
def test_draft_or_blocked_decision_never_sets_a_new_public_price(decision: Any) -> None:
    p = plan(existing(current_price_chf=D("149.90")), decision, reference_price_24h=D("149.90"))
    assert p.price_chf == D("149.90") and p.price_source == "UNCHANGED"
    assert p.product_input["variants"][0]["price"] == "149.90"
    assert p.outcome is PlanOutcome.SEND_ACTIVE  # le stock local réel reste vendable au dernier prix validé


def test_quarantine_and_product_stoploss_unpublish_with_last_validated_price() -> None:
    for kw, blocker in (({"quarantined": True}, PublishBlocker.QUARANTINED),
                        ({"stoploss_blocked": True}, PublishBlocker.STOPLOSS_PRODUCT)):
        p = plan(existing(current_price_chf=D("149.90")), **kw)
        assert p.outcome is PlanOutcome.UNPUBLISH and p.action == "UNPUBLISH_PRODUCT"
        # statut seulement : le dernier prix validé reste celui de la boutique, rien d'autre n'est réécrit
        assert p.target_status is ShopStatus.DRAFT and p.price_chf is None and p.price_source is None
        assert p.product_input == {"status": "DRAFT"} and p.identifier == {"id": "gid://shopify/Product/7"}
        assert blocker.value in p.blockers
    draft = plan(existing(shopify_status=ShopStatus.DRAFT), quarantined=True)
    assert draft.outcome is PlanOutcome.NOT_SENT


def test_existing_unapproved_reference() -> None:
    active = plan(existing(approved=False))
    assert active.outcome is PlanOutcome.UNPUBLISH and PublishBlocker.NOT_APPROVED.value in active.reviews
    draft = plan(existing(approved=False, shopify_status=ShopStatus.DRAFT))
    assert draft.outcome is PlanOutcome.SEND_DRAFT and draft.action == "SAVE_DRAFT_PRODUCT"


def test_existing_approved_reference_with_incomplete_content_is_left_untouched() -> None:
    p = plan(existing(description_html=None))
    assert p.outcome is PlanOutcome.NOT_SENT and PublishBlocker.DESCRIPTION_MISSING.value in p.reviews


# ------------------------------------------------------------------ identité et contenu


def test_title_type_variant_and_inventory_policy() -> None:
    p = plan(listing(category_rule_validated=True))
    data = p.product_input
    assert data["title"] == product_title_fr(IDENTITY, TABLE) == "Display Extension Fictive Alpha – FR"
    assert data["productType"] == "Display"
    variant = data["variants"][0]
    assert variant["price"] == f"{ENGINE_PRICE:.2f}" and isinstance(variant["price"], str)
    assert variant["inventoryPolicy"] == "DENY"
    assert variant["inventoryItem"] == {"sku": "DSP-FICTIF_ALPHA-FR", "tracked": True}
    assert variant["barcode"] == "2000000001012"
    assert "inventoryQuantities" not in variant  # le stock passe uniquement par inventorySetQuantities
    assert data["handle"] == slugify(f"{data['title']}-DSP-FICTIF_ALPHA-FR")


def test_metafields_and_tags_follow_theme_contract_exactly() -> None:
    p = plan(listing(category_rule_validated=True, new_arrival=True, gift=True, max_qty=2,
                     release_date=date(2026, 11, 7), release_date_status=ReleaseDateStatus.CONFIRMEE,
                     shipping_delay="2 jours ouvrés", restock_alert=True))
    data = p.product_input
    assert PUBLIC_METAFIELD_NAMESPACE == "boutique"
    by_key = {m["key"]: m for m in data["metafields"]}
    assert all(m["namespace"] == "boutique" for m in data["metafields"])
    assert set(by_key) <= set(PUBLIC_METAFIELDS)
    assert by_key["statut_stock"]["value"] == "stock_local"
    assert by_key["langue"]["value"] == "FR"
    assert by_key["extension"]["value"] == "Extension Fictive Alpha"
    assert by_key["format"]["value"] == "Display"
    assert by_key["contenu_valide"]["type"] == "multi_line_text_field"
    assert by_key["date_sortie"] == {"namespace": "boutique", "key": "date_sortie", "type": "date", "value": "2026-11-07"}
    assert by_key["date_sortie_statut"]["value"] == "confirmee"
    assert by_key["quantite_max"] == {"namespace": "boutique", "key": "quantite_max", "type": "number_integer", "value": "2"}
    assert by_key["alerte_reassort"]["value"] == "true" and by_key["fin_de_serie"]["value"] == "false"
    assert data["tags"] == ["cadeau", "ext:extension-fictive-alpha", "nouveaute", "statut:stock-local"]


def test_new_arrival_tag_only_on_purchasable_active_product() -> None:
    draft = plan(listing(new_arrival=True, max_qty=2))
    assert "nouveaute" not in draft.product_input["tags"]
    rupture = plan(listing(category_rule_validated=True, new_arrival=True, max_qty=2, stock_status=StockStatus.RUPTURE))
    assert "nouveaute" not in rupture.product_input["tags"] and "statut:rupture" in rupture.product_input["tags"]


def test_preorder_listing_is_a_distinct_sheet_with_date_and_limit() -> None:
    with pytest.raises(ValueError):
        listing(stock_status=StockStatus.PRECOMMANDE)
    with pytest.raises(ValueError):
        listing(public_sku="DSP-FICTIF_ALPHA-FR-PRECO")
    with pytest.raises(ValueError):
        listing(release_date_status=ReleaseDateStatus.ESTIMEE)
    pre = listing(public_sku="DSP-FICTIF_ALPHA-FR-PRECO", stock_status=StockStatus.PRECOMMANDE, category_rule_validated=True)
    p = plan(pre)
    assert p.outcome is PlanOutcome.SEND_DRAFT
    assert {PublishBlocker.MAX_QTY_MISSING.value, PublishBlocker.RELEASE_DATE_MISSING.value} <= set(p.reviews)
    ok = plan(pre.replace(max_qty=2, release_date=date(2026, 11, 7), release_date_status=ReleaseDateStatus.ESTIMEE))
    assert ok.outcome is PlanOutcome.SEND_ACTIVE
    variant = ok.product_input["variants"][0]
    assert variant["optionValues"] == [{"optionName": "Disponibilité", "name": "Précommande"}]
    assert "statut:precommande" in ok.product_input["tags"]


def test_accessory_has_no_language_metafield() -> None:
    ident = normalize_identity(gtin="2000000001029", language="Français", extension=None, format="Protège-cartes",
                               content="65 protège-cartes", sealed=True, table=TABLE).identity
    p = plan(listing(identity=ident, public_sku="ACC-SLEEVES-65", category_rule_validated=True))
    assert p.outcome is PlanOutcome.SEND_ACTIVE, p.messages
    keys = {m["key"] for m in p.product_input["metafields"]}
    assert "langue" not in keys and "extension" not in keys
    assert " – " not in p.product_input["title"]


@pytest.mark.parametrize(
    ("identity_kw", "blocker"),
    [
        ({"language": "Japonais"}, PublishBlocker.LANGUAGE_NOT_FR),
        ({"sealed": False}, PublishBlocker.NOT_SEALED),
        ({"content": None}, PublishBlocker.IDENTITY_INCOMPLETE),
        ({"extension": "Inconnue au bataillon"}, PublishBlocker.IDENTITY_INCOMPLETE),
    ],
)
def test_identity_problems_never_published(identity_kw: dict[str, Any], blocker: PublishBlocker) -> None:
    fields = dict(gtin="2000000001012", language="Français", extension="Fictive Alpha", format="Display",
                  content="36 boosters", sealed=True)
    fields.update(identity_kw)
    ident = normalize_identity(**fields, table=TABLE).identity
    p = plan(listing(identity=ident, category_rule_validated=True))
    assert p.outcome is PlanOutcome.NOT_SENT and blocker.value in p.blockers


def test_fictitious_data_never_on_a_real_shop() -> None:
    real = plan(listing(category_rule_validated=True), real_shop=True)
    assert real.outcome is PlanOutcome.NOT_SENT and PublishBlocker.FICTIF_DATA.value in real.blockers
    not_flagged = plan(listing(category_rule_validated=True, fictif=False))
    assert PublishBlocker.FICTITIOUS_GTIN.value in not_flagged.blockers and not_flagged.outcome is PlanOutcome.NOT_SENT


@pytest.mark.parametrize(
    "text",
    [
        "<p>Un excellent investissement pour l'avenir.</p>",
        "<p>Carte rare garantie dans chaque display !</p>",
        "<p>Revendeur officiel Pokémon en Suisse.</p>",
        "<p>Ce coffret prendra de la valeur.</p>",
    ],
)
def test_forbidden_claims_block_publication(text: str) -> None:
    p = plan(listing(category_rule_validated=True, description_html=text))
    assert PublishBlocker.FORBIDDEN_CLAIM.value in p.blockers and p.outcome is PlanOutcome.NOT_SENT
    assert forbidden_claims(text)
    assert forbidden_claims(DESCRIPTION) == []


def test_unsafe_html_blocked() -> None:
    p = plan(listing(category_rule_validated=True, description_html="<p>ok</p><script>alert(1)</script>"))
    assert PublishBlocker.UNSAFE_HTML.value in p.blockers and p.outcome is PlanOutcome.NOT_SENT


def test_stock_status_from_promise() -> None:
    def promise(kind: PromiseKind) -> AvailabilityPromise:
        return AvailabilityPromise(kind=kind, local_qty=0, preorder_qty=0, firm_allocation=0, restock_signal=False)

    assert stock_status_from_promise(promise(PromiseKind.LOCAL_STOCK)) is StockStatus.STOCK_LOCAL
    assert stock_status_from_promise(promise(PromiseKind.PREORDER)) is StockStatus.PRECOMMANDE
    assert stock_status_from_promise(promise(PromiseKind.UNAVAILABLE)) is StockStatus.RUPTURE


# ------------------------------------------------------------------- fuite de champs sensibles


def clean_payload() -> dict[str, Any]:
    p = plan(listing(category_rule_validated=True, max_qty=2))
    assert p.product_input is not None
    return copy.deepcopy(p.product_input)


def test_clean_payload_passes_and_matches_schema() -> None:
    payload = clean_payload()
    assert_no_sensitive_fields(payload)
    assert set(payload) <= set(PRODUCT_INPUT_SCHEMA)


def _inject(payload: dict[str, Any], path: tuple[Any, ...], value: Any) -> None:
    target: Any = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("cost",), "95.00"),
        (("unitCost",), "95.00"),
        (("coutRendu",), "102.34"),
        (("marge",), "0.20"),
        (("margin_pct",), "0.20"),
        (("contribution_chf",), "30.62"),
        (("supplier_id",), "fictif_grossiste_a"),
        (("fournisseur",), "Grossiste"),
        (("prixAchat",), "95.00"),
        (("b2bPrice",), "95.00"),
        (("landedCost",), "102.34"),
        (("floor_price",), "120.00"),
        (("vendor",), "Grossiste FICTIF"),
        (("customerEmail",), "client@example.org"),
        (("compareAtPrice",), "199.90"),
        (("giftCardTemplateSuffix",), "x"),
        (("variants", 0, "inventoryItem", "cost"), "95.00"),
        (("variants", 0, "inventoryItem", "unitCost"), {"amount": "95.00"}),
        (("variants", 0, "inventoryQuantities"), [{"locationId": "gid://shopify/Location/1", "quantity": 99}]),
        (("variants", 0, "compareAtPrice"), "199.90"),
        (("variants", 0, "supplierSku"), "FICTIF-A-001"),
        (("files", 0, "supplier"), "x"),
        (("seo", "internalNote"), "x"),
    ],
)
def test_injected_sensitive_or_unlisted_key_is_rejected(path: tuple[Any, ...], value: Any) -> None:
    payload = clean_payload()
    if path[0] == "files" and not payload.get("files"):
        payload["files"] = [{"originalSource": OWN.url, "alt": "x", "contentType": "IMAGE"}]
    _inject(payload, path, value)
    with pytest.raises(SensitiveFieldError) as err:
        assert_no_sensitive_fields(payload)
    assert str(path[-1]) in str(err.value)


@pytest.mark.parametrize(
    ("path", "value", "fragment"),
    [
        (("descriptionHtml",), "<p>Prix d'achat 95 CHF, belle affaire</p>", "prix d"),
        (("descriptionHtml",), "<p>Notre marge reste faible</p>", "marge"),
        (("descriptionHtml",), "<p>Livré par notre fournisseur habituel</p>", "fournisseur"),
        (("descriptionHtml",), "<p>Tarif B2B disponible</p>", "b2b"),
        (("descriptionHtml",), "<p>Écrire à jean.dupont@example.org</p>", "email"),
        (("descriptionHtml",), "<p>Appelez le 079 123 45 67</p>", "téléphone"),
        (("descriptionHtml",), "<p>Virement CH93 0076 2011 6238 5295 7</p>", "IBAN"),
        (("descriptionHtml",), "<p>Stock fictif_grossiste_a</p>", "référence interne"),
        (("title",), "Display coût 95 CHF", "co"),
        (("tags",), ["fournisseur-fictif"], "tags[0]"),
        (("tags",), ["promo-libre"], "tags[0]"),
        (("variants", 0, "price"), 144.9, "texte attendu"),
        (("variants", 0, "price"), "0.00", "prix CHF"),
        (("variants", 0, "price"), "144.9", "prix CHF"),
        (("variants", 0, "inventoryPolicy"), "CONTINUE", "DENY"),
        (("variants", 0, "barcode"), "2000000001013", "GTIN"),
        (("variants", 0, "inventoryItem", "sku"), "sku minuscule", "SKU"),
        (("status",), "ARCHIVED", "status"),
        (("handle",), "Pas Un Handle", "handle"),
        (("metafields",), [{"namespace": "interne", "key": "cout", "type": "single_line_text_field", "value": "95"}], "métachamp"),
        (("metafields",), [{"namespace": "boutique", "key": "statut_stock", "type": "single_line_text_field",
                            "value": "en_stock_chez_fournisseur"}], "invalide"),
        (("metafields",), [{"namespace": "boutique", "key": "quantite_max", "type": "single_line_text_field",
                            "value": "2"}], "type"),
        (("files",), [{"originalSource": "http://cdn.example.org/a.jpg", "alt": "x", "contentType": "IMAGE"}], "https"),
        (("files",), [{"originalSource": "https://cdn.example.org/fictif_grossiste_a/a.jpg", "alt": "x",
                       "contentType": "IMAGE"}], "référence interne"),
        (("files",), [{"originalSource": "https://cdn.example.org/a.mp4", "alt": "x", "contentType": "VIDEO"}], "IMAGE"),
    ],
)
def test_sensitive_values_and_invalid_public_fields_are_rejected(path: tuple[Any, ...], value: Any, fragment: str) -> None:
    payload = clean_payload()
    _inject(payload, path, value)
    violations = sensitive_violations(payload, sensitive_terms=["fictif_grossiste_a", "FICTIF-A-001"])
    assert violations, payload
    assert any(fragment.lower() in v.lower() for v in violations), violations
    with pytest.raises(SensitiveFieldError):
        assert_no_sensitive_fields(payload, sensitive_terms=["fictif_grossiste_a"] if "fictif_grossiste_a" in json.dumps(value) else ())


def test_build_publication_refuses_to_send_a_leaking_payload() -> None:
    leaking = listing(category_rule_validated=True, description_html="<p>Arrivage FICTIF-A-001 du fournisseur</p>")
    p = plan(leaking, sensitive_terms=["FICTIF-A-001", "fictif_grossiste_a"])
    assert p.outcome is PlanOutcome.NOT_SENT and p.product_input is None and p.identifier is None
    assert PublishBlocker.SENSITIVE_FIELD.value in p.blockers and p.violations
    assert "FICTIF-A-001" in " ".join(p.violations)


def test_plan_never_contains_costs_margins_or_order_fields() -> None:
    cost = D("123.45")
    decision = decide_price(cost, PARAMS)
    p = build_publication(listing(category_rule_validated=True), decision, max_daily_change=CAP, table=TABLE)
    dumped = p.model_dump_json()
    for forbidden in (str(cost), str(decision.contribution_chf), str(decision.floor_price), str(decision.profitable_price),
                      "contribution", "landed", "floor", "margin", "order", "cost"):
        assert forbidden not in dumped, forbidden
    assert str(decision.recommended_price) in dumped


def test_metafields_public_helper() -> None:
    good = [{"ownerId": "gid://shopify/Product/1", "namespace": "boutique", "key": "fin_de_serie", "type": "boolean",
             "value": "true"}]
    assert_metafields_public(good, require_owner=True)
    with pytest.raises(SensitiveFieldError):
        assert_metafields_public(good)  # ownerId hors liste blanche sans require_owner
    with pytest.raises(SensitiveFieldError):
        assert_metafields_public([{**good[0], "value": True}], require_owner=True)
    with pytest.raises(SensitiveFieldError):
        assert_metafields_public(["pas un objet"])  # type: ignore[list-item]


def test_listing_validation() -> None:
    with pytest.raises(ValueError):
        listing(public_sku="dsp minuscule")
    with pytest.raises(ValueError):
        listing(handle="Pas Valide")
    with pytest.raises(ValueError):
        listing(shopify_status=ShopStatus.ACTIVE)
    with pytest.raises(ValueError):
        listing(shopify_product_id="7")
    with pytest.raises(ValueError):
        PriceValidation.new(product_key="FICTIF-P1", price=D("10"), reason="FICTIF approbation", now=datetime(2026, 10, 4))
    assert slugify("Coffret Dresseur d'Élite (ETB) – FR") == "coffret-dresseur-d-elite-etb-fr"


# ------------------------------------------------------------ lot F3 : régressions de la revue adverse


def test_self_declared_validation_no_longer_exists_and_approval_below_floor_is_refused() -> None:
    """MOT-04 / SEC-03 : un prix « validé » sous le coût n'est jamais publié sans exception C18."""
    with pytest.raises(ValueError):  # l'ancien champ libre validated_by n'existe plus
        PriceValidation(price=D("100.00"), validated_by="agent-07", validated_at=NOW)  # type: ignore[call-arg]
    below = approval(D("100.00"))  # coût 100 : contribution négative
    p = plan(existing(), price_validation=below, reference_price_24h=ENGINE_PRICE)
    assert PublishBlocker.APPROVED_PRICE_BELOW_FLOOR.value in p.reviews
    assert p.price_chf == ENGINE_PRICE and p.price_source == "UNCHANGED" and p.price_approval_id is None
    new = plan(listing(category_rule_validated=True), price_validation=approval(D("9.90")))
    assert new.outcome is PlanOutcome.NOT_SENT and new.price_chf is None  # aucun nouveau prix : revue humaine
    assert PublishBlocker.APPROVED_PRICE_BELOW_FLOOR.value in new.reviews
    exception = approval(D("100.00"), floor_exception_ref="C18-FICTIF-2026-001")
    p2 = plan(existing(), price_validation=exception, reference_price_24h=ENGINE_PRICE)
    assert p2.price_chf == D("100.00") and p2.price_source == "HUMAN_VALIDATED"
    assert p2.price_approval_id == exception.approval_id


def test_approval_is_unusable_for_another_reference_when_expired_or_unverifiable() -> None:
    review = decide_price(COST, PARAMS, market_ref=D("120"))
    item = listing(category_rule_validated=True)
    for kw in (
        {"price_validation": approval(D("149.90"), product_key="FICTIF-P2")},
        {"price_validation": approval(D("149.90")), "now": NOW + timedelta(hours=49)},
        {"price_validation": approval(D("149.90")), "params": None},
        {"price_validation": approval(D("149.90")), "now": None},
    ):
        p = plan(item, review, **kw)
        assert PublishBlocker.PRICE_APPROVAL_INVALID.value in p.reviews
        assert p.outcome is PlanOutcome.NOT_SENT and p.price_source is None
    with pytest.raises(ValueError):  # au plus 7 jours
        approval(D("149.90"), valid_for=timedelta(days=8))


def test_price_approval_book_is_persisted_latest_wins_and_revocable() -> None:
    journal = InMemoryStateJournal(PriceApprovalBook.STREAM)
    book = PriceApprovalBook(store=journal)
    first = book.record(approval(D("149.90")))
    later = PriceValidation.new(product_key="FICTIF-P1", price=D("144.90"), reason="FICTIF nouvelle approbation",
                                now=NOW + timedelta(minutes=5))
    book.record(later)
    assert book.active_for("FICTIF-P1", NOW + timedelta(minutes=10)) == later
    assert book.active_for("FICTIF-P1", NOW + timedelta(days=3)) is None  # expirée
    restored = PriceApprovalBook.restore(journal)
    assert restored.active_for("FICTIF-P1", NOW + timedelta(minutes=10)) == later
    assert restored.revoke(later.approval_id) and not restored.revoke(later.approval_id)
    assert restored.active_for("FICTIF-P1", NOW + timedelta(minutes=10)) == first
    again = PriceApprovalBook.restore(journal)
    assert again.active_for("FICTIF-P1", NOW + timedelta(minutes=10)) == first
    with pytest.raises(PublishError):
        again.record(first)


@pytest.mark.parametrize(
    "changes",
    [
        {"descriptionHtml": "<p>Prix de revient 98,50 CHF, acheté chez le distributeur Asmodee Suisse, bénéfice 36 %.</p>"},
        {"descriptionHtml": "<p>Einkaufspreis CHF 98.50 beim Lieferant Carletto, Händlerrabatt 30 %.</p>"},
        {"descriptionHtml": "<p>PA 98.50 HT - PV 154.90 - remise revendeur 30 %, markup 1.57.</p>"},
        {"seo": {"title": "Display", "description": "Revient à 98.50, profit 56.40"}},
        {"tags": ["statut:stock-local", "ext:pa-98-50-chf-distrib-carletto"]},
        {"handle": "display-alpha-pa-98-50-revient-carletto"},
        {"files": [{"originalSource": "https://cdn.example.org/a.jpg", "alt": "Bon de livraison, PA 98.50",
                    "contentType": "IMAGE"}]},
        {"descriptionHtml": "<p>Contact : jean.dupont [at] gmail [dot] com</p>"},
        {"descriptionHtml": "<p>Appeler +33 6 12 34 56 78</p>"},
        {"descriptionHtml": "<p>Appeler 079-123-45-67</p>"},
        {"descriptionHtml": "<p>Livré à Mme Martin, Rue du Rhône 12, 1204 Genève</p>"},
        {"descriptionHtml": "<p>Seulement 49.90 au lieu de 59.90 !</p>"},
    ],
)
def test_public_text_filter_catches_costs_suppliers_amounts_and_personal_data(changes: dict[str, Any]) -> None:
    """SEC-08 : vocabulaire FR/DE/IT/EN, montants, données personnelles, handle et étiquettes."""
    good = plan(listing(category_rule_validated=True)).product_input
    assert good is not None and sensitive_violations(good) == []
    bad = {**copy.deepcopy(good), **changes}
    assert sensitive_violations(bad, sensitive_terms=["Carletto", "Asmodee"]), changes


def test_metafield_text_and_extension_tag_are_checked() -> None:
    good = plan(listing(category_rule_validated=True)).product_input
    assert good is not None
    leak = copy.deepcopy(good)
    leak["metafields"].append({"namespace": "boutique", "key": "delai_expedition", "type": "single_line_text_field",
                               "value": "dès réception de Carletto (commande n° PO-4471)"})
    assert sensitive_violations(leak, sensitive_terms=["Carletto"])
    other_ext = copy.deepcopy(good)
    other_ext["tags"] = [t if not t.startswith("ext:") else "ext:autre-extension" for t in other_ext["tags"]]
    assert any("boutique.extension" in v for v in sensitive_violations(other_ext))
    with pytest.raises(SensitiveFieldError):
        assert_metafields_public([{"namespace": "boutique", "key": "contenu_valide", "type": "multi_line_text_field",
                                   "value": "36 boosters (acheté 98.50, revient 2.74/booster)"}])


def test_supplier_names_become_sensitive_terms_in_sync() -> None:
    from pokeshop.sync import supplier_terms

    terms = supplier_terms("asmodee_fr", "Asmodee France")
    assert {"Asmodee France", "Asmodee", "asmodee_fr"} <= terms and "France" not in terms
    text = {"descriptionHtml": "<p>Display importé, acheté chez Asmodee.</p>"}
    good = plan(listing(category_rule_validated=True)).product_input
    assert sensitive_violations({**good, **text}, sensitive_terms=sorted(terms))


def test_protective_unpublish_needs_no_current_price_and_never_rewrites_content() -> None:
    """SEC-09 / SEC-15 : dépublication sans prix courant ; charge minimale même avec un contenu modifié."""
    for kw in ({"quarantined": True}, {"stoploss_blocked": True}):
        p = plan(existing(current_price_chf=None), None, **kw)
        assert p.outcome is PlanOutcome.UNPUBLISH and p.send and p.product_input == {"status": "DRAFT"}
    rewritten = existing(approved=False, current_price_chf=D("1.00"),
                         description_html="<p>Nouvelle description réécrite pendant le gel.</p>",
                         images=(PublicImage(url="https://images.example.org/autre.jpg", alt="autre",
                                             rights=ImageRights.OWN_PHOTO),))
    p = plan(rewritten)
    assert p.outcome is PlanOutcome.UNPUBLISH and p.product_input == {"status": "DRAFT"}
    assert p.price_chf is None and p.identifier == {"id": "gid://shopify/Product/7"}
    assert_protective_payload(p.product_input)
    with pytest.raises(SensitiveFieldError):
        assert_protective_payload({"status": "DRAFT", "descriptionHtml": "<p>x</p>"})


def test_public_stock_status_is_recomputed_from_engine_stock() -> None:
    """E2E-12 : statut déclaré « stock local » sans stock vendable => rupture, nouvelle référence en brouillon."""
    computed = stock_status_for(listing(), local_sellable=0)
    assert computed is StockStatus.RUPTURE
    p = plan(listing(category_rule_validated=True), stock_status=computed)
    assert p.outcome is PlanOutcome.SEND_DRAFT and p.stock_status == "rupture"
    assert PublishBlocker.STOCK_STATUS_CORRECTED.value in p.reviews and PublishBlocker.NO_SELLABLE_STOCK.value in p.reviews
    by_key = {m["key"]: m["value"] for m in p.product_input["metafields"]}
    assert by_key["statut_stock"] == "rupture" and "statut:rupture" in p.product_input["tags"]
    ok = plan(listing(category_rule_validated=True), stock_status=stock_status_for(listing(), local_sellable=3))
    assert ok.outcome is PlanOutcome.SEND_ACTIVE and "statut:stock-local" in ok.product_input["tags"]
    preco = listing(public_sku="DSP-FICTIF_ALPHA-FR-PRECO", stock_status=StockStatus.PRECOMMANDE)
    assert stock_status_for(preco, local_sellable=0, firm_allocation=0) is StockStatus.RUPTURE
    assert stock_status_for(preco, local_sellable=0, firm_allocation=6) is StockStatus.PRECOMMANDE


def test_small_product_carries_the_cart_guard_tag() -> None:
    """MOT-10 : un petit produit (règle active) porte l'étiquette lue par la validation de panier."""
    small_rules = PARAMS.replace(small_product_max_shipping_ttc=D("0"), small_product_min_order_ttc=D("127"))
    d = decide_price(D("3.50"), small_rules)
    assert d.small_product
    p = plan(listing(category_rule_validated=True), d, params=small_rules)
    assert SMALL_PRODUCT_TAG in p.product_input["tags"]
    assert SMALL_PRODUCT_TAG not in plan(listing(category_rule_validated=True)).product_input["tags"]
