# Schema contract delta — E1 plan → Etapa 5

Compares brief §25.1 / [`schema/001_master.sql`](schema/001_master.sql) (Etapa 1 stub) with the JSONL produced after E3/E4/Pre-E5.

**Sync policy:** full-replace of all `ozro_*` tables from `reports/*.jsonl` (`pipeline.py sync`).

**Special cases (not invented %/HP):**

| Domain | Flag / field | Meaning |
|---|---|---|
| Recipes | `success_status=variable`, `success_chance` NULL | Player/RNG formula; see `rathena/.../recipes_variable_formulas.md` |
| Mobs (ABR/bionic) | `hp_status=not_extractable`, HP NULL | Caster formula in `status.cpp` |
| Shops | `runtime_mutated`, `inventory_declared` | Declared inventory only; runtime mutations flagged |
| Spawns | `npc_id`, `spawn_route=npc_script` | Scripted spawn path (Pre-E5) |
| NPC deliveries | `ozro_npc_script_rewards.acquisition_type=npc_delivery` | Literal `getitem` / `getitem2` |
| Shop / acquisition dups | `list_index` on `ozro_npc_shop_items` + `ozro_acquisition_outputs` | Headers can list the same `item_id` multiple times; sync assigns `list_index` per shop / per `acquisition_output_id` so rows are preserved |

---

## Out of SQL (stay as reports / discovery only)

| JSONL / source | Reason |
|---|---|
| `client_*` | Client asset inventory / gaps — not Master World rows |
| Discovery YAML / manifests | Extractor inputs, not dataset |

---

## Kept (E1 table name still exists; core role unchanged)

`ozro_dataset_metadata`, `ozro_source_provenance`, `ozro_maps`, `ozro_map_connections`, `ozro_map_distances`, `ozro_map_routes`, `ozro_npcs`, `ozro_npc_functions`, `ozro_npc_quests`, `ozro_mobs`, `ozro_spawns`, `ozro_mob_skills`, `ozro_skill_summons`, `ozro_items`, `ozro_item_scripts`, `ozro_item_restrictions`, `ozro_mob_drops`, `ozro_npc_shops`, `ozro_npc_shop_items`, `ozro_npc_shop_links`, `ozro_npc_shop_link_shops`, `ozro_npc_script_evidence`, `ozro_quests`, `ozro_quest_targets`, `ozro_quest_drops`, `ozro_instances`, `ozro_instance_maps`, `ozro_boxes`, `ozro_box_rewards`, `ozro_box_item_links`, `ozro_recipes`, `ozro_recipe_materials`, `ozro_enchantments`, `ozro_item_relationships` *(see note)*

**Dropped / unused from E1 stubs (no matching extract):**

- `ozro_skills` — no standalone `skills.jsonl` (skill ids live on mob_skills / summons / recipes)
- `ozro_item_properties` — no extract; item scalars live on `ozro_items`
- `ozro_item_enchantments` (single JSON blob) — replaced by normalized enchant_* tables
- `ozro_enchantment_materials` E1 stub — replaced by `ozro_enchant_materials`
- `ozro_item_combos` E1 stub — replaced by combo groups/sets/members
- `ozro_acquisition_sources` + thin `ozro_source_outputs` — replaced by `ozro_acquisition_outputs`

**Note on relationships:** E1 `ozro_item_relationships` is superseded by `ozro_item_dependencies` (+ combo tables). No separate `item_relationships.jsonl`.

---

## Expanded (E1 table + columns added for E3/E4/Pre-E5)

