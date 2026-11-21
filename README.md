# ozro-data

Master World Dataset for OzRo. Regenerates SQL from rAthena + client GRF sources.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python pipeline.py discover
python pipeline.py extract maps   # needs reports/client_maps.jsonl
```

Paths: `config/extractor.yml`. Schema: `database/schema/`. Final field docs: later (`DATA.md`).
