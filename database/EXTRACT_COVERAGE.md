# Extract coverage audit (source → JSONL → SQL)

**Rule:** SQL only persists what extractors write to `reports/*.jsonl`.  
A missing YAML field is an **extract gap**, not a sync bug.

Re-run mindset: for each domain, compare source keys vs JSONL keys (allowlist). Descriptions/client copy can stay out by product choice.

---

## Items (`item_db_*.yml` → `items.jsonl` / `ozro_items`)

| YAML field | Status | Where |
|---|---|---|
| Id, AegisName, Name, Type, SubType, Buy/Sell, Weight, Attack, MagicAttack, Defense, Range, Slots, Weapon/ArmorLevel, EquipLevel*, Refineable, View, Flags, Jobs, Locations | OK | `ozro_items` |
| Script / EquipScript / UnEquipScript | OK | `ozro_item_scripts` |
| Trade.* | OK | `ozro_item_restrictions` |
| **Classes** | **fixed** (was omit) | `ozro_items.classes` JSON |
| **Gender** | **fixed** | `ozro_items.gender` |
| **Gradable** | **fixed** | `ozro_items.gradable` |
| **Delay** | **fixed** | `ozro_items.delay` JSON |
| **NoUse** | **fixed** | `ozro_items.no_use` JSON |
| **Stack** | **fixed** | `ozro_items.stack` JSON |
| Client item descriptions | Out of scope (by design) | `itemInfo` / translations later |

---

## Mobs (`mob_db.yml` → `mobs.jsonl`)

| Area | Status |
|---|---|
| Core stats, HP/EXP effective, element/race/size, modes, drops→`ozro_mob_drops` | OK |
| GroupId / Title | OK — in `stats.group_id` / `stats.title` |

---

## Other domains (spot-check)

| Domain | Notes |
|---|---|
| Quests / instances | Top-level YAML keys covered; nested targets/drops in child tables |
| Enchantments | `TargetItems` / `Slots` live in `enchant_targets` / `enchant_options` (not omitted) |
| Boxes / barters / recipes / random options | Structured into child JSONL tables |
| NPC script rewards | Literals only by design (variables omitted — documented) |

---

## How this happened

Extractors use **explicit field maps** (safe, typed). Anything not listed never reaches JSONL/SQL.  
There was no automated “YAML key coverage” gate before E5 — that is the process gap.

## Follow-up

1. Keep this file updated when adding source fields.
2. Prefer a CI/check script: `yaml_keys - jsonl_mapped = miss` for items/mobs.
3. After item fix: `pipeline.py extract items` → `schema --reset` → `sync`.
