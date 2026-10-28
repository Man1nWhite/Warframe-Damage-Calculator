from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def excel_round(value: float, digits: int = 0) -> float:
    quant = Decimal("1") if digits == 0 else Decimal("1").scaleb(-digits)
    rounded = Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)
    return float(rounded)
