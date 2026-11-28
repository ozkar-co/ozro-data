# OzRo Master World Dataset — Reference Sheet

Single integration reference for consumers (web, CLI, market tools).  
**Authoritative store:** MySQL tables `ozro_*` (prefix from `config/database.yml`).  
**Intermediate:** `reports/*.jsonl`. Do not re-parse rAthena sources in consumers.

| | |
|---|---|
| Spec / historia | `rathena/docs/ozro-market/historia/brief-02/master_dataset.md` |
| Schema DDL | `database/schema/001_master.sql` |
| E1 → E5 delta | `database/SCHEMA_DELTA.md` |
| **Source → JSONL coverage** | [`database/EXTRACT_COVERAGE.md`](database/EXTRACT_COVERAGE.md) — what was / was not extracted |
| Column map (machine) | `database/table_specs.json` |
| Variable craft formulas | `rathena/.../brief-02/recipes_variable_formulas.md` |
| Regenerate | `./rebuild.sh` or `pipeline.py resolve` → `extract …` → `schema [--reset]` → `sync` |

Last verified sync fingerprint / counts: see `reports/sync_summary.json` and `ozro_dataset_metadata`.

**Coverage rule:** SQL only contains what extractors wrote to JSONL. A missing YAML field is an extract gap. Client item **descriptions** are intentionally out (translations). Equip constraints (`classes`, `gender`, `gradable`, `delay`, `no_use`, `stack`) are in `ozro_items`. Mob behavior for UI: prefer `modes_effective`, not sparse YAML `modes`.

---

## 1. How to use this DB

1. Read **only** `ozro_*`.
2. Prefer `*_effective` fields (HP, EXP, buy/sell, drop/box chances, **`modes_effective`**) — already resolved for OzRo rates / runtime behavior.
3. Respect status flags (`success_status`, `hp_status`, `rate_status`, …). `NULL` chance/HP + status ≠ “0%” / “0 HP”.
4. `level_penalty` is **not** baked into drop/EXP rows. Apply at query time if the UI knows player vs mob level.
5. Full replace on sync: empty window is OK; no incremental merge API.

```bash
./rebuild.sh                        # full discover → extract → schema --reset → sync
# or after extracts only:
python pipeline.py schema --reset   # first time / contract change
python pipeline.py sync             # after extracts
```

---

## 2. Units and conventions

| Concept | Convention |
|---|---|
| Drop chance (mob_db) | `rate_unit=per_10000` → 10000 = 100% |
| Map bonus drop | `rate_unit=per_100000`, `is_map_bonus=1` |
| Recipe / box / enchant chance | see `*_unit` / `chance_unit` on the row |
| IDs | Stable hashes (`CHAR(40)` / `VARCHAR(128)`) or natural ids (`item_id`, `mob_id`, `quest_id`, `map_id`) |
| Booleans | `TINYINT(1)` |
| JSON blobs | lists/dicts from extract (`modes`, `modes_effective`, `flags`, `connection_ids`, …) |
| Duplicate shop lines | `list_index` in PK (`npc_shop_items`, `acquisition_outputs`) |

**Join keys (most used):**

| From | To | On |
|---|---|---|
| Almost everything | `ozro_items` | `item_id` |
| Spawns / drops / skills | `ozro_mobs` | `mob_id` |
| Spawns / NPCs / shops | `ozro_maps` | `map_id` |
| Shop items | `ozro_npc_shops` | `shop_id` |
| Recipe mats | `ozro_recipes` | `recipe_id` |
| Box rewards | `ozro_boxes` | `box_id` |
| Provenance | any row | `provenance_id` → `ozro_source_provenance` |

Logical FKs are **not** enforced in MySQL (full-replace sync). Integrity is extract-time + count checks.

---

## 3. Catalog by domain

Row counts are approximate from the first E5 sync; re-check `sync_summary.json` after regenerate.

### 3.1 Meta

| Table | PK | Rows | Role |
|---|---|---|---|
| `ozro_dataset_metadata` | `dataset_version` | 1 | Version, fingerprint, notes JSON |
| `ozro_source_provenance` | `provenance_id` | ~301k | Derived at sync from extract provenance |
| `ozro_dataset_rates` | `key` | 46 | Effective battle-conf rates/flags (§24.4) |
| `ozro_dataset_level_penalty` | `penalty_id` | 30 | Flat `type` / `difference` / `rate` (Exp/Drop) |

