# ozro-data

Master World Dataset for OzRo. Regenerates SQL from rAthena + client GRF sources.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python pipeline.py discover
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
```


Paths: `config/extractor.yml`. Schema: `database/schema/`. Final field docs: later (`DATA.md`).
