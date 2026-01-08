"""Tests for economy and transaction skills."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.skills.economy import (
    COPPER_PER_GOLD,
    COPPER_PER_PLATINUM,
    COPPER_PER_SILVER,
    Currency,
    ItemStack,
    TransactionType,
    Wallet,
    calculate_buy_price,
    calculate_sell_price,
    convert_currency,
    execute_loot,
    execute_purchase,
    execute_sale,
)

# --- Currency Tests ---


class TestCurrency:
    """Tests for Currency model."""

    def test_default_values(self):
        c = Currency()
        assert c.pp == 0
        assert c.gp == 0
        assert c.sp == 0
        assert c.cp == 0

    def test_total_copper_empty(self):
        c = Currency()
        assert c.total_copper == 0

    def test_total_copper_all_denominations(self):
        c = Currency(pp=1, gp=2, sp=3, cp=4)
        expected = 1 * COPPER_PER_PLATINUM + 2 * COPPER_PER_GOLD + 3 * COPPER_PER_SILVER + 4
        assert c.total_copper == expected
        assert c.total_copper == 1234  # 1000 + 200 + 30 + 4

    def test_from_copper_zero(self):
        c = Currency.from_copper(0)
        assert c.pp == 0
        assert c.gp == 0
        assert c.sp == 0
        assert c.cp == 0

    def test_from_copper_uses_largest_first(self):
        # 1234 cp = 1 pp, 2 gp, 3 sp, 4 cp
        c = Currency.from_copper(1234)
        assert c.pp == 1
        assert c.gp == 2
        assert c.sp == 3
        assert c.cp == 4

    def test_from_copper_negative_raises(self):
        with pytest.raises(ValueError, match="negative"):
            Currency.from_copper(-100)

    def test_addition(self):
        c1 = Currency(gp=10)
        c2 = Currency(gp=5, sp=5)
        result = c1 + c2
        assert result.total_copper == 1550  # 1000 + 500 + 50

    def test_subtraction(self):
        c1 = Currency(gp=10)
        c2 = Currency(gp=3)
        result = c1 - c2
        assert result.total_copper == 700

    def test_subtraction_insufficient_raises(self):
        c1 = Currency(gp=5)
        c2 = Currency(gp=10)
        with pytest.raises(ValueError, match="Insufficient"):
            c1 - c2

    def test_comparison_equal(self):
        c1 = Currency(gp=1)
        c2 = Currency(sp=10)
        assert c1 == c2

    def test_comparison_greater(self):
        c1 = Currency(gp=10)
        c2 = Currency(gp=5)
        assert c1 > c2
        assert c1 >= c2

    def test_comparison_less(self):
        c1 = Currency(gp=5)
        c2 = Currency(gp=10)
        assert c1 < c2
        assert c1 <= c2


class TestConvertCurrency:
    """Tests for currency conversion."""

    def test_gold_to_silver(self):
        assert convert_currency(1, "gp", "sp") == 10

    def test_platinum_to_gold(self):
        assert convert_currency(1, "pp", "gp") == 10

    def test_silver_to_copper(self):
        assert convert_currency(1, "sp", "cp") == 10

    def test_copper_to_gold_truncates(self):
        # 50 cp = 0.5 gp, truncates to 0
        assert convert_currency(50, "cp", "gp") == 0
        # 100 cp = 1 gp
        assert convert_currency(100, "cp", "gp") == 1

    def test_invalid_denomination_raises(self):
        with pytest.raises(ValueError, match="Unknown denomination"):
            convert_currency(10, "ep", "gp")  # Electrum not supported


# --- Wallet Tests ---


class TestWallet:
    """Tests for Wallet model."""

    def test_default_empty(self):
        w = Wallet(owner_id="player1")
        assert w.balance.total_copper == 0

    def test_can_afford_true(self):
        w = Wallet(owner_id="player1", balance=Currency(gp=100))
        assert w.can_afford(Currency(gp=50)) is True

    def test_can_afford_false(self):
        w = Wallet(owner_id="player1", balance=Currency(gp=10))
        assert w.can_afford(Currency(gp=50)) is False

    def test_can_afford_exact(self):
        w = Wallet(owner_id="player1", balance=Currency(gp=50))
        assert w.can_afford(Currency(gp=50)) is True

    def test_add_currency(self):
        w = Wallet(owner_id="player1", balance=Currency(gp=10))
        new_balance = w.add(Currency(gp=5))
        assert new_balance.total_copper == 1500
        assert w.balance.total_copper == 1500

    def test_remove_currency(self):
        w = Wallet(owner_id="player1", balance=Currency(gp=10))
        new_balance = w.remove(Currency(gp=3))
        assert new_balance.total_copper == 700
        assert w.balance.total_copper == 700

    def test_remove_insufficient_raises(self):
        w = Wallet(owner_id="player1", balance=Currency(gp=5))
        with pytest.raises(ValueError, match="Insufficient"):
            w.remove(Currency(gp=10))


# --- ItemStack Tests ---


class TestItemStack:
    """Tests for ItemStack model."""

    def test_single_item(self):
        item = ItemStack(
            item_id="sword_001",
            name="Longsword",
            quantity=1,
            unit_value=Currency(gp=15),
        )
        assert item.total_value.total_copper == 1500

    def test_multiple_items(self):
        item = ItemStack(
            item_id="arrow_001",
            name="Arrow",
            quantity=20,
            unit_value=Currency(cp=5),
        )
        assert item.total_value.total_copper == 100


# --- Transaction Tests ---


class TestExecutePurchase:
    """Tests for purchase transactions."""

    def test_successful_purchase(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=100))
        item = ItemStack(
            item_id="potion_001",
            name="Healing Potion",
            unit_value=Currency(gp=50),
        )

        result = execute_purchase(wallet, item, quantity=1)

        assert result.success is True
        assert result.transaction_type == TransactionType.BUY
        assert result.currency_delta == -5000  # Lost 50 gp
        assert len(result.items_transferred) == 1
        assert result.items_transferred[0].direction == "to_actor"
        assert wallet.balance.total_copper == 5000  # 50 gp remaining

    def test_purchase_multiple(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=100))
        item = ItemStack(
            item_id="arrow_001",
            name="Arrow",
            unit_value=Currency(sp=1),
        )

        result = execute_purchase(wallet, item, quantity=20)

        assert result.success is True
        assert result.currency_delta == -200  # 20 sp = 200 cp
        assert result.items_transferred[0].quantity == 20

    def test_purchase_insufficient_funds(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=10))
        item = ItemStack(
            item_id="armor_001",
            name="Plate Armor",
            unit_value=Currency(gp=1500),
        )

        result = execute_purchase(wallet, item, quantity=1)

        assert result.success is False
        assert "Insufficient funds" in result.error
        assert wallet.balance.total_copper == 1000  # Unchanged

    def test_purchase_with_seller(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=100))
        seller_id = uuid4()
        item = ItemStack(
            item_id="item_001",
            name="Widget",
            unit_value=Currency(gp=10),
        )

        result = execute_purchase(wallet, item, quantity=1, seller_id=seller_id)

        assert result.counterparty_id == seller_id


class TestExecuteSale:
    """Tests for sale transactions."""

    def test_successful_sale_half_price(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=0))
        item = ItemStack(
            item_id="sword_001",
            name="Longsword",
            unit_value=Currency(gp=30),  # Base price
        )

        result = execute_sale(wallet, item, quantity=1)

        assert result.success is True
        assert result.transaction_type == TransactionType.SELL
        # Default 50% sell price: 30 gp / 2 = 15 gp = 1500 cp
        assert result.currency_delta == 1500
        assert len(result.items_transferred) == 1
        assert result.items_transferred[0].direction == "from_actor"
        assert wallet.balance.total_copper == 1500

    def test_sale_custom_ratio(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=0))
        item = ItemStack(
            item_id="gem_001",
            name="Ruby",
            unit_value=Currency(gp=100),
        )

        # Gems sell at 100% value
        result = execute_sale(wallet, item, quantity=1, sell_ratio=1.0)

        assert result.currency_delta == 10000  # Full 100 gp

    def test_sale_multiple_items(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=0))
        item = ItemStack(
            item_id="arrow_001",
            name="Arrow",
            unit_value=Currency(sp=1),
        )

        result = execute_sale(wallet, item, quantity=20, sell_ratio=0.5)

        # 20 arrows * 1 sp * 0.5 = 10 sp = 100 cp
        assert result.currency_delta == 100


class TestExecuteLoot:
    """Tests for loot transactions."""

    def test_loot_currency_only(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=10))

        result = execute_loot(wallet, currency=Currency(gp=50, sp=30))

        assert result.success is True
        assert result.transaction_type == TransactionType.LOOT
        assert result.counterparty_id is None
        assert result.currency_delta == 5300  # 50 gp + 30 sp
        assert wallet.balance.total_copper == 6300

    def test_loot_items_only(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=0))
        items = [
            ItemStack(item_id="gem_001", name="Ruby", quantity=2),
            ItemStack(item_id="sword_001", name="Magic Sword", quantity=1),
        ]

        result = execute_loot(wallet, items=items)

        assert result.success is True
        assert result.currency_delta == 0
        assert len(result.items_transferred) == 2
        assert all(t.direction == "to_actor" for t in result.items_transferred)

    def test_loot_currency_and_items(self):
        wallet = Wallet(owner_id="player1", balance=Currency(gp=0))
        items = [ItemStack(item_id="gem_001", name="Diamond", quantity=1)]

        result = execute_loot(wallet, currency=Currency(gp=100), items=items)

        assert result.currency_delta == 10000
        assert len(result.items_transferred) == 1


class TestCalculatePrices:
    """Tests for price calculation utilities."""

    def test_buy_price_single(self):
        price = calculate_buy_price(Currency(gp=50), quantity=1)
        assert price.total_copper == 5000

    def test_buy_price_multiple(self):
        price = calculate_buy_price(Currency(gp=10), quantity=5)
        assert price.total_copper == 5000

    def test_sell_price_default_ratio(self):
        price = calculate_sell_price(Currency(gp=100), quantity=1)
        assert price.total_copper == 5000  # 50%

    def test_sell_price_custom_ratio(self):
        price = calculate_sell_price(Currency(gp=100), quantity=1, sell_ratio=0.75)
        assert price.total_copper == 7500

    def test_sell_price_multiple(self):
        price = calculate_sell_price(Currency(gp=10), quantity=4, sell_ratio=0.5)
        assert price.total_copper == 2000  # 4 * 10 gp * 0.5 = 20 gp
