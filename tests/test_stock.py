"""Tests stock vendable, précommandes, péremption, réservations concurrentes et réassort (BP §5, §13).

Offres et quantités FICTIVES.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from pokeshop.errors import (
    ConcurrencyError,
    InsufficientStockError,
    InvalidStateError,
    ReservationNotFoundError,
    StockError,
)
from pokeshop.models import (
    AvailabilityStatus,
    MovementKind,
    PromiseKind,
    ReorderCandidate,
    ReservationStatus,
    SupplierOffer,
)
from pokeshop.stock import (
    StockRegistry,
    availability_promise,
    is_stale,
    pooled_quantity,
    preorder_quota,
    propose_reorder,
    reorder_point,
    sellable_local,
)

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def offer(**kw) -> SupplierOffer:
    base = dict(
        supplier_id="FICTIF_SUPPLIER_A",
        supplier_sku="FICTIF-SKU-1",
        gtin="2000000000008",
        language="FR",
        extension="FICTIF Extension Alpha",
        format="etb",
        content="9 boosters",
        sealed=True,
        units_per_pack=1,
        price=D("50"),
        currency="CHF",
        price_includes_vat=False,
        vat_rate=D("0"),
        moq=1,
        carton_qty=1,
        availability_status=AvailabilityStatus.IN_STOCK,
        available_qty=100,
        ship_from_country="CH",
        source_ts=NOW - timedelta(hours=1),
        raw_ref="FICTIF_snapshot",
    )
    base.update(kw)
    return SupplierOffer(**base)


# ============================================================ fonctions pures


@pytest.mark.parametrize(
    "on_hand,reserved,damaged,safety,expected",
    [(10, 2, 1, 1, 6), (3, 2, 1, 1, 0), (0, 0, 0, 0, 0), (5, 0, 0, 0, 5), (5, 5, 0, 0, 0), (1, 0, 0, 2, 0)],
)
def test_sellable_local(on_hand, reserved, damaged, safety, expected):
    assert sellable_local(on_hand, reserved, damaged, safety) == expected


@pytest.mark.parametrize("bad", [(-1, 0, 0, 0), (0, -1, 0, 0), (0, 0, -1, 0), (0, 0, 0, -1)])
def test_sellable_local_rejects_negative(bad):
    with pytest.raises(StockError):
        sellable_local(*bad)


@pytest.mark.parametrize("bad", [(1.0, 0, 0, 0), (True, 0, 0, 0), ("1", 0, 0, 0)])
def test_sellable_local_rejects_non_int(bad):
    with pytest.raises(TypeError):
        sellable_local(*bad)


@pytest.mark.parametrize("alloc,committed,safety,expected", [(50, 20, 5, 25), (10, 10, 1, 0), (0, 0, 0, 0), (12, 0, 0, 12)])
def test_preorder_quota(alloc, committed, safety, expected):
    assert preorder_quota(alloc, committed, safety) == expected


def test_preorder_quota_rejects_negative():
    with pytest.raises(StockError):
        preorder_quota(-1, 0, 0)


@pytest.mark.parametrize(
    "age,expected",
    [
        (timedelta(hours=1), False),
        (timedelta(hours=24), False),
        (timedelta(hours=24, seconds=1), True),
        (timedelta(days=3), True),
        (timedelta(minutes=-1), False),
        (timedelta(minutes=-10), True),
    ],
)
def test_is_stale(age, expected):
    assert is_stale(NOW - age, NOW) is expected


def test_is_stale_custom_age_and_timezones():
    from datetime import timezone

    cet = timezone(timedelta(hours=2))
    assert is_stale(datetime(2026, 10, 4, 13, 0, tzinfo=cet), NOW) is False  # = 11:00 UTC
    assert is_stale(NOW - timedelta(hours=2), NOW, timedelta(hours=1)) is True
    with pytest.raises(StockError):
        is_stale(datetime(2026, 10, 4), NOW)
    with pytest.raises(StockError):
        is_stale(NOW, datetime(2026, 10, 4))
    with pytest.raises(StockError):
        is_stale(NOW, NOW, timedelta(0))


def test_pooled_quantity_never_adds_shared_stock():
    offers = [
        offer(supplier_sku="A", stock_pool_id="P1", allocation_qty=10),
        offer(supplier_sku="B", stock_pool_id="P1", allocation_qty=8),
        offer(supplier_sku="C", stock_pool_id="P2", allocation_qty=5),
        offer(supplier_sku="D", allocation_qty=12),
    ]
    assert pooled_quantity(offers) == 15
    assert pooled_quantity(offers + [offer(supplier_sku="E", allocation_qty=20)]) == 20
    assert pooled_quantity([offer(allocation_qty=7), offer(supplier_sku="X", allocation_qty=9)]) == 9
    assert pooled_quantity([]) == 0
    assert pooled_quantity(offers, "available_qty") == 200  # pools P1 et P2 déclarés distincts
    with pytest.raises(StockError):
        pooled_quantity(offers, "price")


class TestAvailabilityPromise:
    def test_local_stock_is_the_only_shippable_promise(self):
        p = availability_promise(local_sellable=3, offers=[offer()], now=NOW)
        assert p.kind is PromiseKind.LOCAL_STOCK
        assert p.promisable_qty == 3
        assert p.restock_signal is True

    def test_unallocated_upstream_stock_never_promised(self):
        p = availability_promise(local_sellable=0, offers=[offer(available_qty=500)], now=NOW, preorders_enabled=True)
        assert p.kind is PromiseKind.UNAVAILABLE
        assert p.promisable_qty == 0
        assert p.restock_signal is True
        assert "UPSTREAM_STOCK_NOT_PROMISED" in p.reasons

    def test_preorder_on_firm_allocation(self):
        o = offer(availability_status=AvailabilityStatus.ALLOCATION, available_qty=None, allocation_qty=20)
        p = availability_promise(local_sellable=0, offers=[o], now=NOW, preorders_enabled=True, committed_preorders=5, preorder_safety=2)
        assert p.kind is PromiseKind.PREORDER
        assert p.preorder_qty == 13
        assert p.promisable_qty == 13
        assert p.firm_allocation == 20

    def test_preorders_disabled(self):
        o = offer(allocation_qty=20, available_qty=None, availability_status=AvailabilityStatus.ALLOCATION)
        p = availability_promise(local_sellable=0, offers=[o], now=NOW)
        assert p.kind is PromiseKind.UNAVAILABLE
        assert "PREORDERS_DISABLED" in p.reasons

    def test_preorder_quota_exhausted(self):
        o = offer(allocation_qty=10, available_qty=None, availability_status=AvailabilityStatus.ALLOCATION)
        p = availability_promise(local_sellable=0, offers=[o], now=NOW, preorders_enabled=True, committed_preorders=10)
        assert p.kind is PromiseKind.UNAVAILABLE
        assert "PREORDER_QUOTA_EXHAUSTED" in p.reasons

    def test_stale_allocation_excluded(self):
        o = offer(allocation_qty=20, source_ts=NOW - timedelta(hours=30))
        p = availability_promise(local_sellable=0, offers=[o], now=NOW, preorders_enabled=True)
        assert p.kind is PromiseKind.UNAVAILABLE
        assert p.firm_allocation == 0
        assert p.restock_signal is False
        assert "STALE_OFFER" in p.reasons
        assert p.excluded_offers == ("FICTIF_SUPPLIER_A/FICTIF-SKU-1",)

    def test_stale_upstream_does_not_block_local_sales(self):
        o = offer(source_ts=NOW - timedelta(days=5))
        p = availability_promise(local_sellable=2, offers=[o], now=NOW)
        assert p.kind is PromiseKind.LOCAL_STOCK
        assert p.local_qty == 2

    def test_shared_pool_allocations_not_added(self):
        offers = [
            offer(supplier_sku="A", allocation_qty=20, stock_pool_id="DISTRIB-1"),
            offer(supplier_sku="B", allocation_qty=20, stock_pool_id="DISTRIB-1"),
        ]
        p = availability_promise(local_sellable=0, offers=offers, now=NOW, preorders_enabled=True)
        assert p.preorder_qty == 20

    def test_negative_local_rejected(self):
        with pytest.raises(StockError):
            availability_promise(local_sellable=-1, now=NOW)


# ================================================================ registre


@pytest.fixture
def reg() -> StockRegistry:
    r = StockRegistry(clock=lambda: NOW)
    r.receive("ETB-FICTIF", 5, "RECEP-1")
    return r


class TestRegistry:
    def test_receive_and_level(self, reg):
        lvl = reg.level("ETB-FICTIF")
        assert (lvl.on_hand, lvl.reserved, lvl.damaged, lvl.safety, lvl.version) == (5, 0, 0, 0, 1)
        assert reg.sellable("ETB-FICTIF") == 5
        assert reg.level("INCONNU").version == 0

    def test_reserve_and_insufficient(self, reg):
        res = reg.reserve("ETB-FICTIF", 3, "CMD-1")
        assert res.status is ReservationStatus.ACTIVE
        assert reg.sellable("ETB-FICTIF") == 2
        with pytest.raises(InsufficientStockError):
            reg.reserve("ETB-FICTIF", 3, "CMD-2")

    def test_last_unit_bought_simultaneously_threads(self):
        reg = StockRegistry()
        reg.receive("DISPLAY-FICTIF", 1, "RECEP")
        barrier = threading.Barrier(24)
        wins: list[str] = []
        losses: list[Exception] = []
        lock = threading.Lock()

        def buy(i: int) -> None:
            barrier.wait()
            try:
                reg.reserve("DISPLAY-FICTIF", 1, f"CMD-{i}")
                with lock:
                    wins.append(f"CMD-{i}")
            except InsufficientStockError as exc:
                with lock:
                    losses.append(exc)

        threads = [threading.Thread(target=buy, args=(i,)) for i in range(24)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(wins) == 1
        assert len(losses) == 23
        lvl = reg.level("DISPLAY-FICTIF")
        assert lvl.reserved == 1 and lvl.sellable == 0

    def test_last_unit_compare_and_set(self):
        reg = StockRegistry(clock=lambda: NOW)
        reg.receive("DISPLAY-FICTIF", 1, "RECEP")
        seen_by_a = reg.level("DISPLAY-FICTIF")
        seen_by_b = reg.level("DISPLAY-FICTIF")
        assert seen_by_a.sellable == seen_by_b.sellable == 1
        reg.reserve("DISPLAY-FICTIF", 1, "CMD-A", expected_version=seen_by_a.version)
        with pytest.raises(ConcurrencyError):
            reg.reserve("DISPLAY-FICTIF", 1, "CMD-B", expected_version=seen_by_b.version)
        fresh = reg.level("DISPLAY-FICTIF")
        with pytest.raises(InsufficientStockError):
            reg.reserve("DISPLAY-FICTIF", 1, "CMD-B", expected_version=fresh.version)

    def test_concurrent_cas_retry_never_oversells(self):
        reg = StockRegistry()
        reg.receive("BOOSTER-FICTIF", 10, "RECEP")
        sold = []
        lock = threading.Lock()

        def worker(i: int) -> None:
            for _ in range(200):
                lvl = reg.level("BOOSTER-FICTIF")
                if lvl.sellable == 0:
                    return
                try:
                    reg.reserve("BOOSTER-FICTIF", 1, f"CMD-{i}", expected_version=lvl.version)
                    with lock:
                        sold.append(i)
                    return
                except ConcurrencyError:
                    continue
                except InsufficientStockError:
                    return

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(sold) == 10
        assert reg.level("BOOSTER-FICTIF").reserved == 10

    def test_reserve_is_idempotent_per_order(self, reg):
        a = reg.reserve("ETB-FICTIF", 2, "CMD-1")
        b = reg.reserve("ETB-FICTIF", 2, "CMD-1")
        assert a == b
        assert reg.level("ETB-FICTIF").reserved == 2
        assert len(reg.movements("ETB-FICTIF")) == 2  # réception + 1 réservation
        with pytest.raises(InvalidStateError):
            reg.reserve("ETB-FICTIF", 3, "CMD-1")

    def test_reservation_cancelled_releases_stock(self, reg):
        res = reg.reserve("ETB-FICTIF", 4, "CMD-1")
        assert reg.sellable("ETB-FICTIF") == 1
        cancelled = reg.cancel(res.reservation_id)
        assert cancelled.status is ReservationStatus.CANCELLED
        assert reg.sellable("ETB-FICTIF") == 5
        assert reg.cancel(res.reservation_id) == cancelled  # idempotent
        assert reg.level("ETB-FICTIF").reserved == 0
        again = reg.reserve("ETB-FICTIF", 1, "CMD-1")
        assert again.reservation_id != res.reservation_id

    def test_fulfill(self, reg):
        res = reg.reserve("ETB-FICTIF", 2, "CMD-1")
        done = reg.fulfill(res.reservation_id)
        assert done.status is ReservationStatus.FULFILLED
        lvl = reg.level("ETB-FICTIF")
        assert (lvl.on_hand, lvl.reserved) == (3, 0)
        assert reg.fulfill(res.reservation_id) == done
        with pytest.raises(InvalidStateError):
            reg.cancel(res.reservation_id)
        other = reg.reserve("ETB-FICTIF", 1, "CMD-2")
        reg.cancel(other.reservation_id)
        with pytest.raises(InvalidStateError):
            reg.fulfill(other.reservation_id)

    def test_unknown_reservation(self, reg):
        with pytest.raises(ReservationNotFoundError) as exc:
            reg.cancel("RES-404")
        assert isinstance(exc.value, KeyError)
        assert "RES-404" in str(exc.value)

    def test_refund_before_shipping_is_cancellation(self, reg):
        res = reg.reserve("ETB-FICTIF", 2, "CMD-1")
        out = reg.refund(res.reservation_id, "RMB-1", returned=False)
        assert out.status is ReservationStatus.CANCELLED
        assert reg.sellable("ETB-FICTIF") == 5
        assert reg.refund(res.reservation_id, "RMB-1", returned=False) == out  # reprise sans double écriture
        res2 = reg.reserve("ETB-FICTIF", 2, "CMD-2")
        with pytest.raises(InvalidStateError):
            reg.refund(res2.reservation_id, "RMB-2", 1, returned=False)
        reg.cancel(res2.reservation_id)
        with pytest.raises(InvalidStateError):
            reg.refund(res2.reservation_id, "RMB-3", returned=False)

    def test_refund_with_return_to_stock(self, reg):
        res = reg.reserve("ETB-FICTIF", 2, "CMD-1")
        reg.fulfill(res.reservation_id)
        assert reg.sellable("ETB-FICTIF") == 3
        out = reg.refund(res.reservation_id, "RMB-1", 1, returned=True)
        assert out.refunded_qty == 1
        assert reg.sellable("ETB-FICTIF") == 4
        # reprise : même refund_id => aucune double remise en stock
        reg.refund(res.reservation_id, "RMB-1", 1, returned=True)
        assert reg.sellable("ETB-FICTIF") == 4
        reg.refund(res.reservation_id, "RMB-2", returned=True)
        assert reg.sellable("ETB-FICTIF") == 5
        with pytest.raises(InvalidStateError):
            reg.refund(res.reservation_id, "RMB-3", 1, returned=True)

    def test_refund_damaged_return_not_sellable(self, reg):
        res = reg.reserve("ETB-FICTIF", 1, "CMD-1")
        reg.fulfill(res.reservation_id)
        reg.refund(res.reservation_id, "RMB-1", returned=True, damaged=True)
        lvl = reg.level("ETB-FICTIF")
        assert (lvl.on_hand, lvl.damaged, lvl.sellable) == (5, 1, 4)
        assert reg.movements("ETB-FICTIF")[-1].kind is MovementKind.RETURN_DAMAGED

    def test_refund_without_return_keeps_stock(self, reg):
        res = reg.reserve("ETB-FICTIF", 1, "CMD-1")
        reg.fulfill(res.reservation_id)
        reg.refund(res.reservation_id, "RMB-1", returned=False)
        assert reg.level("ETB-FICTIF").on_hand == 4
        assert reg.movements("ETB-FICTIF")[-1].kind is MovementKind.REFUND_NO_RETURN

    def test_refund_argument_errors(self, reg):
        res = reg.reserve("ETB-FICTIF", 1, "CMD-1")
        with pytest.raises(StockError):
            reg.refund(res.reservation_id, "", returned=True)
        with pytest.raises(StockError):
            reg.refund(res.reservation_id, "RMB", returned=False, damaged=True)

    def test_damaged_stock(self, reg):
        reg.reserve("ETB-FICTIF", 3, "CMD-1")
        reg.mark_damaged("ETB-FICTIF", 1, "CASSE-1")
        assert reg.sellable("ETB-FICTIF") == 1
        with pytest.raises(InsufficientStockError):
            reg.mark_damaged("ETB-FICTIF", 2, "CASSE-2")  # unités réservées non dégradables ici
        reg.write_off_damaged("ETB-FICTIF", 1, "DESTRUCTION-1")
        lvl = reg.level("ETB-FICTIF")
        assert (lvl.on_hand, lvl.damaged, lvl.reserved, lvl.sellable) == (4, 0, 3, 1)
        with pytest.raises(InsufficientStockError):
            reg.write_off_damaged("ETB-FICTIF", 1, "X")

    def test_safety_stock(self, reg):
        reg.set_safety("ETB-FICTIF", 2)
        assert reg.sellable("ETB-FICTIF") == 3
        with pytest.raises(InsufficientStockError):
            reg.reserve("ETB-FICTIF", 4, "CMD-1")

    def test_cas_on_other_mutations(self, reg):
        v = reg.level("ETB-FICTIF").version
        reg.receive("ETB-FICTIF", 1, "R2", expected_version=v)
        with pytest.raises(ConcurrencyError):
            reg.mark_damaged("ETB-FICTIF", 1, "X", expected_version=v)
        with pytest.raises(ConcurrencyError):
            reg.set_safety("ETB-FICTIF", 1, expected_version=v)

    def test_journal_is_append_only_and_versioned(self, reg):
        res = reg.reserve("ETB-FICTIF", 1, "CMD-1")
        reg.fulfill(res.reservation_id)
        moves = reg.movements("ETB-FICTIF")
        assert [m.kind for m in moves] == [MovementKind.RECEIPT, MovementKind.RESERVE, MovementKind.FULFILL]
        assert [m.version_after for m in moves] == [1, 2, 3]
        assert [m.seq for m in moves] == [1, 2, 3]
        assert all(m.at == NOW for m in moves)
        assert reg.reservations("CMD-1")[0].reservation_id == res.reservation_id
        assert reg.reservations() == reg.reservations("CMD-1")

    @pytest.mark.parametrize(
        "call",
        [
            lambda r: r.receive("ETB-FICTIF", 0, "X"),
            lambda r: r.receive("", 1, "X"),
            lambda r: r.receive("ETB-FICTIF", 1, "X", at=datetime(2026, 10, 4)),
            lambda r: r.reserve("ETB-FICTIF", 1, ""),
            lambda r: r.set_safety("ETB-FICTIF", -1),
        ],
    )
    def test_invalid_operations(self, reg, call):
        with pytest.raises(StockError):
            call(reg)


# ================================================================ réassort


@pytest.mark.parametrize("avg,lead,safety,expected", [(D("2"), 7, 3, D("17")), (D("0.5"), 10, 0, D("5")), (D("0"), 30, 2, D("2"))])
def test_reorder_point(avg, lead, safety, expected):
    assert reorder_point(avg, lead, safety) == expected


def test_reorder_point_errors():
    with pytest.raises(TypeError):
        reorder_point(1.5, 7, 0)  # type: ignore[arg-type]
    with pytest.raises(StockError):
        reorder_point(D("-1"), 7, 0)


def cand(key="ETB-ALPHA", ext="Alpha", **kw) -> ReorderCandidate:
    o_kw = kw.pop("offer_kw", {})
    base = dict(
        product_key=key,
        extension=ext,
        offer=offer(supplier_sku=f"FICTIF-{key}", **o_kw),
        unit_cost_chf=D("50"),
        sellable_qty=3,
        on_order_qty=0,
        avg_daily_sales=D("1"),
        lead_time_days=7,
        safety_stock=2,
        coverage_days=14,
    )
    base.update(kw)
    return ReorderCandidate(**base)


def propose(cands, **kw):
    base = dict(budget_available=D("3000"), stock_budget_total=D("3000"), now=NOW, rules_version="test-v1")
    base.update(kw)
    return propose_reorder(cands, **base)


class TestProposeReorder:
    def test_proposal_is_never_an_order(self):
        p = propose([cand(unit_cost_chf=D("10"))])
        assert p.status == "PROPOSAL_TO_VALIDATE"
        assert p.requires_human_validation is True
        assert p.rules_version == "test-v1"
        line = p.lines[0]
        # besoin = 1 × (7 + 14) + 2 − 3 = 20
        assert line.qty == 20
        assert line.reorder_point == D("9")
        assert line.position == 3
        assert p.total_cost_chf == D("200.00")
        assert p.budget_remaining_chf == D("2800.00")
        assert p.extension_exposure_after == {"Alpha": D("200.00")}

    def test_moq(self):
        p = propose([cand(unit_cost_chf=D("10"), offer_kw=dict(moq=30))])
        assert p.lines[0].qty == 30
        assert any("MOQ" in n for n in p.lines[0].notes)

    def test_carton_multiples(self):
        p = propose([cand(unit_cost_chf=D("10"), offer_kw=dict(carton_qty=6))])
        assert p.lines[0].qty == 24

    def test_moq_not_multiple_of_carton(self):
        p = propose([cand(unit_cost_chf=D("10"), offer_kw=dict(moq=25, carton_qty=6))])
        assert p.lines[0].qty == 30

    def test_budget_reduces_by_cartons(self):
        p = propose([cand(offer_kw=dict(carton_qty=6))], budget_available=D("500"))
        assert p.lines[0].qty == 6
        assert any("REDUCED_BY_BUDGET" in n for n in p.lines[0].notes)
        assert p.budget_remaining_chf == D("200.00")

    def test_budget_below_moq_skips(self):
        p = propose([cand(offer_kw=dict(moq=12, carton_qty=6))], budget_available=D("500"))
        assert p.lines == ()
        assert p.skipped[0].reason == "BUDGET"

    def test_extension_cap_25_percent(self):
        p = propose([cand()], extension_exposure={"Alpha": D("600")})
        # plafond 750 CHF, déjà 600 => 150 CHF => 3 unités à 50
        assert p.lines[0].qty == 3
        assert any("EXTENSION_CAP" in n for n in p.lines[0].notes)
        assert p.extension_exposure_after["Alpha"] == D("750.00")

    def test_extension_cap_reached_skips(self):
        p = propose([cand()], extension_exposure={"Alpha": D("750")})
        assert p.skipped[0].reason == "EXTENSION_CAP"

    def test_extension_cap_shared_between_candidates(self):
        a = cand("A", sellable_qty=0, unit_cost_chf=D("30"))
        b = cand("B", sellable_qty=1, unit_cost_chf=D("30"))
        p = propose([b, a])
        # A (couverture 0 j) servi d'abord : besoin 23 × 30 = 690 ; reste 60 => B = 2
        assert [ln.product_key for ln in p.lines] == ["A", "B"]
        assert [ln.qty for ln in p.lines] == [23, 2]
        assert p.extension_exposure_after["Alpha"] == D("750.00")

    def test_documented_cap_exception(self):
        p = propose([cand()], extension_exposure={"Alpha": D("600")}, cap_exceptions={"Alpha": D("0.40")})
        assert p.lines[0].qty == 12
        assert any("EXTENSION_CAP_EXCEPTION" in n for n in p.lines[0].notes)

    def test_stale_offer_ineligible(self):
        p = propose([cand(offer_kw=dict(source_ts=NOW - timedelta(hours=25)))])
        assert p.lines == ()
        assert p.skipped[0].reason == "STALE_OFFER"

    @pytest.mark.parametrize("status", [AvailabilityStatus.OUT_OF_STOCK, AvailabilityStatus.DISCONTINUED])
    def test_upstream_unavailable(self, status):
        p = propose([cand(offer_kw=dict(availability_status=status))])
        assert p.skipped[0].reason == "UPSTREAM_UNAVAILABLE"

    @pytest.mark.parametrize(
        "kw,field",
        [(dict(carton_qty=None), "carton_qty"), (dict(moq=None), "moq"), (dict(availability_status=AvailabilityStatus.UNKNOWN), "availability_status")],
    )
    def test_unknown_fields_skipped(self, kw, field):
        p = propose([cand(offer_kw=kw)])
        assert p.skipped[0].reason == "UNKNOWN_FIELDS"
        assert field in p.skipped[0].detail

    def test_above_reorder_point(self):
        p = propose([cand(sellable_qty=10)])
        assert p.skipped[0].reason == "ABOVE_REORDER_POINT"

    def test_on_order_counts_in_position(self):
        p = propose([cand(sellable_qty=3, on_order_qty=7)])
        assert p.skipped[0].reason == "ABOVE_REORDER_POINT"

    def test_no_probable_sales(self):
        p = propose([cand(sellable_qty=0, avg_daily_sales=D("0"), safety_stock=0)])
        assert p.skipped[0].reason == "NO_PROBABLE_SALES"

    def test_invalid_cost(self):
        p = propose([cand(unit_cost_chf=D("0"))])
        assert p.skipped[0].reason == "INVALID_COST"

    def test_upstream_quantity_caps(self):
        p = propose([cand(unit_cost_chf=D("10"), offer_kw=dict(available_qty=10, carton_qty=6))])
        assert p.lines[0].qty == 6
        assert any("UPSTREAM_CAPPED" in n for n in p.lines[0].notes)
        p2 = propose([cand(unit_cost_chf=D("10"), offer_kw=dict(available_qty=4, carton_qty=6))])
        assert p2.skipped[0].reason == "INSUFFICIENT_UPSTREAM"

    def test_allocation_preferred_over_available(self):
        p = propose([cand(unit_cost_chf=D("10"), offer_kw=dict(available_qty=100, allocation_qty=5))])
        assert p.lines[0].qty == 5

    def test_unknown_upstream_quantity_flagged(self):
        p = propose([cand(unit_cost_chf=D("10"), offer_kw=dict(available_qty=None))])
        assert p.lines[0].qty == 20
        assert any("UPSTREAM_QTY_UNKNOWN" in n for n in p.lines[0].notes)

    def test_deterministic_hash(self):
        a = propose([cand()])
        b = propose([cand()])
        c = propose([cand()], budget_available=D("2999"))
        assert a.inputs_hash == b.inputs_hash != c.inputs_hash

    @pytest.mark.parametrize(
        "kw",
        [
            dict(budget_available=D("-1")),
            dict(extension_cap_pct=D("0")),
            dict(extension_cap_pct=D("1.5")),
            dict(cap_exceptions={"Alpha": D("2")}),
            dict(now=datetime(2026, 10, 4)),
        ],
    )
    def test_invalid_arguments(self, kw):
        with pytest.raises(StockError):
            propose([cand()], **kw)

    def test_duplicate_candidates(self):
        with pytest.raises(StockError):
            propose([cand(), cand()])
