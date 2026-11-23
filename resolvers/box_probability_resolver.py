"""Normalize item_group reward rates to effective chances (Etapa 4).

Algorithms (itemdb.cpp get_random_itemsubgroup):
- SharedPool / Random: weight = Rate; P = Rate / sum(Rate) for a fresh draw
  (SharedPool long-run frequency matches Random; first-draw odds identical).
- All: every entry is granted → chance 1 (per_10000 = 10000).
- Drop: independent check Rate/10000 (official chance).
"""

from __future__ import annotations

from typing import Any


def normalize_subgroup_chances(
    entries: list[dict[str, Any]], algorithm: str
) -> list[dict[str, Any]]:
    """Annotate each entry dict with chance_effective / chance_unit / chance_status.

    `entries` must include at least `rate` (YAML Rate). Mutates and returns same list.
    total_rate uses all entries with a numeric rate (server pool), even if some are
    later filtered for client display.
    """
    algo = (algorithm or "SharedPool").strip()
    rates: list[int] = []
    for e in entries:
        r = e.get("rate")
        rates.append(0 if r is None else int(r))

    if algo == "All":
        for e in entries:
            e["chance_effective"] = 10000
            e["chance_unit"] = "per_10000"
            e["chance_status"] = "guaranteed_all"
            e["subgroup_total_rate"] = None
        return entries

    if algo == "Drop":
        for e, r in zip(entries, rates):
            e["chance_effective"] = r  # already per_10000
            e["chance_unit"] = "per_10000"
            e["chance_status"] = "independent_drop"
            e["subgroup_total_rate"] = None
        return entries

    # SharedPool, Random, or unknown → weight normalize
    total = sum(rates)
    for e, r in zip(entries, rates):
        e["subgroup_total_rate"] = total
        if total <= 0:
            e["chance_effective"] = 0
            e["chance_unit"] = "per_10000"
            e["chance_status"] = "zero_pool"
        else:
            e["chance_effective"] = int(r * 10000 / total)
            e["chance_unit"] = "per_10000"
            e["chance_status"] = (
                "normalized_sharedpool"
                if algo == "SharedPool"
                else "normalized_random"
                if algo == "Random"
                else "normalized_weighted"
            )
    return entries
