-- OzRo Master World Dataset — contract schema (Etapa 1).
-- Prefix is configurable; default ozro_. Adjust via config/database.yml on sync.
-- Idempotent sync (Etapa 5) will recreate/replace contents; this file defines structure.

CREATE TABLE IF NOT EXISTS ozro_dataset_metadata (
  dataset_version VARCHAR(64) NOT NULL PRIMARY KEY,
  generated_at DATETIME NOT NULL,
  source_fingerprint CHAR(64) NOT NULL,
  notes JSON NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_source_provenance (
  provenance_id CHAR(40) NOT NULL PRIMARY KEY,
  domain VARCHAR(64) NOT NULL,
  record_id VARCHAR(128) NOT NULL,
  source_kind VARCHAR(64) NOT NULL,
  source_path VARCHAR(512) NOT NULL,
  source_ref VARCHAR(256) NULL,
  transform VARCHAR(64) NOT NULL,
  raw_excerpt MEDIUMTEXT NULL,
  INDEX idx_prov_record (domain, record_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_maps (
  map_id VARCHAR(64) NOT NULL PRIMARY KEY,
  display_name VARCHAR(128) NULL,
  category VARCHAR(32) NULL,
  categories JSON NULL,
  is_town TINYINT(1) NOT NULL DEFAULT 0,
  is_dungeon TINYINT(1) NOT NULL DEFAULT 0,
  is_instance TINYINT(1) NOT NULL DEFAULT 0,
  is_quest_map TINYINT(1) NOT NULL DEFAULT 0,
  is_guild_map TINYINT(1) NOT NULL DEFAULT 0,
  is_interior TINYINT(1) NOT NULL DEFAULT 0,
  is_accessible TINYINT(1) NOT NULL DEFAULT 1,
  access_conditions JSON NULL,
  width INT NULL,
  height INT NULL,
  client_resource_present TINYINT(1) NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_map_connections (
  connection_id CHAR(40) NOT NULL PRIMARY KEY,
  connection_type VARCHAR(32) NOT NULL,
  source_map_id VARCHAR(64) NOT NULL,
  source_x INT NULL,
  source_y INT NULL,
  destination_map_id VARCHAR(64) NOT NULL,
  destination_x INT NULL,
  destination_y INT NULL,
  npc_id VARCHAR(128) NULL,
  zeny_cost INT NULL,
  required_items JSON NULL,
  conditions JSON NULL,
  is_directional TINYINT(1) NOT NULL DEFAULT 1,
  friction_weight DECIMAL(8,3) NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_conn_src (source_map_id),
  INDEX idx_conn_dst (destination_map_id),
  INDEX idx_conn_type (connection_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_map_distances (
  from_map_id VARCHAR(64) NOT NULL,
  to_map_id VARCHAR(64) NOT NULL,
  friction DECIMAL(12,4) NOT NULL,
  hop_count INT NOT NULL,
  PRIMARY KEY (from_map_id, to_map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_map_routes (
  from_map_id VARCHAR(64) NOT NULL,
  to_map_id VARCHAR(64) NOT NULL,
  connection_ids JSON NOT NULL,
  PRIMARY KEY (from_map_id, to_map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npcs (
  npc_id VARCHAR(128) NOT NULL PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  display_name VARCHAR(128) NULL,
  map_id VARCHAR(64) NULL,
  x INT NULL,
  y INT NULL,
  sprite_id INT NULL,
  npc_type VARCHAR(64) NULL,
  functions JSON NULL,
  description TEXT NULL,
  script_path VARCHAR(512) NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_npc_map (map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_functions (
  npc_id VARCHAR(128) NOT NULL,
  function_name VARCHAR(64) NOT NULL,
  PRIMARY KEY (npc_id, function_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_quests (
  npc_id VARCHAR(128) NOT NULL,
  quest_id VARCHAR(64) NOT NULL,
  role VARCHAR(32) NULL,
  PRIMARY KEY (npc_id, quest_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_mobs (
  mob_id INT NOT NULL PRIMARY KEY,
  aegis_name VARCHAR(64) NOT NULL,
  name VARCHAR(128) NULL,
  japanese_name VARCHAR(128) NULL,
  mob_class VARCHAR(32) NULL,
  mob_role VARCHAR(32) NOT NULL DEFAULT 'pending',
  is_mvp TINYINT(1) NOT NULL DEFAULT 0,
  level INT NULL,
  hp_base BIGINT NULL,
  hp_multiplier DECIMAL(10,4) NULL,
  hp_effective BIGINT NULL,
  sp INT NULL,
  base_exp_base BIGINT NULL,
  base_exp_effective BIGINT NULL,
  job_exp_base BIGINT NULL,
  job_exp_effective BIGINT NULL,
  mvp_exp_base BIGINT NULL,
  mvp_exp_effective BIGINT NULL,
  attack INT NULL,
  attack2 INT NULL,
  defense INT NULL,
  magic_defense INT NULL,
  stats JSON NULL,
  race VARCHAR(32) NULL,
  size VARCHAR(16) NULL,
  element VARCHAR(32) NULL,
  element_level INT NULL,
  modes JSON NULL,
  sprite_name VARCHAR(64) NULL,
  has_sprite TINYINT(1) NULL,
  provenance_id CHAR(40) NULL,
  UNIQUE KEY uq_mob_aegis (aegis_name),
  INDEX idx_mob_role (mob_role),
  INDEX idx_mob_class (mob_class)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_spawns (
  spawn_id CHAR(40) NOT NULL PRIMARY KEY,
  mob_id INT NOT NULL,
  map_id VARCHAR(64) NULL,
  spawn_type VARCHAR(32) NOT NULL,
  amount INT NULL,
  x INT NULL,
  y INT NULL,
  x_area INT NULL,
  y_area INT NULL,
  respawn_min INT NULL,
  respawn_max INT NULL,
  respawn_unit VARCHAR(16) NULL,
  spawn_condition JSON NULL,
  event_id VARCHAR(64) NULL,
  parent_mob_id INT NULL,
  skill_id INT NULL,
  script_path VARCHAR(512) NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_spawn_mob (mob_id),
  INDEX idx_spawn_map (map_id),
  INDEX idx_spawn_parent (parent_mob_id),
  INDEX idx_spawn_type (spawn_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_skills (
  skill_id INT NOT NULL PRIMARY KEY,
  aegis_name VARCHAR(128) NULL,
  name VARCHAR(128) NULL,
  skill_owner VARCHAR(16) NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_mob_skills (
  mob_skill_id CHAR(40) NOT NULL PRIMARY KEY,
  mob_id INT NOT NULL,
  skill_id INT NULL,
  skill_name VARCHAR(128) NULL,
  state VARCHAR(32) NULL,
  skill_lv INT NULL,
  rate INT NULL,
  condition_type VARCHAR(64) NULL,
  condition_value VARCHAR(64) NULL,
  val1 INT NULL,
  vals JSON NULL,
  source_file VARCHAR(512) NULL,
  source_line INT NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_mob_skill_mob (mob_id),
  INDEX idx_mob_skill_skill (skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_skill_summons (
  summon_id CHAR(40) NOT NULL PRIMARY KEY,
  summon_kind VARCHAR(32) NOT NULL,
  parent_mob_id INT NULL,
  skill_id INT NULL,
  summoned_mob_id INT NOT NULL,
  amount INT NULL,
  conditions JSON NULL,
  source_file VARCHAR(512) NULL,
  source_line INT NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_summon_parent (parent_mob_id),
  INDEX idx_summon_child (summoned_mob_id),
  INDEX idx_summon_kind (summon_kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_items (
  item_id INT NOT NULL PRIMARY KEY,
  aegis_name VARCHAR(64) NOT NULL,
  name VARCHAR(128) NULL,
  display_name VARCHAR(128) NULL,
  type VARCHAR(32) NULL,
  subtype VARCHAR(32) NULL,
  item_category VARCHAR(32) NULL,
  item_subcategory VARCHAR(64) NULL,
  is_costume TINYINT(1) NOT NULL DEFAULT 0,
  equip_slot_key VARCHAR(128) NULL,
  equip_slot_families JSON NULL,
  card_insert_key VARCHAR(128) NULL,
  card_insert_slots JSON NULL,
  buy_base INT NULL,
  sell_base INT NULL,
  buy_effective INT NULL,
  sell_effective INT NULL,
  weight INT NULL,
  attack INT NULL,
  magic_attack INT NULL,
  defense INT NULL,
  range_atk INT NULL,
  slots INT NULL,
  weapon_level INT NULL,
  armor_level INT NULL,
  equip_level_min INT NULL,
  equip_level_max INT NULL,
  refineable TINYINT(1) NULL,
  view_id INT NULL,
  flags JSON NULL,
  jobs JSON NULL,
  locations JSON NULL,
  sprite_name VARCHAR(128) NULL,
  has_sprite TINYINT(1) NULL,
  has_item_icon TINYINT(1) NULL,
  assets_complete TINYINT(1) NULL,
  provenance_id CHAR(40) NULL,
  UNIQUE KEY uq_item_aegis (aegis_name),
  INDEX idx_item_type (type),
  INDEX idx_item_category (item_category),
  INDEX idx_item_costume (is_costume)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_properties (
  item_id INT NOT NULL,
  property_key VARCHAR(64) NOT NULL,
  property_value JSON NOT NULL,
  layer ENUM('original','normalized','effective','inferred') NOT NULL,
  PRIMARY KEY (item_id, property_key, layer)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_scripts (
  item_script_id CHAR(40) NOT NULL PRIMARY KEY,
  item_id INT NOT NULL,
  script_kind ENUM('Script','EquipScript','UnEquipScript','other') NOT NULL,
  trigger_name VARCHAR(32) NULL,
  script_body MEDIUMTEXT NOT NULL,
  script_hash CHAR(40) NULL,
  parsed_effects JSON NULL,
  parse_status VARCHAR(32) NULL,
  source_file VARCHAR(512) NULL,
  provenance_id CHAR(40) NULL,
  UNIQUE KEY uq_item_script_kind (item_id, script_kind),
  INDEX idx_item_script_item (item_id),
  INDEX idx_item_script_status (parse_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_restrictions (
  item_id INT NOT NULL,
  restriction_key VARCHAR(64) NOT NULL,
  restriction_value JSON NOT NULL,
  source_kind VARCHAR(32) NULL,
  source_file VARCHAR(512) NULL,
  provenance_id CHAR(40) NULL,
  PRIMARY KEY (item_id, restriction_key),
  INDEX idx_item_restrict_key (restriction_key),
  INDEX idx_item_restrict_src (source_kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_enchantments (
  enchantment_id VARCHAR(64) NOT NULL PRIMARY KEY,
  item_id INT NULL,
  data JSON NOT NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_acquisition_sources (
  source_id CHAR(40) NOT NULL PRIMARY KEY,
  source_type VARCHAR(64) NOT NULL,
  label VARCHAR(128) NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_source_outputs (
  source_id CHAR(40) NOT NULL,
  item_id INT NOT NULL,
  quantity_min INT NULL,
  quantity_max INT NULL,
  chance_base DECIMAL(12,6) NULL,
  chance_effective DECIMAL(12,6) NULL,
  PRIMARY KEY (source_id, item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_mob_drops (
  drop_id CHAR(40) NOT NULL PRIMARY KEY,
  mob_id INT NOT NULL,
  item_id INT NOT NULL,
  drop_category VARCHAR(32) NULL,
  is_map_bonus TINYINT(1) NOT NULL DEFAULT 0,
  drop_slot INT NULL,
  chance_base INT NULL,
  chance_effective INT NULL,
  rate_unit VARCHAR(16) NULL,
  rate_key VARCHAR(64) NULL,
  rate_adjust INT NULL,
  rate_status VARCHAR(32) NULL,
  boss_kind VARCHAR(16) NULL,
  item_family VARCHAR(16) NULL,
  stealable TINYINT(1) NULL,
  map_id VARCHAR(64) NULL,
  source_file VARCHAR(512) NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_drop_mob (mob_id),
  INDEX idx_drop_item (item_id),
  INDEX idx_drop_cat (drop_category),
  INDEX idx_drop_map (map_id),
  INDEX idx_drop_map_bonus (is_map_bonus),
  INDEX idx_drop_rate_status (rate_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_shops (
  shop_id CHAR(40) NOT NULL PRIMARY KEY,
  npc_id VARCHAR(128) NOT NULL,
  shop_name VARCHAR(128) NULL,
  shop_type VARCHAR(32) NOT NULL,
  currency VARCHAR(64) NULL,
  cost_item_id INT NULL,
  cost_variable VARCHAR(64) NULL,
  discount TINYINT(1) NULL,
  script_path VARCHAR(512) NULL,
  script_line INT NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_shop_npc (npc_id),
  INDEX idx_shop_type (shop_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_shop_items (
  shop_id CHAR(40) NOT NULL,
  item_id INT NOT NULL,
  price INT NULL,
  stock INT NULL,
  price_is_default TINYINT(1) NULL,
  PRIMARY KEY (shop_id, item_id),
  INDEX idx_shop_item (item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_shop_links (
  link_id CHAR(40) NOT NULL PRIMARY KEY,
  caller_npc_id VARCHAR(128) NULL,
  target_name VARCHAR(128) NULL,
  resolve_status VARCHAR(32) NOT NULL,
  script_path VARCHAR(512) NULL,
  script_line INT NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_shop_link_caller (caller_npc_id),
  INDEX idx_shop_link_status (resolve_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_shop_link_shops (
  link_id CHAR(40) NOT NULL,
  shop_id CHAR(40) NOT NULL,
  PRIMARY KEY (link_id, shop_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_npc_script_evidence (
  evidence_id CHAR(40) NOT NULL PRIMARY KEY,
  npc_id VARCHAR(128) NOT NULL,
  script_path VARCHAR(512) NULL,
  script_line INT NULL,
  functions JSON NULL,
  quest_ids JSON NULL,
  mob_commands JSON NULL,
  variable_count INT NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_npc_evidence_npc (npc_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_quests (
  quest_id VARCHAR(64) NOT NULL PRIMARY KEY,
  name VARCHAR(128) NULL,
  data JSON NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_instances (
  instance_id VARCHAR(64) NOT NULL PRIMARY KEY,
  name VARCHAR(128) NULL,
  data JSON NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_boxes (
  box_id VARCHAR(64) NOT NULL PRIMARY KEY,
  item_id INT NULL,
  data JSON NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_box_rewards (
  box_id VARCHAR(64) NOT NULL,
  item_id INT NOT NULL,
  amount INT NULL,
  chance DECIMAL(12,6) NULL,
  PRIMARY KEY (box_id, item_id, amount)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_recipes (
  recipe_id CHAR(40) NOT NULL PRIMARY KEY,
  result_item_id INT NOT NULL,
  skill VARCHAR(64) NULL,
  skill_level INT NULL,
  data JSON NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_recipe_materials (
  recipe_id CHAR(40) NOT NULL,
  item_id INT NOT NULL,
  amount INT NOT NULL,
  PRIMARY KEY (recipe_id, item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_enchantments (
  enchantment_id VARCHAR(64) NOT NULL PRIMARY KEY,
  name VARCHAR(128) NULL,
  data JSON NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_enchantment_materials (
  enchantment_id VARCHAR(64) NOT NULL,
  item_id INT NOT NULL,
  amount INT NOT NULL,
  PRIMARY KEY (enchantment_id, item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_combos (
  combo_id CHAR(40) NOT NULL PRIMARY KEY,
  script_body MEDIUMTEXT NULL,
  provenance_id CHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ozro_item_relationships (
  relationship_id CHAR(40) NOT NULL PRIMARY KEY,
  relationship_type VARCHAR(64) NOT NULL,
  left_item_id INT NOT NULL,
  right_item_id INT NOT NULL,
  data JSON NULL,
  provenance_id CHAR(40) NULL,
  INDEX idx_rel_left (left_item_id),
  INDEX idx_rel_right (right_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
