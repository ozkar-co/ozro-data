"""Central battle-conf merge + effective value helpers (Etapa 4).

Load order matches conf/battle_athena.conf: each conf/battle/*.conf, then
conf/import/battle_conf.txt. Extractors must not re-parse battle conf themselves.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from discovery.scan import _load_extractor_config

_IMPORT_RE = re.compile(r"^import:\s*(\S+)\s*$")
_KV_RE = re.compile(r"^([^:]+):\s*(.*)$")

# rAthena config_switch truthy / falsy tokens (strlib.cpp)
_TRUE = frozenset({"on", "yes", "oui", "ja", "si", "sim", "true"})
_FALSE = frozenset({"off", "no", "non", "nein", "nao", "false"})

# UINT32_MAX — mob status.max_hp cap after monster_hp_rate / mvp_hp_rate
_HP_CAP = 0xFFFFFFFF


def _strip_comment(line: str) -> str:
    return line.split("//", 1)[0].strip()


def _parse_value(raw: str) -> int | str:
    """Parse a battle conf value the way rAthena stores ints (config_switch)."""
    val = raw.strip()
    low = val.lower()
    if low in _TRUE:
        return 1
    if low in _FALSE:
        return 0
    try:
        # strtol base 0: 0x.., 0.., decimal
        return int(val, 0)
    except ValueError:
        return val


def _parse_conf_file(path: Path) -> dict[str, int | str]:
    out: dict[str, int | str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = _strip_comment(raw)
        if not line or line.startswith("import:"):
            continue
        m = _KV_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip()
        out[key] = _parse_value(m.group(2))
    return out


def _battle_import_chain(rathena: Path, battle_athena: str) -> list[Path]:
    """Resolve import list from battle_athena.conf (order preserved)."""
    root_path = rathena / battle_athena
    chain: list[Path] = []
    if root_path.is_file():
        for raw in root_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = _strip_comment(raw)
            m = _IMPORT_RE.match(line)
            if m:
                chain.append(rathena / m.group(1))
    if not chain:
        # Fallback if battle_athena missing: battle_dir/*.conf then import
        battle_dir = rathena / "conf" / "battle"
        if battle_dir.is_dir():
            chain.extend(sorted(battle_dir.glob("*.conf")))
        chain.append(rathena / "conf" / "import" / "battle_conf.txt")
    return chain


class ConfigurationResolver:
    """Merged effective battle configuration for OzRo."""

    def __init__(
        self,
        values: dict[str, int | str],
        *,
        sources: list[str],
        rathena: Path,
    ) -> None:
        self._values = values
        self.sources = sources
        self.rathena = rathena

    @classmethod
    def from_project(cls, project_root: Path | None = None) -> ConfigurationResolver:
        root = project_root or Path(__file__).resolve().parents[1]
        cfg = _load_extractor_config(root)
        rathena = Path(cfg["paths"]["rathena"])
        battle_athena = cfg.get("conf", {}).get("battle_athena", "conf/battle_athena.conf")
        chain = _battle_import_chain(rathena, battle_athena)
        merged: dict[str, int | str] = {}
        sources: list[str] = []
        for path in chain:
            if not path.is_file():
                continue
            rel = str(path.relative_to(rathena)) if path.is_relative_to(rathena) else str(path)
            sources.append(rel)
            merged.update(_parse_conf_file(path))
        return cls(merged, sources=sources, rathena=rathena)

    # --- raw access ---------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        val = self._values.get(key, default)
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            try:
                return int(val, 0)
            except ValueError:
                return default
        return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        if key not in self._values:
            return default
        val = self._values[key]
        if isinstance(val, int):
            return val != 0
        if isinstance(val, str):
            low = val.lower()
            if low in _TRUE:
                return True
            if low in _FALSE:
                return False
        return bool(val)

    def all_values(self) -> dict[str, int | str]:
        return dict(self._values)

    # --- domain snapshots ---------------------------------------------------

    def drop_rates(self) -> dict[str, int]:
        """item_rate_* / item_drop_* / caps / drop flags (§24.4)."""
        out: dict[str, int] = {}
        for key, val in self._values.items():
            if not (
                key.startswith("item_rate_")
                or key.startswith("item_drop_")
                or key
                in (
                    "drop_rateincrease",
                    "item_logarithmic_drops",
                    "enable_bonus_map_drops",
                    "drop_rate_cap",
                    "drop_rate_cap_vip",
                )
            ):
                continue
            if isinstance(val, int):
                out[key] = val
            else:
                try:
                    out[key] = int(str(val), 0)
                except ValueError:
                    continue
        return out

    def rates_catalog(self) -> list[dict[str, Any]]:
        """Flat catalog for ozro_dataset_rates (§24.4). unit: 100 = 1x for *_rate*."""
        rows: list[dict[str, Any]] = []

        def _add(key: str, value: int, group: str, unit: str) -> None:
            rows.append(
                {
                    "key": key,
                    "value": value,
                    "group": group,
                    "unit": unit,
                }
            )

        for key, value in sorted(self.hp_rates().items()):
            _add(key, value, "hp", "percent_of_base_100")
        for key, value in sorted(self.exp_rates().items()):
            _add(key, value, "exp", "percent_of_base_100")

        drops = self.drop_rates()
        for key in sorted(drops):
            if key.startswith("item_rate_"):
                _add(key, drops[key], "drops", "percent_of_base_100")
            elif key.startswith("item_drop_") or key in (
                "drop_rate_cap",
                "drop_rate_cap_vip",
            ):
                _add(key, drops[key], "drop_bounds", "per_10000")
            elif key in (
                "drop_rateincrease",
                "item_logarithmic_drops",
                "enable_bonus_map_drops",
            ):
                _add(key, drops[key], "drop_flags", "bool_int")
        return rows

    def exp_rates(self) -> dict[str, int]:
        keys = (
            "base_exp_rate",
            "job_exp_rate",
            "mvp_exp_rate",
            "quest_exp_rate",
        )
        return {k: self.get_int(k, 100) for k in keys}

    def hp_rates(self) -> dict[str, int]:
        return {
            "monster_hp_rate": self.get_int("monster_hp_rate", 100),
            "mvp_hp_rate": self.get_int("mvp_hp_rate", 100),
        }

    def features(self) -> dict[str, bool]:
        return {
            k: self.get_bool(k)
            for k in sorted(self._values)
            if k.startswith("feature.")
        }

    # --- effective transforms (rAthena semantics) ---------------------------

    def hp_rate_pct(self, *, is_mvp: bool) -> int:
        """Percent multiplier: MVP → mvp_hp_rate, else monster_hp_rate."""
        if is_mvp:
            return self.get_int("mvp_hp_rate", 100)
        return self.get_int("monster_hp_rate", 100)

    def apply_hp(self, hp_base: int | None, *, is_mvp: bool) -> tuple[int | None, int]:
        """Return (hp_effective, hp_multiplier_pct). None base → (None, rate)."""
        rate = self.hp_rate_pct(is_mvp=is_mvp)
        if hp_base is None:
            return None, rate
        if rate == 100:
            return int(hp_base), rate
        # mob.cpp loadingFinished: maxhp * rate / 100, cap [1, UINT32_MAX]
        effective = int(float(hp_base) * float(rate) / 100.0)
        effective = max(1, min(_HP_CAP, effective))
        return effective, rate

    def apply_base_exp(self, exp: int | None) -> int | None:
        if exp is None:
            return None
        rate = self.get_int("base_exp_rate", 100)
        return int(float(exp) * float(rate) / 100.0)

    def apply_job_exp(self, exp: int | None) -> int | None:
        if exp is None:
            return None
        rate = self.get_int("job_exp_rate", 100)
        return int(float(exp) * float(rate) / 100.0)

    def apply_mvp_exp(self, exp: int | None) -> int | None:
        if exp is None:
            return None
        rate = self.get_int("mvp_exp_rate", 100)
        return int(float(exp) * float(rate) / 100.0)

    def apply_quest_exp(self, exp: int | None) -> int | None:
        if exp is None:
            return None
        rate = self.get_int("quest_exp_rate", 100)
        return int(float(exp) * float(rate) / 100.0)

    def mob_drop_adjust(
        self, baserate: int, rate_adjust: int, rate_min: int, rate_max: int
    ) -> int:
        """Linear path of mob_drop_adjust (logarithmic_drops off on OzRo)."""
        if rate_adjust == 0:
            return 0
        rate = baserate * rate_adjust / 100.0
        return int(max(rate_min, min(rate_max, rate)))

    def snapshot(self) -> dict[str, Any]:
        """§24.4 rates catalog + nested views for audit. Not editorial features copy."""
        catalog = self.rates_catalog()
        drops = self.drop_rates()
        return {
            "schema_version": 1,
            "unit_note": "For *_rate* keys, 100 = 1x (percent_of_base_100).",
            "sources": list(self.sources),
            "catalog": catalog,
            "catalog_count": len(catalog),
            "hp": self.hp_rates(),
            "exp": self.exp_rates(),
            "drops": {
                k: v
                for k, v in sorted(drops.items())
                if k.startswith("item_rate_")
                or k
                in (
                    "drop_rateincrease",
                    "item_logarithmic_drops",
                    "enable_bonus_map_drops",
                )
            },
            "drop_bounds": {
                k: v
                for k, v in sorted(drops.items())
                if k.startswith("item_drop_")
                or k in ("drop_rate_cap", "drop_rate_cap_vip")
            },
            "features": self.features(),
            "ozro_highlights": {
                "monster_hp_rate": self.get_int("monster_hp_rate", 100),
                "mvp_hp_rate": self.get_int("mvp_hp_rate", 100),
                "base_exp_rate": self.get_int("base_exp_rate", 100),
                "job_exp_rate": self.get_int("job_exp_rate", 100),
                "mvp_exp_rate": self.get_int("mvp_exp_rate", 100),
                "quest_exp_rate": self.get_int("quest_exp_rate", 100),
                "item_rate_common": self.get_int("item_rate_common", 100),
                "item_rate_equip": self.get_int("item_rate_equip", 100),
                "item_rate_card": self.get_int("item_rate_card", 100),
                "item_rate_card_mvp": self.get_int("item_rate_card_mvp", 100),
                "item_rate_common_mvp": self.get_int("item_rate_common_mvp", 100),
                "item_rate_equip_mvp": self.get_int("item_rate_equip_mvp", 100),
                "item_rate_mvp": self.get_int("item_rate_mvp", 100),
                "item_rate_treasure": self.get_int("item_rate_treasure", 100),
                "item_rate_adddrop": self.get_int("item_rate_adddrop", 100),
                "drop_rate_cap": self.get_int("drop_rate_cap", 9000),
                "enable_bonus_map_drops": self.get_bool("enable_bonus_map_drops"),
                "item_logarithmic_drops": self.get_bool("item_logarithmic_drops"),
                "feature.barter": self.get_bool("feature.barter"),
            },
            "policy_notes": {
                "mvp_floor_drops": (
                    "item_rate_*_mvp remain 100 (1x) except card_mvp=10000; "
                    "verified via @rates/@mi (Eddga); not a missing-import bug"
                ),
            },
        }