### 3.2 World / travel

| Table | PK | Rows | Role |
|---|---|---|---|
| `ozro_maps` | `map_id` | 985 | Catalog + flags (town/dungeon/instance/…) |
| `ozro_map_connections` | `connection_id` | 4050 | Warps, kafra, airship, boat, OzRo TP |
| `ozro_map_distances` | `(from,to)` | 171614 | Dijkstra friction all-pairs |
| `ozro_map_routes` | `(from,to)` | 171614 | `connection_ids` JSON path |

### 3.3 NPCs

| Table | PK | Rows | Role |
|---|---|---|---|
| `ozro_npcs` | `npc_id` | 20674 | Placed / script NPCs |
| `ozro_npc_functions` | `(npc_id, function_name)` | ~22k | Derived from `npcs.functions[]` |
| `ozro_npc_quests` | `link_id` | 4710 | NPC ↔ quest |
| `ozro_npc_script_evidence` | `evidence_id` | 7478 | Script scan evidence |
| `ozro_npc_script_rewards` | `npc_script_reward_id` | 2213 | Literal getitem/getitem2 → `acquisition_type=npc_delivery` |

### 3.4 Mobs / combat

| Table | PK | Rows | Role |
|---|---|---|---|
| `ozro_mobs` | `mob_id` | 2675 | Stats + `hp_*` / EXP effective + behavior modes |
| `ozro_spawns` | `spawn_id` | 9375 | Natural / script / instance; `spawn_route`, `npc_id` |
| `ozro_mob_skills` | `mob_skill_id` | 14449 | mob_skill_db |
| `ozro_skill_summons` | `summon_id` | 1177 | Summon/slave links (`summon_kind=mob_slave` today; player skill summons deferred) |
| `ozro_skills` | `skill_id` | ~1635 | Player `skill_db.yml`: `aegis_prefix`, `skill_type`, `is_quest`, `is_platinum` |
| `ozro_skill_item_costs` | `skill_item_cost_id` | ~ItemCost rows | Cast consume items (`Requires.ItemCost`) |
| `ozro_skill_teachers` | `skill_teacher_id` | varies | Platinum grants: `skill_perm` / `f_get_platinum` (+ optional `npc_id`) |

**`hp_status`:** `from_mob_db` (normal) · `not_extractable` (ABR/bionic caster formula — HP NULL).

**`spawn_route` (sample):** `npc_script` · `instance_script` · NULL (natural headers).

**Behavior modes (`ozro_mobs`):**

| Column | Layer | Meaning |
|---|---|---|
| `modes` | original | Sparse YAML `Modes` only (e.g. `Mvp`, `Detector`, `Ignore*`). Most mobs are `NULL`/`{}`. **Not** full in-game behavior. |
| `modes_effective` | normalized | Runtime `status.mode` after load: **Ai bitmask ∨ YAML Modes ∨ Class overlays** (same rules as `mob.cpp` parse + `loadingFinished`). Sparse `{ "Aggressive": true, … }`. |
| `stats.ai` | original | YAML `Ai` (`"02"`, `"10"`, `Abr_Offensive`, …) kept inside `stats` JSON. |
| `mob_class` | original | YAML `Class` (`Normal` / `Boss` / `Guardian` / `Battlefield` / `Event`). Boss overlays add Detector + StatusImmune + KnockBackImmune even when absent from `modes`. |

Consumer rule: encyclopedia / filters / tags → **`modes_effective`**. Keep `modes` only when you need “what the YAML declared”.

Observed effective keys (counts vary by sync): `CanMove`, `CanAttack`, `Aggressive`, `Looter`, `Assist`, `Angry`, `CastSensorIdle`, `CastSensorChase`, `ChangeChase`, `ChangeTargetMelee`, `ChangeTargetChase`, `Detector`, `Mvp`, `StatusImmune`, `KnockBackImmune`, `FixedItemDrop`, `TeleportBlock`, `IgnoreMelee` / `IgnoreMagic` / `IgnoreRanged` / `IgnoreMisc`, `SkillImmune`, `NoRandomWalk`, `RandomTarget`, `TargetWeak`, …

Logic lives in `resolvers/mob_modes.py` (extract → `mobs.jsonl` → SQL). Assumes `monster_active_enable: yes` (OzRo default; Aggressive is not stripped).

