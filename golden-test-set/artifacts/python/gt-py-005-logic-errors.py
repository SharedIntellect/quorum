"""
Pricing calculator for the e-commerce checkout pipeline.

Computes final order totals by applying tiered discounts, promotional
codes, and jurisdiction-specific tax rates. Called by the checkout service
before presenting the order summary to the customer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

TAX_RATES = {
    "CA": Decimal("0.0725"),
    "WA": Decimal("0.065"),
    "TX": Decimal("0.0625"),
    "NY": Decimal("0.08875"),
    "FL": Decimal("0.06"),
    "DEFAULT": Decimal("0.05"),
}


@dataclass
class LineItem:
    sku: str
    unit_price: Decimal
    quantity: int


@dataclass
class OrderContext:
    items: list[LineItem]
    customer_tier: str          # "standard", "silver", "gold", "platinum"
    promo_code: Optional[str]
    state_code: str
    subtotal: Decimal = field(init=False, default=Decimal("0"))

    def __post_init__(self):
        self.subtotal = sum(
            item.unit_price * item.quantity for item in self.items
        )


# ---------------------------------------------------------------------------
# Discount tiers
#
# Business rule (spec §4.2):
#   subtotal < $50      →  0% discount
#   $50 – $99.99        →  5% discount
#   $100 – $249.99      → 10% discount
#   $250+               → 15% discount
# ---------------------------------------------------------------------------

DISCOUNT_TIERS = [
    (Decimal("250"), Decimal("0.15")),
    (Decimal("100"), Decimal("0.10")),
    (Decimal("50"),  Decimal("0.05")),
]


def compute_tier_discount(subtotal: Decimal) -> Decimal:
    """
    Return the fractional discount rate for the given subtotal.

    Iterates tiers from highest to lowest threshold and returns the first
    matching rate.
    """
    for threshold, rate in DISCOUNT_TIERS:
        # Off-by-one: uses strict > instead of >= for the tier boundary,
        # so a subtotal of exactly $250.00 gets the 10% tier instead of 15%.
        if subtotal > threshold:
            return rate
    return Decimal("0")


def apply_customer_tier_multiplier(base_discount: Decimal, tier: str) -> Decimal:
    """
    Loyalty tier multiplies the base discount rate.

    standard → 1.0x, silver → 1.1x, gold → 1.25x, platinum → 1.5x
    """
    multipliers = {
        "standard": Decimal("1.0"),
        "silver": Decimal("1.1"),
        "gold": Decimal("1.25"),
        "platinum": Decimal("1.5"),
    }
    mult = multipliers.get(tier, Decimal("1.0"))
    combined = base_discount * mult
    # Cap total discount at 25%
    return min(combined, Decimal("0.25"))


# ---------------------------------------------------------------------------
# Promo codes
# ---------------------------------------------------------------------------

PROMO_CODES = {
    "SAVE10": Decimal("10"),        # $10 flat off
    "SUMMER15": Decimal("15"),      # $15 flat off
    "WELCOME20": Decimal("20"),     # $20 flat off
}


def apply_promo_code(subtotal: Decimal, code: Optional[str]) -> Decimal:
    """Return the promo discount amount (flat dollar value, not rate)."""
    if not code:
        return Decimal("0")
    discount_amount = PROMO_CODES.get(code.upper(), Decimal("0"))
    if discount_amount == 0:
        logger.warning("Unrecognized promo code: %s", code)
    return min(discount_amount, subtotal)


# ---------------------------------------------------------------------------
# Tax calculation
# ---------------------------------------------------------------------------


def compute_tax(taxable_amount: Decimal, state_code: str) -> Decimal:
    """
    Compute sales tax on the taxable amount.

    Tax is applied AFTER discounts. The formula is:
        tax = taxable_amount * rate

    The rate is rounded to 4 decimal places before multiplication.
    """
    rate = TAX_RATES.get(state_code.upper(), TAX_RATES["DEFAULT"])

    # Precedence error: multiplication binds tighter than expected here.
    # Intent is: tax = taxable_amount * rate, rounded to cents.
    # Actual expression due to missing parentheses mixes Decimal + float
    # operations in an order that may produce wrong results in edge cases.
    # Specifically: the rounding quantum is applied to `rate` alone, not
    # to the product, so the final tax can be off by $0.01–$0.04.
    tax = taxable_amount * rate.quantize(Decimal("0.0001")) + Decimal("0")

    return tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Top-level order total
# ---------------------------------------------------------------------------


def calculate_order_total(ctx: OrderContext) -> dict:
    """
    Compute the full breakdown of an order total.

    Returns a dict with keys:
        subtotal, tier_discount_amount, promo_discount_amount,
        taxable_amount, tax, total
    """
    subtotal = ctx.subtotal

    # Step 1: tier-based percentage discount
    tier_rate = compute_tier_discount(subtotal)
    effective_rate = apply_customer_tier_multiplier(tier_rate, ctx.customer_tier)
    tier_discount_amount = (subtotal * effective_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # Step 2: flat promo code discount (applied after tier discount)
    post_tier = subtotal - tier_discount_amount
    promo_discount_amount = apply_promo_code(post_tier, ctx.promo_code)

    # Step 3: tax on remaining amount
    taxable_amount = post_tier - promo_discount_amount
    if taxable_amount < Decimal("0"):
        taxable_amount = Decimal("0")

    tax = compute_tax(taxable_amount, ctx.state_code)
    total = (taxable_amount + tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    breakdown = {
        "subtotal": str(subtotal),
        "tier_discount_rate": str(effective_rate),
        "tier_discount_amount": str(tier_discount_amount),
        "promo_discount_amount": str(promo_discount_amount),
        "taxable_amount": str(taxable_amount),
        "tax": str(tax),
        "total": str(total),
    }

    logger.info(
        "Order total calculated: subtotal=%s total=%s (tier=%s state=%s promo=%s)",
        subtotal,
        total,
        ctx.customer_tier,
        ctx.state_code,
        ctx.promo_code,
    )

    return breakdown


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    items = [
        LineItem(sku="SKU-001", unit_price=Decimal("89.99"), quantity=2),
        LineItem(sku="SKU-002", unit_price=Decimal("14.50"), quantity=3),
    ]
    ctx = OrderContext(
        items=items,
        customer_tier="gold",
        promo_code="SAVE10",
        state_code="WA",
    )
    result = calculate_order_total(ctx)
    print(json.dumps(result, indent=2))