| Table | Notable new / real columns vs E1 stub |
|---|---|
| `ozro_mobs` | `hp_status`, `hp_note`, `classification_layer`, `client_gap_reason`, `source` JSON |
| `ozro_spawns` | `npc_id`, `spawn_route`, `spawn_kind`, `boss_flag`, `x2`/`y2`, `classification_layer`, `source` JSON |
| `ozro_mob_drops` | `item_aegis_name`, `item_ratio_source`, `random_option_group` |
| `ozro_npc_shops` | `inventory_declared`, `runtime_mutated`, `runtime_ops` JSON, `map_id`, `x`/`y`, `sprite` |
| `ozro_npc_shop_items` | `price_effective`, `price_source`, `npc_id` |
| `ozro_npc_shop_links` | `is_runtime`, `item_count` |
| `ozro_recipes` | Full produce fields: `produce_id`, `recipe_family`, `item_lv`, skill require, `success_*`, `zeny_*`, `fail_*` (no longer a JSON blob) |
| `ozro_recipe_materials` | `recipe_material_id`, `role`, `index`, `produce_id`, `aegis_name` |
| `ozro_boxes` / `ozro_box_rewards` | Effective chance fields, refine/duration, algorithms |
| `ozro_items` | Buy/sell effective + sources, classification, equip slot families, assets flags |
| `ozro_maps` | `classification_layer`, `categories`/`client`/`source` JSON |
| `ozro_map_connections` | `classification_layer`, friction, conditions JSON |
| `ozro_instance_maps` | `in_maps_catalog`, `spawn_rows` |
| `ozro_quests` | `time_limit` JSON (was only seconds) |

---

## Added (not in E1 §25.1 list, or only named abstractly)

| Table | Source JSONL | Why |
|---|---|---|
| `ozro_dataset_rates` | `dataset_rates.jsonl` | §24.4 rates catalog (E4) |
| `ozro_dataset_level_penalty` | `level_penalty.jsonl` | Pre-E5 flat Type/Difference/Rate |
| `ozro_npc_script_rewards` | `npc_script_rewards.jsonl` | Pre-E5 NPC→item deliveries |
| `ozro_instance_npc_links` | `instance_npc_links.jsonl` | Create-NPC binds (replaces thin `ozro_instance_npcs`) |
| `ozro_barters` | `barters.jsonl` | Barter shops |
| `ozro_barter_items` | `barter_items.jsonl` | |
| `ozro_barter_required_items` | `barter_required_items.jsonl` | |
| `ozro_enchant_targets` | `enchant_targets.jsonl` | Normalized item_enchant.yml |
| `ozro_enchant_options` | `enchant_options.jsonl` | |
| `ozro_enchant_perfect` | `enchant_perfect.jsonl` | |
| `ozro_enchant_upgrades` | `enchant_upgrades.jsonl` | |
| `ozro_enchant_materials` | `enchant_materials.jsonl` | |
| `ozro_item_combo_groups` | `item_combo_groups.jsonl` | Combos normalized |
| `ozro_item_combo_sets` | `item_combo_sets.jsonl` | |
| `ozro_item_combo_members` | `item_combo_members.jsonl` | |
| `ozro_item_dependencies` | `item_dependencies.jsonl` | §22.2 graph |
| `ozro_acquisition_outputs` | `acquisition_outputs.jsonl` | Unified acquisition union |
| `ozro_random_options` | `random_options.jsonl` | |
| `ozro_random_option_groups` | `random_option_groups.jsonl` | |
| `ozro_random_option_group_slots` | `random_option_group_slots.jsonl` | |
| `ozro_random_option_group_random` | `random_option_group_random.jsonl` | |
| `ozro_drop_random_option_links` | `drop_random_option_links.jsonl` | |
| `ozro_npc_enchant_sources` | `npc_enchant_sources.jsonl` | Script enchant evidence |
| `ozro_npc_enchant_items` | `npc_enchant_items.jsonl` | |
| `ozro_npc_item_transforms` | `npc_item_transforms.jsonl` | |

`ozro_npc_functions` is **derived at sync** from `npcs.jsonl` → `functions[]` (no separate JSONL).  
`ozro_npc_shop_link_shops` is **derived** from `npc_shop_links.jsonl` → `shop_ids[]`.  
`ozro_source_provenance` is **derived** from rows that carry `provenance_id` (+ `source_file` when present).

---

## Volume (approx. rows at first E5 sync)

| Domain | Rows |
|---|---|
| map_distances / map_routes | ~171k each |
| acquisition_outputs | ~54k |
| item_restrictions | ~40k |
| item_dependencies | ~37k |
| box_rewards | ~33k |
| items | ~23k |
| npcs | ~21k |
| Rest | see `reports/*_summary.json` / sync_summary |