### 3.5 Items

| Table | PK | Rows | Role |
|---|---|---|---|
| `ozro_items` | `item_id` | 22622 | Catalog + buy/sell effective + equip constraints |
| `ozro_item_scripts` | `item_script_id` | 15731 | Script / EquipScript / UnEquipScript |
| `ozro_item_restrictions` | `(item_id, restriction_key)` | 40145 | Trade.* / noequip / flag.NoConsume |
| `ozro_item_dependencies` | `item_dependency_id` | 37129 | Consume/produce/socket/combo/box edges |
| Combo | `item_combo_groups` / `_sets` / `_members` | 3k / 4k / 11k | item_combos.yml |

**`ozro_items` JSON / constraint columns (consumers):**

| Column | Source YAML | Notes |
|---|---|---|
| `jobs` | `Jobs` | e.g. `{"Knight": true, …}` |
| `classes` | `Classes` | e.g. `{"Upper": true, "All_Third": true, "Fourth": true}` (~1943 rows) |
| `locations` | `Locations` | e.g. `{"Right_Hand": true}` |
| `flags` | `Flags` | |
| `gender` | `Gender` | `Male` / `Female` / null |
| `gradable` | `Gradable` | bool / null |
| `delay` | `Delay` | `{Duration, Status}` JSON |
| `no_use` | `NoUse` | e.g. `{Sitting: true}` |
| `stack` | `Stack` | JSON / null |
| `buy_effective` / `sell_effective` | Buy/Sell + resolver | Already rate-resolved |

Not in SQL (by design): client lore/description text.

### 3.6 Acquisition (how to get an item)

| Table | PK | Rows | Role |
|---|---|---|---|
| `ozro_mob_drops` | `drop_id` | 13802 | Mob + map-bonus drops; `chance_effective` |
| `ozro_drop_random_option_links` | … | 336 | Drop → random option group |
| `ozro_npc_shops` / `_items` | shop / `(shop_id,list_index)` | 342 / 2911 | Declared shops |
| `ozro_npc_shop_links` / `_link_shops` | … | 93 / 77 | callshop wiring; `is_runtime` |
| `ozro_barters` / `_items` / `_required_items` | … | 62 / 1k / 1k | barters.yml |
| `ozro_boxes` / `_rewards` / `_item_links` | … | 3k / 33k / 2k | item_group + openers |
| `ozro_recipes` / `_materials` | … | 293 / 1003 | produce_db |
| `ozro_quests` / `_targets` / `_drops` | … | 5k / 1k / 69 | quest_db |
| `ozro_quest_groups` / `_members` / `_edges` / `_npcs` | `group_id` / … | varies | High-precision clusters: `script_transition`, `same_title_contig`; NPC `same_id` / `same_file` |
| `ozro_acquisition_outputs` | `(acquisition_output_id, list_index)` | 53684 | **Union** of sources for “where does item X come from?” |

**`acquisition_outputs.source_type` (observed):**  
`box_reward` · `mob_drop` · `npc_shop` · `npc_reward` · `npc_barter` · `map_drop` · `crafting` · `socketing` · `enchanting` · `quest_drop`

**`box_reward` rows also carry** `algorithm` / `chance_status` (from `box_rewards`; NULL on other source types). Prefer this table for “all sources of item X”; use domain tables when you need full drop/shop/recipe detail.

### 3.7 Instances / enchant / random options / NPC enchant evidence

| Group | Tables | Notes |
|---|---|---|
| Instances | `instances`, `instance_maps`, `instance_npc_links` | Create-NPC binds on links |
| Enchant DB | `enchantments`, `enchant_targets`, `enchant_options`, `enchant_perfect`, `enchant_upgrades`, `enchant_materials` | From item_enchant.yml |
| Random opts | `random_options`, `random_option_groups`, `_slots`, `_random` | |
| NPC enchant scripts | `npc_enchant_sources`, `npc_enchant_items`, `npc_item_transforms` | Script evidence, not full UI flow |

---

## 4. Flags consumers must honor

