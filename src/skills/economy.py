"""
Economy and Transaction Skills.

Implements SRD 5e currency and item transaction handling.
All currency stored internally as copper pieces for precision.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Currency conversion rates (to copper pieces)
COPPER_PER_SILVER = 10
COPPER_PER_GOLD = 100
COPPER_PER_PLATINUM = 1000


class Currency(BaseModel):
    """
    Currency holdings in standard D&D denominations.

    Internally converts to copper for all calculations.
    """

    pp: int = Field(default=0, ge=0, description="Platinum pieces")
    gp: int = Field(default=0, ge=0, description="Gold pieces")
    sp: int = Field(default=0, ge=0, description="Silver pieces")
    cp: int = Field(default=0, ge=0, description="Copper pieces")

    @property
    def total_copper(self) -> int:
        """Total value in copper pieces."""
        return (
            self.pp * COPPER_PER_PLATINUM
            + self.gp * COPPER_PER_GOLD
            + self.sp * COPPER_PER_SILVER
            + self.cp
        )

    @classmethod
    def from_copper(cls, copper: int) -> Currency:
        """Create Currency from total copper, using largest denominations first."""
        if copper < 0:
            raise ValueError("Cannot create currency from negative copper")

        pp = copper // COPPER_PER_PLATINUM
        copper %= COPPER_PER_PLATINUM

        gp = copper // COPPER_PER_GOLD
        copper %= COPPER_PER_GOLD

        sp = copper // COPPER_PER_SILVER
        cp = copper % COPPER_PER_SILVER

        return cls(pp=pp, gp=gp, sp=sp, cp=cp)

    def __add__(self, other: Currency) -> Currency:
        """Add two currency amounts."""
        return Currency.from_copper(self.total_copper + other.total_copper)

    def __sub__(self, other: Currency) -> Currency:
        """Subtract currency. Raises if result would be negative."""
        result = self.total_copper - other.total_copper
        if result < 0:
            raise ValueError("Insufficient funds")
        return Currency.from_copper(result)

    def __ge__(self, other: Currency) -> bool:
        """Check if this currency is >= other."""
        return self.total_copper >= other.total_copper

    def __gt__(self, other: Currency) -> bool:
        """Check if this currency is > other."""
        return self.total_copper > other.total_copper

    def __le__(self, other: Currency) -> bool:
        """Check if this currency is <= other."""
        return self.total_copper <= other.total_copper

    def __lt__(self, other: Currency) -> bool:
        """Check if this currency is < other."""
        return self.total_copper < other.total_copper

    def __eq__(self, other: object) -> bool:
        """Check if currencies are equal in value."""
        if not isinstance(other, Currency):
            return NotImplemented
        return self.total_copper == other.total_copper


class ItemStack(BaseModel):
    """A stack of identical items."""

    item_id: UUID | str = Field(description="Reference to item definition")
    name: str = Field(description="Display name")
    quantity: int = Field(default=1, ge=1)
    unit_value: Currency = Field(default_factory=Currency, description="Value per item")

    @property
    def total_value(self) -> Currency:
        """Total value of the stack."""
        return Currency.from_copper(self.unit_value.total_copper * self.quantity)


class TransactionType(StrEnum):
    """Types of economic transactions."""

    BUY = "buy"  # Actor pays currency, receives items
    SELL = "sell"  # Actor gives items, receives currency
    LOOT = "loot"  # Actor receives items/currency (no counterparty)
    TRADE = "trade"  # Actor exchanges items/currency with counterparty
    GIFT = "gift"  # Actor gives items/currency (no payment)


class ItemTransfer(BaseModel):
    """Record of items transferred in a transaction."""

    item_id: UUID | str
    name: str
    quantity: int = Field(default=1, ge=1)
    direction: Literal["to_actor", "from_actor"]


class TransactionResult(BaseModel):
    """Result of an economic transaction."""

    success: bool
    transaction_type: TransactionType
    actor_id: UUID | str
    counterparty_id: UUID | str | None = None
    items_transferred: list[ItemTransfer] = Field(default_factory=list)
    currency_delta: int = Field(
        description="Change in actor's wealth (copper). Positive = gained money."
    )
    actor_new_balance: Currency
    error: str | None = None


class Wallet(BaseModel):
    """A character's currency holdings with transaction methods."""

    owner_id: UUID | str
    balance: Currency = Field(default_factory=Currency)

    def can_afford(self, cost: Currency) -> bool:
        """Check if wallet can afford a cost."""
        return self.balance >= cost

    def add(self, amount: Currency) -> Currency:
        """Add currency to wallet. Returns new balance."""
        self.balance = self.balance + amount
        return self.balance

    def remove(self, amount: Currency) -> Currency:
        """Remove currency from wallet. Raises if insufficient. Returns new balance."""
        self.balance = self.balance - amount
        return self.balance


def calculate_buy_price(base_price: Currency, quantity: int = 1) -> Currency:
    """Calculate total purchase price."""
    return Currency.from_copper(base_price.total_copper * quantity)


