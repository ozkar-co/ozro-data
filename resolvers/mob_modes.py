"""Effective mob modes = AI bitmask ∨ YAML Modes ∨ Class overlays.

Mirrors rAthena MobDatabase parse (Ai / Modes) + loadingFinished (Class),
with monster_active_enable assumed on (OzRo default: do not strip Aggressive).

Original YAML Modes stay in ozro_mobs.modes; this layer is modes_effective.
"""

from __future__ import annotations

from typing import Any

# e_mode bits — src/common/mmo.hpp
MD_CANMOVE = 0x0000001
MD_LOOTER = 0x0000002
MD_AGGRESSIVE = 0x0000004
MD_ASSIST = 0x0000008
MD_CASTSENSORIDLE = 0x0000010
MD_NORANDOMWALK = 0x0000020
MD_NOCAST = 0x0000040
MD_CANATTACK = 0x0000080
MD_CASTSENSORCHASE = 0x0000200
MD_CHANGECHASE = 0x0000400
MD_ANGRY = 0x0000800
MD_CHANGETARGETMELEE = 0x0001000
MD_CHANGETARGETCHASE = 0x0002000
MD_TARGETWEAK = 0x0004000
MD_RANDOMTARGET = 0x0008000
MD_IGNOREMELEE = 0x0010000
MD_IGNOREMAGIC = 0x0020000
MD_IGNORERANGED = 0x0040000
MD_MVP = 0x0080000
MD_IGNOREMISC = 0x0100000
MD_KNOCKBACKIMMUNE = 0x0200000
MD_TELEPORTBLOCK = 0x0400000
MD_FIXEDITEMDROP = 0x1000000
MD_DETECTOR = 0x2000000
MD_STATUSIMMUNE = 0x4000000
MD_SKILLIMMUNE = 0x8000000

# Bit → encyclopedia / YAML-style name (MD_FOO → Foo, Ignore* kept)
_BIT_NAMES: list[tuple[int, str]] = [
    (MD_CANMOVE, "CanMove"),
    (MD_LOOTER, "Looter"),
    (MD_AGGRESSIVE, "Aggressive"),
    (MD_ASSIST, "Assist"),
    (MD_CASTSENSORIDLE, "CastSensorIdle"),
    (MD_NORANDOMWALK, "NoRandomWalk"),
    (MD_NOCAST, "NoCast"),
    (MD_CANATTACK, "CanAttack"),
    (MD_CASTSENSORCHASE, "CastSensorChase"),
    (MD_CHANGECHASE, "ChangeChase"),
    (MD_ANGRY, "Angry"),
    (MD_CHANGETARGETMELEE, "ChangeTargetMelee"),
    (MD_CHANGETARGETCHASE, "ChangeTargetChase"),
    (MD_TARGETWEAK, "TargetWeak"),
    (MD_RANDOMTARGET, "RandomTarget"),
    (MD_IGNOREMELEE, "IgnoreMelee"),
    (MD_IGNOREMAGIC, "IgnoreMagic"),
    (MD_IGNORERANGED, "IgnoreRanged"),
    (MD_MVP, "Mvp"),
    (MD_IGNOREMISC, "IgnoreMisc"),
    (MD_KNOCKBACKIMMUNE, "KnockBackImmune"),
    (MD_TELEPORTBLOCK, "TeleportBlock"),
    (MD_FIXEDITEMDROP, "FixedItemDrop"),
    (MD_DETECTOR, "Detector"),
    (MD_STATUSIMMUNE, "StatusImmune"),
    (MD_SKILLIMMUNE, "SkillImmune"),
]

_NAME_TO_BIT = {name: bit for bit, name in _BIT_NAMES}
# Accept MD_ style and common aliases from YAML
_NAME_TO_BIT.update(
    {
        "KnockbackImmune": MD_KNOCKBACKIMMUNE,
        "KnockBackImmune": MD_KNOCKBACKIMMUNE,
        "MVP": MD_MVP,
        "Mvp": MD_MVP,
    }
)

# e_aegis_monstertype — src/map/mob.hpp (Ai: N → MONSTER_TYPE_NN)
_AI_BITS: dict[str, int] = {
    "01": 0x81,
    "02": 0x83,
    "03": 0x1089,
    "04": 0x3885,
    "05": 0x2085,
    "06": 0,
    "07": 0x108B,
    "08": 0x7085,
    "09": 0x3095,
    "10": 0x84,
    "11": 0x84,
    "12": 0x2085,
    "13": 0x308D,
    "17": 0x91,
    "19": 0x3095,
    "20": 0x3295,
    "21": 0x3695,
    "24": 0xA1,
    "25": 0x1,
    "26": 0xB695,
    "27": 0x8084,
    "Abr_Passive": 0x21,
    "Abr_Offensive": 0xA5,
    "ABR_PASSIVE": 0x21,
    "ABR_OFFENSIVE": 0xA5,
}

# Class overlays — MobDatabase::loadingFinished
_CLASS_OVERLAY: dict[str, int] = {
    "Boss": MD_DETECTOR | MD_STATUSIMMUNE | MD_KNOCKBACKIMMUNE,
    "Guardian": MD_STATUSIMMUNE,
    "Battlefield": MD_STATUSIMMUNE | MD_SKILLIMMUNE,
    "Event": MD_FIXEDITEMDROP,
}


def normalize_ai_key(ai: Any) -> str | None:
    """Normalize YAML Ai (int/str) to MONSTER_TYPE key; None → default 06."""
    if ai is None or ai == "":
        return "06"
    if isinstance(ai, bool):
        return "06"
    if isinstance(ai, int):
        return f"{ai:02d}"
    s = str(ai).strip()
    if not s:
        return "06"
    if s.isdigit():
        return f"{int(s):02d}"
    return s


def bitmask_to_modes(mask: int) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for bit, name in _BIT_NAMES:
        if mask & bit:
            out[name] = True
    return out


def compute_modes_effective(
    *,
    ai: Any,
    modes: dict[str, Any] | None,
    mob_class: str | None,
) -> dict[str, bool]:
    """Return sparse {ModeName: true} matching runtime status.mode after load."""
    ai_key = normalize_ai_key(ai)
    mask = _AI_BITS.get(ai_key, 0) if ai_key else 0
    # Unknown AI → rAthena defaults to MONSTER_TYPE_06 (0)
    if ai_key not in _AI_BITS:
        mask = 0

    for name, active in (modes or {}).items():
        if name.startswith("_"):
            continue
        if not active:
            # YAML false clears the bit
            bit = _NAME_TO_BIT.get(str(name))
            if bit is not None:
                mask &= ~bit
            continue
        bit = _NAME_TO_BIT.get(str(name))
        if bit is not None:
            mask |= bit

    overlay = _CLASS_OVERLAY.get(str(mob_class or "Normal"), 0)
    mask |= overlay

    return bitmask_to_modes(mask)
