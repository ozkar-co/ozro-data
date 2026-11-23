"""Native Buy/Sell resolution (rAthena itemdb.cpp loadingFinished)."""

from __future__ import annotations

from typing import Any


def resolve_buy_sell(
    buy: int | None, sell: int | None
) -> dict[str, Any]:
    """Derive effective NPC buy/sell from YAML Buy/Sell.

    Rules (itemdb.cpp):
    - missing Buy, has Sell → buy = sell * 2
    - has Buy, missing Sell → sell = buy / 2 (integer)
    - both missing → 0 / 0 (struct defaults)
    - if buy/124 < sell/75 → sell forced to 1 (zeny exploit guard)
    """
    has_buy = buy is not None
    has_sell = sell is not None
    buy_i = int(buy) if has_buy else None
    sell_i = int(sell) if has_sell else None
    buy_source = "yaml" if has_buy else None
    sell_source = "yaml" if has_sell else None
    derived = False

    if not has_buy and has_sell:
        buy_i = sell_i * 2
        buy_source = "derived_from_sell"
        derived = True
    elif has_buy and not has_sell:
        sell_i = buy_i // 2
        sell_source = "derived_from_buy"
        derived = True
    elif not has_buy and not has_sell:
        buy_i = 0
        sell_i = 0
        buy_source = "default_zero"
        sell_source = "default_zero"

    if buy_i is not None and sell_i is not None and buy_i / 124.0 < sell_i / 75.0:
        sell_i = 1
        sell_source = "exploit_cap"
        derived = True

    return {
        "buy_effective": buy_i,
        "sell_effective": sell_i,
        "buy_source": buy_source,
        "sell_source": sell_source,
        "value_was_derived": derived,
    }


def shop_price_effective(
    price_raw: int, *, shop_type: str, item_buy_effective: int | None
) -> dict[str, Any]:
    """Resolve shop header price; -1 → item_db buy for shop/marketshop else 0.

    Matches npc.cpp npc_parse_shop when value < 0.
    """
    price_is_default = price_raw < 0
    if not price_is_default:
        return {
            "price": price_raw,
            "price_effective": price_raw,
            "price_is_default": False,
            "price_source": "shop_header",
        }
    if shop_type in ("shop", "marketshop"):
        buy = 0 if item_buy_effective is None else int(item_buy_effective)
        return {
            "price": price_raw,
            "price_effective": buy,
            "price_is_default": True,
            "price_source": "item_buy_effective",
        }
    return {
        "price": price_raw,
        "price_effective": 0,
        "price_is_default": True,
        "price_source": "non_zeny_shop_default_zero",
    }
