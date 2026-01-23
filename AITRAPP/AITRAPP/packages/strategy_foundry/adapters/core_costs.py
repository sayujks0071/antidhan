from dataclasses import dataclass

@dataclass
class CostModel:
    slippage_bps: float
    brokerage_per_order: float
    tax_bps: float
    spread_guard_bps: float

    def calculate_cost(self, price: float, quantity: int, side: str) -> float:
        """
        Calculate total cost (Slippage + Brokerage + Tax) for a trade.
        """
        value = price * quantity

        # Slippage (BPS)
        slippage_cost = value * (self.slippage_bps / 10000.0)

        # Taxes (BPS)
        tax_cost = value * (self.tax_bps / 10000.0)

        # Brokerage (Flat)
        brokerage_cost = self.brokerage_per_order

        return slippage_cost + tax_cost + brokerage_cost

    def get_slippage_price(self, price: float, side: int) -> float:
        """
        Adjust price for slippage.
        Side: 1 (Buy), -1 (Sell)
        """
        slippage_pct = self.slippage_bps / 10000.0
        if side == 1:
            return price * (1 + slippage_pct)
        else:
            return price * (1 - slippage_pct)