| Flag | Values / meaning | Consumer action |
|---|---|---|
| `recipes.success_status` | `fixed_src` · `fixed_db` · `variable` | If `variable`: `success_chance` is NULL — use formula doc / calculator, do not show 0% |
| `mobs.hp_status` | `from_mob_db` · `not_extractable` | If not_extractable: do not show HP as 0 |
| `mobs.modes` vs `modes_effective` | JSON sparse bool maps | UI behavior tags → `modes_effective` only; `modes` is YAML original |
| `npc_shops.inventory_declared` | bool | Inventory = declared header only |
| `npc_shops.runtime_mutated` | bool | Warn “may change in-game” |
| `npc_shop_links.is_runtime` | bool | Dynamic callshop |
| `mob_drops.is_map_bonus` | bool | Separate from normal drops; different `rate_unit` |
| `npc_script_rewards.acquisition_type` | `npc_delivery` | Not a box/recipe |

---

## 5. Integration recipes (query patterns)

**All sources for an item**
```sql
SELECT source_type, npc_id, mob_id, map_id, probability, probability_unit, price, quantity_min
FROM ozro_acquisition_outputs
WHERE item_id = ?
ORDER BY source_type;
```

**Shop in Prontera but never a mob drop**
```sql
SELECT DISTINCT i.item_id, i.aegis_name, sh.map_id, sh.shop_name, si.price_effective
FROM ozro_npc_shop_items si
JOIN ozro_npc_shops sh ON sh.shop_id = si.shop_id
JOIN ozro_items i ON i.item_id = si.item_id
LEFT JOIN ozro_mob_drops d ON d.item_id = si.item_id AND d.is_map_bonus = 0
WHERE sh.map_id IN ('prontera', 'prt_in')
  AND d.drop_id IS NULL;
```
(Note: “not a mob drop” ≠ “unobtainable” — check boxes / NPC rewards via `acquisition_outputs`.)

**Mob drops with effective chance**
```sql
SELECT m.aegis_name, i.aegis_name, d.chance_base, d.chance_effective, d.rate_unit
FROM ozro_mob_drops d
JOIN ozro_mobs m ON m.mob_id = d.mob_id
JOIN ozro_items i ON i.item_id = d.item_id
WHERE m.aegis_name = 'PORING' AND d.is_map_bonus = 0;
```

**Mob behavior (effective modes)**
```sql
SELECT mob_id, aegis_name, modes, modes_effective,
       JSON_EXTRACT(stats, '$.ai') AS ai, mob_class
FROM ozro_mobs
WHERE aegis_name IN ('PORING', 'AMON_RA');

-- Filter: aggressive field mobs
SELECT mob_id, aegis_name
FROM ozro_mobs
WHERE JSON_EXTRACT(modes_effective, '$.Aggressive') = true;
```

**Travel friction**
```sql
SELECT friction, hop_count FROM ozro_map_distances
WHERE from_map_id = 'prontera' AND to_map_id = 'geffen';
```

**Craft materials**
```sql
SELECT r.result_aegis_name, r.success_status, r.success_chance,
       rm.aegis_name, rm.amount, rm.role
FROM ozro_recipes r
JOIN ozro_recipe_materials rm ON rm.recipe_id = r.recipe_id
WHERE r.produce_id = ?;
```

---

## 6. What is intentionally out of scope

- Client item **descriptions** / lore (translations will replace them).
- Client-only reports (`client_*`) beyond asset presence flags already on items/mobs.
- Live shop mutation state (only flags).
- Player-level penalty applied into each drop row.
- Invented % for `variable` recipes or ABR/bionic HP.
- Economic / market pricing (this dataset is world facts only).

See `EXTRACT_COVERAGE.md` before assuming a YAML field is “missing from SQL”.

---

## 7. Ops checklist (deploy to server)

1. MySQL reachable; user can DDL/DML on target DB.
2. Copy/update `config/database.yml` (host/user/pass/database; keep `table_prefix: ozro_`).
3. On app host: venv + `pip install -r requirements.txt`.
4. Full rebuild: `./rebuild.sh` (discover → resolve → all extracts → `schema --reset` → `sync`).  
   Or ensure `reports/` present and run `schema --reset` + `sync` only.
5. `schema --reset` only touches `ozro_*` (not rAthena game tables).
6. Confirm `SELECT * FROM ozro_dataset_metadata`, one drop, one shop, and one mob `modes_effective` (e.g. `AMON_RA`).
7. Point consumers at this DB; never at raw `db/re/*.yml` for world answers.
