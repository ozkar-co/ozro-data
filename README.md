# ozro-data

Master World Dataset for OzRo. Extracts rAthena + client GRF sources to JSONL, then syncs into MySQL (`ozro_*`).

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python pipeline.py discover
python pipeline.py resolve        # Etapa 4: rates catalog → configuration_effective.json + dataset_rates.jsonl
python pipeline.py extract level_penalty  # Pre-E5: flat Type/Difference/Rate
python pipeline.py extract maps   # needs reports/client_maps.jsonl
python pipeline.py extract mobs   # needs reports/client_mob_server_gaps.jsonl
python pipeline.py extract items  # needs reports/client_item_info.jsonl
python pipeline.py extract npcs   # needs reports/discovery_files.yml
python pipeline.py extract map_connections  # warps+OzRo TP+kafra+airship+boat; audit JSON
python pipeline.py extract map_distances    # Dijkstra all-pairs from map_connections.jsonl
python pipeline.py extract skills           # mob_skill_db → summons/slaves
python pipeline.py extract spawns           # headers+scripted+slaves; needs skills for slaves
python pipeline.py extract mobs             # re-run after spawns to resolve mob_role
python pipeline.py extract shops            # header shop/cashshop/… → npc_shops + items
python pipeline.py extract npc_scripts      # script body evidence → refine npc functions
python pipeline.py extract item_scripts     # Script/EquipScript/UnEquipScript from item_db
python pipeline.py extract item_restrictions # Trade.* + item_noequip bitmask
python pipeline.py extract drops            # mob_db + map_drops + mob_item_ratio; needs items+mobs
python pipeline.py extract quests           # quest_db + npc links; needs mobs/items/evidence
python pipeline.py extract instances        # instance_db + maps + NPC create links
python pipeline.py extract boxes            # item_group_db + getgroupitem links
python pipeline.py extract recipes          # produce_db → recipes + materials
python pipeline.py extract enchantments     # item_enchant.yml targets/options/perfect/upgrades
python pipeline.py extract item_relationships  # item_combos.yml groups/sets/members
python pipeline.py extract random_options   # item_randomopt_db/group + drop links
python pipeline.py extract barters          # barters.yml inventory + RequiredItems
python pipeline.py extract npc_enchants     # getitem2/socket NPC stone+target inventory
python pipeline.py extract acquisition      # union drops/shops/barters/boxes/recipes/quests
python pipeline.py extract item_dependencies  # §22.2 consume/produce/socket/combo/box edges
python pipeline.py extract npc_script_rewards # literal getitem/getitembound → NPC
python pipeline.py extract closure_sanity   # Etapa 3 closure checks + smoke map list
python pipeline.py schema --reset           # Etapa 5: DROP+CREATE ozro_* (MySQL in config/database.yml)
python pipeline.py sync                     # Etapa 5: full-replace JSONL → ozro_*
```


**Integration reference:** [`DATA.md`](DATA.md) (catalog, units, flags, query patterns).  
**Extract coverage:** [`database/EXTRACT_COVERAGE.md`](database/EXTRACT_COVERAGE.md) (YAML → JSONL gaps).  
Paths: `config/extractor.yml`. Schema: `database/schema/`. Delta vs E1: `database/SCHEMA_DELTA.md`.
