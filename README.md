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
python pipeline.py extract map_connections  # needs npcs.jsonl + discovery_files.yml
python pipeline.py extract spawns # needs discovery_files.yml (+ mobs.jsonl for AegisName)
```


Paths: `config/extractor.yml`. Schema: `database/schema/`. Final field docs: later (`DATA.md`).
