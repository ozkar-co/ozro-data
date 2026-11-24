-- OzRo Master World Dataset — Etapa 5 contract (aligned to reports JSONL).
-- See database/SCHEMA_DELTA.md for E1 → E5 delta.
-- Prefix configurable via config/database.yml (default ozro_).

CREATE TABLE IF NOT EXISTS ozro_dataset_rates (
  `group` VARCHAR(255) NULL,
  `key` VARCHAR(255) NOT NULL,
  unit VARCHAR(128) NULL,
  value INT NULL,
  PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_dataset_level_penalty (
  difference INT NULL,
  penalty_id VARCHAR(128) NOT NULL,
  provenance_id VARCHAR(128) NULL,
  rate INT NULL,
  rate_unit VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  type VARCHAR(255) NULL,
  PRIMARY KEY (penalty_id),
  INDEX idx_lp_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_maps (
  access_conditions JSON NULL,
  categories JSON NULL,
  category VARCHAR(255) NULL,
  classification_layer VARCHAR(255) NULL,
  client JSON NULL,
  client_resource_present TINYINT(1) NULL,
  display_name VARCHAR(255) NULL,
  display_name_source VARCHAR(255) NULL,
  height INT NULL,
  is_accessible TINYINT(1) NULL,
  is_dungeon TINYINT(1) NULL,
  is_guild_map TINYINT(1) NULL,
  is_instance TINYINT(1) NULL,
  is_interior TINYINT(1) NULL,
  is_quest_map TINYINT(1) NULL,
  is_town TINYINT(1) NULL,
  map_id VARCHAR(64) NOT NULL,
  provenance_id VARCHAR(128) NULL,
  source JSON NULL,
  width INT NULL,
  PRIMARY KEY (map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_map_connections (
  classification_layer VARCHAR(255) NULL,
  conditions JSON NULL,
  connection_id VARCHAR(128) NOT NULL,
  connection_type VARCHAR(255) NULL,
  destination_map_id VARCHAR(128) NULL,
  destination_x INT NULL,
  destination_y INT NULL,
  friction_weight DOUBLE NULL,
  is_directional TINYINT(1) NULL,
  label VARCHAR(255) NULL,
  npc_id VARCHAR(128) NULL,
  provenance_id VARCHAR(128) NULL,
  required_items JSON NULL,
  route_id VARCHAR(128) NULL,
  source JSON NULL,
  source_map_id VARCHAR(128) NULL,
  source_x INT NULL,
  source_y INT NULL,
  trigger_xs INT NULL,
  trigger_ys INT NULL,
  warp_name VARCHAR(255) NULL,
  warp_variant VARCHAR(255) NULL,
  zeny_cost INT NULL,
  PRIMARY KEY (connection_id),
  INDEX idx_conn_src (source_map_id),
  INDEX idx_conn_dst (destination_map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_map_distances (
  friction DOUBLE NULL,
  from_map_id VARCHAR(64) NOT NULL,
  hop_count INT NULL,
  to_map_id VARCHAR(64) NOT NULL,
  PRIMARY KEY (from_map_id, to_map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_map_routes (
  connection_ids JSON NULL,
  from_map_id VARCHAR(64) NOT NULL,
  to_map_id VARCHAR(64) NOT NULL,
  PRIMARY KEY (from_map_id, to_map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npcs (
  classification_layer VARCHAR(255) NULL,
  client JSON NULL,
  display_name VARCHAR(255) NULL,
  duplicate_of VARCHAR(255) NULL,
  facing INT NULL,
  has_sprite TINYINT(1) NULL,
  map_id VARCHAR(64) NULL,
  name VARCHAR(255) NULL,
  npc_id VARCHAR(128) NOT NULL,
  npc_type VARCHAR(255) NULL,
  provenance_id VARCHAR(128) NULL,
  script_analysis JSON NULL,
  script_line INT NULL,
  script_path VARCHAR(512) NULL,
  source JSON NULL,
  sprite_id VARCHAR(128) NULL,
  sprite_stem VARCHAR(255) NULL,
  x INT NULL,
  y INT NULL,
  PRIMARY KEY (npc_id),
  INDEX idx_npc_map (map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_functions (
  npc_id VARCHAR(128) NOT NULL,
  function_name VARCHAR(64) NOT NULL,
  PRIMARY KEY (npc_id, function_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_quests (
  in_quest_db TINYINT(1) NULL,
  link_id VARCHAR(128) NOT NULL,
  npc_id VARCHAR(128) NULL,
  provenance_id VARCHAR(128) NULL,
  quest_id INT NULL,
  role VARCHAR(255) NULL,
  script_line INT NULL,
  script_path VARCHAR(512) NULL,
  PRIMARY KEY (link_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_script_evidence (
  evidence JSON NULL,
  evidence_id VARCHAR(128) NOT NULL,
  functions JSON NULL,
  mob_commands JSON NULL,
  npc_id VARCHAR(128) NULL,
  provenance_id VARCHAR(128) NULL,
  quest_ids JSON NULL,
  script_line INT NULL,
  script_path VARCHAR(512) NULL,
  variable_count INT NULL,
  variables JSON NULL,
  PRIMARY KEY (evidence_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_script_rewards (
  acquisition_type VARCHAR(255) NULL,
  attribute INT NULL,
  cards JSON NULL,
  command VARCHAR(255) NULL,
  delivery_kind VARCHAR(255) NULL,
  identify INT NULL,
  is_modified TINYINT(1) NULL,
  item_id INT NULL,
  map_id VARCHAR(64) NULL,
  npc_id VARCHAR(128) NULL,
  npc_script_reward_id VARCHAR(128) NOT NULL,
  provenance_id VARCHAR(128) NULL,
  quantity INT NULL,
  refine INT NULL,
  script_line INT NULL,
  script_path VARCHAR(512) NULL,
  PRIMARY KEY (npc_script_reward_id),
  INDEX idx_nsr_npc (npc_id),
  INDEX idx_nsr_item (item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_mobs (
  aegis_name VARCHAR(128) NULL,
  attack INT NULL,
  attack2 INT NULL,
  base_exp_base BIGINT NULL,
  base_exp_effective BIGINT NULL,
  classification_layer VARCHAR(255) NULL,
  client_gap_reason VARCHAR(255) NULL,
  defense INT NULL,
  element VARCHAR(255) NULL,
  element_level INT NULL,
  has_sprite TINYINT(1) NULL,
  hp_base BIGINT NULL,
  hp_effective BIGINT NULL,
  hp_multiplier INT NULL,
  hp_note MEDIUMTEXT NULL,
  hp_status VARCHAR(255) NULL,
  is_mvp TINYINT(1) NULL,
  japanese_name VARCHAR(255) NULL,
  job_exp_base BIGINT NULL,
  job_exp_effective BIGINT NULL,
  level INT NULL,
  magic_defense INT NULL,
  mob_class VARCHAR(255) NULL,
  mob_id INT NOT NULL,
  mob_role VARCHAR(255) NULL,
  modes JSON NULL,
  modes_effective JSON NULL,
  mvp_exp_base BIGINT NULL,
  mvp_exp_effective BIGINT NULL,
  name VARCHAR(255) NULL,
  provenance_id VARCHAR(128) NULL,
  race VARCHAR(255) NULL,
  size VARCHAR(255) NULL,
  source JSON NULL,
  sp INT NULL,
  sprite_name VARCHAR(255) NULL,
  stats JSON NULL,
  PRIMARY KEY (mob_id),
  INDEX idx_mob_role (mob_role),
  UNIQUE KEY uq_mob_aegis (aegis_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_spawns (
  amount INT NULL,
  boss_flag INT NULL,
  classification_layer VARCHAR(255) NULL,
  display_name VARCHAR(255) NULL,
  event_id VARCHAR(128) NULL,
  map_id VARCHAR(64) NULL,
  mob_id INT NULL,
  npc_id VARCHAR(128) NULL,
  parent_mob_id INT NULL,
  provenance_id VARCHAR(128) NULL,
  respawn_max INT NULL,
  respawn_min INT NULL,
  respawn_unit VARCHAR(255) NULL,
  script_line INT NULL,
  script_path VARCHAR(512) NULL,
  skill_id INT NULL,
  source JSON NULL,
  spawn_condition JSON NULL,
  spawn_id VARCHAR(128) NOT NULL,
  spawn_kind VARCHAR(255) NULL,
  spawn_route VARCHAR(255) NULL,
  spawn_type VARCHAR(255) NULL,
  x INT NULL,
  x2 INT NULL,
  x_area INT NULL,
  y INT NULL,
  y2 INT NULL,
  y_area INT NULL,
  PRIMARY KEY (spawn_id),
  INDEX idx_spawn_mob (mob_id),
  INDEX idx_spawn_map (map_id),
  INDEX idx_spawn_type (spawn_type),
  INDEX idx_spawn_npc (npc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_mob_skills (
  condition_type VARCHAR(255) NULL,
  condition_value VARCHAR(255) NULL,
  mob_id INT NULL,
  mob_skill_id VARCHAR(128) NOT NULL,
  provenance_id VARCHAR(128) NULL,
  rate INT NULL,
  skill_id INT NULL,
  skill_lv INT NULL,
  skill_name VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  source_line INT NULL,
  state VARCHAR(255) NULL,
  val1 INT NULL,
  vals JSON NULL,
  PRIMARY KEY (mob_skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_skill_summons (
  amount INT NULL,
  conditions JSON NULL,
  parent_mob_id INT NULL,
  provenance_id VARCHAR(128) NULL,
  skill_id INT NULL,
  skill_name VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  source_line INT NULL,
  summon_id VARCHAR(128) NOT NULL,
  summon_kind VARCHAR(255) NULL,
  summoned_mob_id INT NULL,
  PRIMARY KEY (summon_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_skills (
  skill_id INT NOT NULL,
  aegis_name VARCHAR(128) NULL,
  aegis_prefix VARCHAR(32) NULL,
  description VARCHAR(255) NULL,
  max_level INT NULL,
  skill_type VARCHAR(64) NULL,
  target_type VARCHAR(64) NULL,
  is_quest TINYINT(1) NULL,
  is_platinum TINYINT(1) NULL,
  flags JSON NULL,
  source_file VARCHAR(512) NULL,
  source_line INT NULL,
  provenance_id VARCHAR(128) NULL,
  PRIMARY KEY (skill_id),
  INDEX idx_skills_aegis (aegis_name),
  INDEX idx_skills_prefix (aegis_prefix),
  INDEX idx_skills_platinum (is_platinum)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_skill_item_costs (
  skill_item_cost_id VARCHAR(128) NOT NULL,
  skill_id INT NULL,
  skill_aegis_name VARCHAR(128) NULL,
  item_aegis_name VARCHAR(128) NULL,
  amount INT NULL,
  level INT NULL,
  provenance_id VARCHAR(128) NULL,
  PRIMARY KEY (skill_item_cost_id),
  INDEX idx_skill_item_costs_skill (skill_id),
  INDEX idx_skill_item_costs_item (item_aegis_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_skill_teachers (
  skill_teacher_id VARCHAR(128) NOT NULL,
  grant_kind VARCHAR(64) NULL,
  skill_id INT NULL,
  skill_aegis_name VARCHAR(128) NULL,
  npc_id VARCHAR(128) NULL,
  npc_display_name VARCHAR(255) NULL,
  map_id VARCHAR(128) NULL,
  x INT NULL,
  y INT NULL,
  script_path VARCHAR(512) NULL,
  script_line INT NULL,
  provenance_id VARCHAR(128) NULL,
  PRIMARY KEY (skill_teacher_id),
  INDEX idx_skill_teachers_skill (skill_id),
  INDEX idx_skill_teachers_npc (npc_id),
  INDEX idx_skill_teachers_kind (grant_kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_items (
  aegis_name VARCHAR(128) NULL,
  armor_level INT NULL,
  assets_complete TINYINT(1) NULL,
  attack INT NULL,
  buy_base INT NULL,
  buy_effective INT NULL,
  buy_source VARCHAR(255) NULL,
  card_insert_key VARCHAR(255) NULL,
  card_insert_slots JSON NULL,
  classification_layer VARCHAR(255) NULL,
  client_gap_reason VARCHAR(255) NULL,
  defense INT NULL,
  display_name VARCHAR(255) NULL,
  equip_level_max INT NULL,
  equip_level_min INT NULL,
  equip_slot_families JSON NULL,
  equip_slot_key VARCHAR(255) NULL,
  flags JSON NULL,
  has_item_icon TINYINT(1) NULL,
  has_script TINYINT(1) NULL,
  has_sprite TINYINT(1) NULL,
  is_costume TINYINT(1) NULL,
  item_category VARCHAR(255) NULL,
  item_id INT NOT NULL,
  item_subcategory VARCHAR(255) NULL,
  jobs JSON NULL,
  stack JSON NULL,
  no_use JSON NULL,
  delay JSON NULL,
  gender VARCHAR(32) NULL,
  gradable TINYINT(1) NULL,
  classes JSON NULL,
  locations JSON NULL,
  magic_attack INT NULL,
  name VARCHAR(255) NULL,
  provenance_id VARCHAR(128) NULL,
  range_atk INT NULL,
  refineable TINYINT(1) NULL,
  sell_base INT NULL,
  sell_effective INT NULL,
  sell_source VARCHAR(255) NULL,
  slots INT NULL,
  source JSON NULL,
  sprite_name VARCHAR(255) NULL,
  subtype VARCHAR(255) NULL,
  type VARCHAR(255) NULL,
  value_was_derived TINYINT(1) NULL,
  view_id INT NULL,
  weapon_level INT NULL,
  weight INT NULL,
  PRIMARY KEY (item_id),
  UNIQUE KEY uq_item_aegis (aegis_name),
  INDEX idx_item_type (type),
  INDEX idx_item_category (item_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_scripts (
  aegis_name VARCHAR(128) NULL,
  item_id INT NULL,
  item_script_id VARCHAR(128) NOT NULL,
  parse_status VARCHAR(255) NULL,
  parsed_effects JSON NULL,
  provenance_id VARCHAR(128) NULL,
  script_body MEDIUMTEXT NULL,
  script_hash VARCHAR(255) NULL,
  script_kind VARCHAR(255) NULL,
  source_file VARCHAR(512) NULL,
  `trigger` VARCHAR(255) NULL,
  PRIMARY KEY (item_script_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_restrictions (
  aegis_name VARCHAR(128) NULL,
  item_id INT NOT NULL,
  provenance_id VARCHAR(128) NULL,
  restriction_key VARCHAR(255) NOT NULL,
  restriction_value JSON NULL,
  source_file VARCHAR(512) NULL,
  source_kind VARCHAR(255) NULL,
  source_line INT NULL,
  PRIMARY KEY (item_id, restriction_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_mob_drops (
  boss_kind VARCHAR(255) NULL,
  chance_base INT NULL,
  chance_effective INT NULL,
  drop_category VARCHAR(255) NULL,
  drop_id VARCHAR(128) NOT NULL,
  drop_slot INT NULL,
  is_map_bonus TINYINT(1) NULL,
  item_aegis_name VARCHAR(255) NULL,
  item_family VARCHAR(255) NULL,
  item_id INT NULL,
  item_ratio_source TINYINT(1) NULL,
  map_id VARCHAR(64) NULL,
  mob_id INT NULL,
  provenance_id VARCHAR(128) NULL,
  random_option_group VARCHAR(255) NULL,
  rate_adjust INT NULL,
  rate_key VARCHAR(255) NULL,
  rate_status VARCHAR(255) NULL,
  rate_unit VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  stealable TINYINT(1) NULL,
  PRIMARY KEY (drop_id),
  INDEX idx_drop_mob (mob_id),
  INDEX idx_drop_item (item_id),
  INDEX idx_drop_cat (drop_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_drop_random_option_links (
  drop_category VARCHAR(255) NULL,
  drop_id VARCHAR(128) NULL,
  drop_random_option_link_id VARCHAR(128) NOT NULL,
  group_db_id INT NULL,
  group_name VARCHAR(128) NULL,
  item_id INT NULL,
  map_id VARCHAR(64) NULL,
  mob_id INT NULL,
  provenance_id VARCHAR(128) NULL,
  random_option_group_id VARCHAR(128) NULL,
  PRIMARY KEY (drop_random_option_link_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_shops (
  cost_item_id TINYINT(1) NULL,
  cost_variable TINYINT(1) NULL,
  currency VARCHAR(255) NULL,
  discount TINYINT(1) NULL,
  inventory_declared TINYINT(1) NULL,
  item_count INT NULL,
  map_id VARCHAR(64) NULL,
  npc_id VARCHAR(128) NULL,
  provenance_id VARCHAR(128) NULL,
  runtime_mutated TINYINT(1) NULL,
  runtime_ops JSON NULL,
  script_line INT NULL,
  script_path VARCHAR(512) NULL,
  shop_id VARCHAR(128) NOT NULL,
  shop_name VARCHAR(128) NULL,
  shop_type VARCHAR(255) NULL,
  source JSON NULL,
  sprite VARCHAR(255) NULL,
  x INT NULL,
  y INT NULL,
  PRIMARY KEY (shop_id),
  INDEX idx_shop_npc (npc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_shop_items (
  item_id INT NULL,
  list_index INT NOT NULL,
  npc_id VARCHAR(128) NULL,
  price INT NULL,
  price_effective INT NULL,
  price_is_default TINYINT(1) NULL,
  price_source VARCHAR(255) NULL,
  shop_id VARCHAR(128) NOT NULL,
  stock INT NULL,
  PRIMARY KEY (shop_id, list_index),
  INDEX idx_shop_item (item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_shop_links (
  caller_npc_id VARCHAR(128) NULL,
  is_runtime TINYINT(1) NULL,
  item_count INT NULL,
  link_id VARCHAR(128) NOT NULL,
  provenance_id VARCHAR(128) NULL,
  resolve_status VARCHAR(255) NULL,
  script_line INT NULL,
  script_path VARCHAR(512) NULL,
  target_name VARCHAR(255) NULL,
  PRIMARY KEY (link_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_shop_link_shops (
  link_id VARCHAR(128) NOT NULL,
  shop_id VARCHAR(128) NOT NULL,
  PRIMARY KEY (link_id, shop_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_quests (
  drop_count INT NULL,
  provenance_id VARCHAR(128) NULL,
  quest_id INT NOT NULL,
  source_file VARCHAR(512) NULL,
  target_count INT NULL,
  time_limit JSON NULL,
  title VARCHAR(255) NULL,
  PRIMARY KEY (quest_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_quest_targets (
  count INT NULL,
  location VARCHAR(255) NULL,
  min_level INT NULL,
  mob_aegis_name VARCHAR(255) NULL,
  mob_id INT NULL,
  mob_subindex INT NOT NULL,
  objective_id INT NULL,
  quest_id INT NOT NULL,
  race VARCHAR(255) NULL,
  source_file VARCHAR(512) NULL,
  target_index INT NOT NULL,
  PRIMARY KEY (quest_id, target_index, mob_subindex)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_quest_drops (
  drop_index INT NOT NULL,
  item_aegis_name VARCHAR(255) NULL,
  item_id INT NULL,
  mob_aegis_name VARCHAR(255) NULL,
  mob_id INT NULL,
  quest_id INT NOT NULL,
  rate INT NULL,
  rate_unit VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (quest_id, drop_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_instances (
  enter_map_id VARCHAR(64) NULL,
  enter_x INT NULL,
  enter_y INT NULL,
  instance_id INT NOT NULL,
  map_count INT NULL,
  name VARCHAR(255) NULL,
  provenance_id VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  time_limit_seconds INT NULL,
  PRIMARY KEY (instance_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_instance_maps (
  in_maps_catalog TINYINT(1) NULL,
  instance_id INT NOT NULL,
  map_id VARCHAR(64) NOT NULL,
  role VARCHAR(255) NULL,
  spawn_rows INT NULL,
  PRIMARY KEY (instance_id, map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_instance_npc_links (
  instance_id INT NULL,
  instance_name VARCHAR(255) NULL,
  link_id VARCHAR(128) NOT NULL,
  match_kind VARCHAR(255) NULL,
  npc_id VARCHAR(128) NULL,
  provenance_id VARCHAR(128) NULL,
  role VARCHAR(255) NULL,
  script_path VARCHAR(512) NULL,
  PRIMARY KEY (link_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_boxes (
  algorithms JSON NULL,
  box_id VARCHAR(128) NOT NULL,
  contains_nested_box TINYINT(1) NULL,
  group_key VARCHAR(128) NULL,
  group_name VARCHAR(128) NULL,
  opener_item_count INT NULL,
  provenance_id VARCHAR(128) NULL,
  reward_count INT NULL,
  source_file VARCHAR(512) NULL,
  subgroup_count INT NULL,
  PRIMARY KEY (box_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_box_rewards (
  algorithm VARCHAR(255) NULL,
  amount INT NULL,
  announced TINYINT(1) NULL,
  box_id VARCHAR(128) NULL,
  chance_effective INT NULL,
  chance_status VARCHAR(255) NULL,
  chance_unit VARCHAR(128) NULL,
  duration INT NULL,
  group_name VARCHAR(128) NULL,
  `index` INT NULL,
  item_aegis_name VARCHAR(255) NULL,
  item_id INT NULL,
  random_option_group VARCHAR(255) NULL,
  rate INT NULL,
  refine_max INT NULL,
  refine_min INT NULL,
  reward_id VARCHAR(128) NOT NULL,
  reward_is_container TINYINT(1) NULL,
  reward_opens_group TINYINT(1) NULL,
  source_file VARCHAR(512) NULL,
  subgroup INT NULL,
  subgroup_total_rate INT NULL,
  PRIMARY KEY (reward_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_box_item_links (
  box_id VARCHAR(128) NULL,
  group_key VARCHAR(128) NULL,
  group_name VARCHAR(128) NULL,
  is_container_flag TINYINT(1) NULL,
  item_id INT NULL,
  link_id VARCHAR(128) NOT NULL,
  provenance_id VARCHAR(128) NULL,
  script_kind VARCHAR(255) NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (link_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_recipes (
  fail_result_item_id TINYINT(1) NULL,
  fail_status VARCHAR(255) NULL,
  item_lv INT NULL,
  produce_id INT NULL,
  provenance_id VARCHAR(128) NULL,
  recipe_family VARCHAR(128) NULL,
  recipe_id VARCHAR(128) NOT NULL,
  require_skill_id INT NULL,
  require_skill_lv INT NULL,
  require_skill_name VARCHAR(128) NULL,
  result_aegis_name VARCHAR(255) NULL,
  result_amount INT NULL,
  result_item_id INT NULL,
  source_file VARCHAR(512) NULL,
  source_kind VARCHAR(255) NULL,
  source_line INT NULL,
  success_chance INT NULL,
  success_chance_unit VARCHAR(128) NULL,
  success_note MEDIUMTEXT NULL,
  success_status VARCHAR(255) NULL,
  zeny_cost TINYINT(1) NULL,
  zeny_note MEDIUMTEXT NULL,
  zeny_status VARCHAR(255) NULL,
  PRIMARY KEY (recipe_id),
  INDEX idx_recipe_result (result_item_id),
  INDEX idx_recipe_family (recipe_family)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_recipe_materials (
  aegis_name VARCHAR(128) NULL,
  amount INT NULL,
  `index` INT NULL,
  item_id INT NULL,
  produce_id INT NULL,
  provenance_id VARCHAR(128) NULL,
  recipe_id VARCHAR(128) NULL,
  recipe_material_id VARCHAR(128) NOT NULL,
  role VARCHAR(255) NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (recipe_material_id),
  INDEX idx_rmat_recipe (recipe_id),
  INDEX idx_rmat_item (item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_enchantments (
  allow_random_options TINYINT(1) NULL,
  chance_unit VARCHAR(128) NULL,
  enchant_db_id INT NULL,
  enchant_id VARCHAR(128) NOT NULL,
  minimum_enchantgrade INT NULL,
  minimum_refine INT NULL,
  provenance_id VARCHAR(128) NULL,
  reset_chance INT NULL,
  reset_price INT NULL,
  slot_order JSON NULL,
  source_file VARCHAR(512) NULL,
  target_count INT NULL,
  PRIMARY KEY (enchant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_enchant_targets (
  aegis_name VARCHAR(128) NULL,
  enchant_db_id INT NULL,
  enchant_id VARCHAR(128) NULL,
  enchant_target_id VARCHAR(128) NOT NULL,
  item_id INT NULL,
  provenance_id VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (enchant_target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_enchant_options (
  aegis_name VARCHAR(128) NULL,
  chance INT NULL,
  chance_unit VARCHAR(128) NULL,
  enchant_db_id INT NULL,
  enchant_id VARCHAR(128) NULL,
  enchant_option_id VARCHAR(128) NOT NULL,
  enchantgrade INT NULL,
  item_id INT NULL,
  kind VARCHAR(255) NULL,
  provenance_id VARCHAR(128) NULL,
  slot INT NULL,
  slot_price INT NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (enchant_option_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_enchant_perfect (
  aegis_name VARCHAR(128) NULL,
  enchant_db_id INT NULL,
  enchant_id VARCHAR(128) NULL,
  enchant_perfect_id VARCHAR(128) NOT NULL,
  item_id INT NULL,
  price INT NULL,
  provenance_id VARCHAR(128) NULL,
  slot INT NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (enchant_perfect_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_enchant_upgrades (
  enchant_db_id INT NULL,
  enchant_id VARCHAR(128) NULL,
  enchant_upgrade_id VARCHAR(128) NOT NULL,
  from_aegis_name VARCHAR(255) NULL,
  from_item_id INT NULL,
  price INT NULL,
  provenance_id VARCHAR(128) NULL,
  slot INT NULL,
  source_file VARCHAR(512) NULL,
  to_aegis_name VARCHAR(255) NULL,
  to_item_id INT NULL,
  PRIMARY KEY (enchant_upgrade_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_enchant_materials (
  aegis_name VARCHAR(128) NULL,
  amount INT NULL,
  context VARCHAR(255) NULL,
  enchant_material_id VARCHAR(128) NOT NULL,
  `index` INT NULL,
  item_id INT NULL,
  parent_id VARCHAR(128) NULL,
  provenance_id VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (enchant_material_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_combo_groups (
  combo_group_id VARCHAR(128) NOT NULL,
  parse_status VARCHAR(255) NULL,
  parsed_effects JSON NULL,
  provenance_id VARCHAR(128) NULL,
  script_body MEDIUMTEXT NULL,
  script_hash VARCHAR(255) NULL,
  set_count INT NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (combo_group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_combo_sets (
  combo_group_id VARCHAR(128) NULL,
  combo_set_id VARCHAR(128) NOT NULL,
  `index` INT NULL,
  member_count INT NULL,
  provenance_id VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (combo_set_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_combo_members (
  aegis_name VARCHAR(128) NULL,
  combo_group_id VARCHAR(128) NULL,
  combo_member_id VARCHAR(128) NOT NULL,
  combo_set_id VARCHAR(128) NULL,
  `index` INT NULL,
  item_id INT NULL,
  provenance_id VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (combo_member_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_dependencies (
  amount INT NULL,
  barter_name VARCHAR(128) NULL,
  box_id VARCHAR(128) NULL,
  combo_group_id VARCHAR(128) NULL,
  combo_set_id VARCHAR(128) NULL,
  dependency_kind VARCHAR(255) NULL,
  from_item_id INT NULL,
  func_name VARCHAR(255) NULL,
  group_name VARCHAR(128) NULL,
  item_dependency_id VARCHAR(128) NOT NULL,
  provenance_id VARCHAR(128) NULL,
  recipe_id VARCHAR(128) NULL,
  role VARCHAR(255) NULL,
  script_path VARCHAR(512) NULL,
  source_ref VARCHAR(255) NULL,
  to_item_id INT NULL,
  PRIMARY KEY (item_dependency_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_barters (
  barter_id VARCHAR(128) NOT NULL,
  barter_name VARCHAR(128) NULL,
  direction TINYINT(1) NULL,
  map_name TINYINT(1) NULL,
  npc_id TINYINT(1) NULL,
  provenance_id VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  sprite TINYINT(1) NULL,
  x INT NULL,
  y INT NULL,
  PRIMARY KEY (barter_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_barter_items (
  aegis_name VARCHAR(128) NULL,
  barter_id VARCHAR(128) NULL,
  barter_item_id VARCHAR(128) NOT NULL,
  barter_name VARCHAR(128) NULL,
  `index` INT NULL,
  item_id INT NULL,
  provenance_id VARCHAR(128) NULL,
  refine INT NULL,
  source_file VARCHAR(512) NULL,
  stock INT NULL,
  zeny INT NULL,
  PRIMARY KEY (barter_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_barter_required_items (
  aegis_name VARCHAR(128) NULL,
  amount INT NULL,
  barter_id VARCHAR(128) NULL,
  barter_item_id VARCHAR(128) NULL,
  barter_name VARCHAR(128) NULL,
  barter_required_id VARCHAR(128) NOT NULL,
  item_id INT NULL,
  offer_index INT NULL,
  provenance_id VARCHAR(128) NULL,
  refine INT NULL,
  req_index INT NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (barter_required_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_random_options (
  option_db_id INT NULL,
  option_name VARCHAR(128) NULL,
  provenance_id VARCHAR(128) NULL,
  random_option_id VARCHAR(128) NOT NULL,
  script MEDIUMTEXT NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (random_option_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_random_option_groups (
  group_db_id INT NULL,
  group_name VARCHAR(128) NULL,
  max_random INT NULL,
  provenance_id VARCHAR(128) NULL,
  random_option_group_id VARCHAR(128) NOT NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (random_option_group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_random_option_group_slots (
  chance INT NULL,
  chance_unit VARCHAR(128) NULL,
  group_db_id INT NULL,
  group_name VARCHAR(128) NULL,
  group_slot_entry_id VARCHAR(128) NOT NULL,
  `index` INT NULL,
  max_value INT NULL,
  min_value INT NULL,
  option_db_id INT NULL,
  option_name VARCHAR(128) NULL,
  param INT NULL,
  provenance_id VARCHAR(128) NULL,
  random_option_group_id VARCHAR(128) NULL,
  slot INT NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (group_slot_entry_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_random_option_group_random (
  chance INT NULL,
  chance_unit VARCHAR(128) NULL,
  group_db_id INT NULL,
  group_name VARCHAR(128) NULL,
  group_random_entry_id VARCHAR(128) NOT NULL,
  `index` INT NULL,
  max_value INT NULL,
  min_value INT NULL,
  option_db_id INT NULL,
  option_name VARCHAR(128) NULL,
  param INT NULL,
  provenance_id VARCHAR(128) NULL,
  random_option_group_id VARCHAR(128) NULL,
  source_file VARCHAR(512) NULL,
  PRIMARY KEY (group_random_entry_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_enchant_sources (
  getitem2_count INT NULL,
  kind VARCHAR(255) NULL,
  npc_enchant_source_id VARCHAR(128) NOT NULL,
  provenance_id VARCHAR(128) NULL,
  script_path VARCHAR(512) NULL,
  stone_count INT NULL,
  target_count INT NULL,
  transform_count INT NULL,
  PRIMARY KEY (npc_enchant_source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_enchant_items (
  evidence JSON NULL,
  item_id INT NULL,
  npc_enchant_item_id VARCHAR(128) NOT NULL,
  npc_enchant_source_id VARCHAR(128) NULL,
  provenance_id VARCHAR(128) NULL,
  role VARCHAR(255) NULL,
  script_path VARCHAR(512) NULL,
  PRIMARY KEY (npc_enchant_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_item_transforms (
  from_item_id INT NULL,
  func_name VARCHAR(255) NULL,
  npc_enchant_source_id VARCHAR(128) NULL,
  npc_item_transform_id VARCHAR(128) NOT NULL,
  provenance_id VARCHAR(128) NULL,
  script_path VARCHAR(512) NULL,
  to_item_id INT NULL,
  transform_kind VARCHAR(255) NULL,
  PRIMARY KEY (npc_item_transform_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_acquisition_outputs (
  acquisition_output_id VARCHAR(128) NOT NULL,
  algorithm VARCHAR(255) NULL,
  barter_name VARCHAR(128) NULL,
  box_id VARCHAR(128) NULL,
  chance_status VARCHAR(255) NULL,
  command VARCHAR(255) NULL,
  from_item_id INT NULL,
  func_name VARCHAR(255) NULL,
  group_name VARCHAR(128) NULL,
  item_id INT NULL,
  map_id VARCHAR(64) NULL,
  mob_id INT NULL,
  npc_id VARCHAR(128) NULL,
  price INT NULL,
  probability INT NULL,
  probability_unit VARCHAR(255) NULL,
  provenance_id VARCHAR(128) NULL,
  quantity_max INT NULL,
  quantity_min INT NULL,
  refine INT NULL,
  role VARCHAR(255) NULL,
  script_path VARCHAR(512) NULL,
  source_ref VARCHAR(255) NULL,
  source_type VARCHAR(255) NULL,
  stock INT NULL,
  zeny INT NULL,
  list_index INT NOT NULL,
  PRIMARY KEY (acquisition_output_id, list_index),
  INDEX idx_acq_item (item_id),
  INDEX idx_acq_type (source_type),
  INDEX idx_acq_npc (npc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_source_provenance (
  provenance_id CHAR(40) NOT NULL,
  domain VARCHAR(64) NULL,
  record_id VARCHAR(128) NULL,
  source_kind VARCHAR(64) NULL,
  source_path VARCHAR(512) NULL,
  source_ref VARCHAR(256) NULL,
  transform VARCHAR(64) NULL,
  PRIMARY KEY (provenance_id),
  INDEX idx_prov_domain (domain)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_dataset_metadata (
  dataset_version VARCHAR(64) NOT NULL,
  generated_at DATETIME NULL,
  source_fingerprint CHAR(64) NULL,
  notes JSON NULL,
  PRIMARY KEY (dataset_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

