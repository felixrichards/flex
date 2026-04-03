# Champsget

## Manual ELO Script

Use `manual_elo.py` for offline ELO maintenance (outside the Discord bot runtime).

### 1. Recalculate all ratings from stored history

```bash
poetry run python manual_elo.py --db-path /opt/random-champs/data/champs.db --recalculate
```

### 2. Add backlog matches from JSON

```bash
poetry run python manual_elo.py --db-path /opt/random-champs/data/champs.db --input-file backlog.json
```

Accepted JSON shapes for `--input-file`:
- single match object
- list of match objects
- `{ "matches": [ ... ] }`

### 3. Do both in one run

```bash
poetry run python manual_elo.py --db-path /opt/random-champs/data/champs.db --input-file backlog.json --recalculate
```

## Testing

Install dev dependencies (includes `pytest`):

```bash
poetry install --extras dev
```

Run all tests:

```bash
poetry run pytest -q
```

Run one test file:

```bash
poetry run pytest -q tests/test_elo_iterative.py
```

### Resource-driven scoreboard parser tests

Add fixtures under `tests/resources/`:
- image files (for example `tests/resources/scoreboards/case_01.png`)
- case index file: `tests/resources/scoreboard_cases.json`

Then run:

```bash
poetry run pytest -q tests/test_scoreboard_parser_resources.py
```