def calculate_sell_price(
    base_price: Currency, quantity: int = 1, sell_ratio: float = 0.5
) -> Currency:
    """
    Calculate sell price (typically half of base price per SRD).

    Args:
        base_price: The item's base/purchase price
        quantity: Number of items being sold
        sell_ratio: Fraction of base price received (default 0.5 = 50%)
    """
    total_copper = int(base_price.total_copper * quantity * sell_ratio)
    return Currency.from_copper(total_copper)


def execute_purchase(
    buyer_wallet: Wallet,
    item: ItemStack,
    quantity: int = 1,
    seller_id: UUID | str | None = None,
) -> TransactionResult:
    """
    Execute a purchase transaction.

    Args:
        buyer_wallet: The buyer's wallet
        item: The item being purchased
        quantity: How many to buy
        seller_id: Optional seller identifier

    Returns:
        TransactionResult with success/failure and new balance
    """
    total_cost = calculate_buy_price(item.unit_value, quantity)

    if not buyer_wallet.can_afford(total_cost):
        return TransactionResult(
            success=False,
            transaction_type=TransactionType.BUY,
            actor_id=buyer_wallet.owner_id,
            counterparty_id=seller_id,
            currency_delta=0,
            actor_new_balance=buyer_wallet.balance,
            error=f"Insufficient funds. Need {total_cost.total_copper} cp, have {buyer_wallet.balance.total_copper} cp",
        )

    buyer_wallet.remove(total_cost)

    return TransactionResult(
        success=True,
        transaction_type=TransactionType.BUY,
        actor_id=buyer_wallet.owner_id,
        counterparty_id=seller_id,
        items_transferred=[
            ItemTransfer(
                item_id=item.item_id,
                name=item.name,
                quantity=quantity,
                direction="to_actor",
            )
        ],
        currency_delta=-total_cost.total_copper,
        actor_new_balance=buyer_wallet.balance,
    )


def execute_sale(
    seller_wallet: Wallet,
    item: ItemStack,
    quantity: int = 1,
    buyer_id: UUID | str | None = None,
    sell_ratio: float = 0.5,
) -> TransactionResult:
    """
    Execute a sale transaction.

    Args:
        seller_wallet: The seller's wallet
        item: The item being sold
        quantity: How many to sell
        buyer_id: Optional buyer identifier
        sell_ratio: Fraction of base price received (default 0.5)

    Returns:
        TransactionResult with success and new balance
    """
    payment = calculate_sell_price(item.unit_value, quantity, sell_ratio)

    seller_wallet.add(payment)

    return TransactionResult(
        success=True,
        transaction_type=TransactionType.SELL,
        actor_id=seller_wallet.owner_id,
        counterparty_id=buyer_id,
        items_transferred=[
            ItemTransfer(
                item_id=item.item_id,
                name=item.name,
                quantity=quantity,
                direction="from_actor",
            )
        ],
        currency_delta=payment.total_copper,
        actor_new_balance=seller_wallet.balance,
    )


def execute_loot(
    looter_wallet: Wallet,
    currency: Currency | None = None,
    items: list[ItemStack] | None = None,
) -> TransactionResult:
    """
    Execute a loot transaction (finding treasure).

    Args:
        looter_wallet: The looter's wallet
        currency: Currency found
        items: Items found

    Returns:
        TransactionResult with loot details
    """
    currency_gained = 0
    if currency:
        looter_wallet.add(currency)
        currency_gained = currency.total_copper

    items_transferred = []
    if items:
        for item in items:
            items_transferred.append(
                ItemTransfer(
                    item_id=item.item_id,
                    name=item.name,
                    quantity=item.quantity,
                    direction="to_actor",
                )
            )

    return TransactionResult(
        success=True,
        transaction_type=TransactionType.LOOT,
        actor_id=looter_wallet.owner_id,
        counterparty_id=None,
        items_transferred=items_transferred,
        currency_delta=currency_gained,
        actor_new_balance=looter_wallet.balance,
    )


def convert_currency(amount: int, from_denom: str, to_denom: str) -> int:
    """
    Convert currency between denominations.

    Args:
        amount: Amount in source denomination
        from_denom: Source denomination (pp, gp, sp, cp)
        to_denom: Target denomination (pp, gp, sp, cp)

    Returns:
        Amount in target denomination (truncates fractional amounts)
    """
    # Convert to copper first
    denom_to_copper = {
        "pp": COPPER_PER_PLATINUM,
        "gp": COPPER_PER_GOLD,
        "sp": COPPER_PER_SILVER,
        "cp": 1,
    }

    if from_denom not in denom_to_copper:
        raise ValueError(f"Unknown denomination: {from_denom}")
    if to_denom not in denom_to_copper:
        raise ValueError(f"Unknown denomination: {to_denom}")

    copper = amount * denom_to_copper[from_denom]
    return copper // denom_to_copper[to_denom]
