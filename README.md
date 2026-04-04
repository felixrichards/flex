# Champsget

Discord command prefix is `champs` (for example `champsget`, `champsmatch`, `champselo`).

## Bot Commands

- `champsget [N] [filters...]`
  Return random champions (weighted by role by default), optionally filtered.

- `champsmatch`
  Attach a scoreboard image to parse and review.

- `champsmatch delete`
  Attach a scoreboard image to delete the matching match from history.

- `champsmatch addplayer <username> <name> [primary_role] [secondary_role]`
  Add username -> real-name mapping, optionally role-scoped.
  Role aliases are supported (for example `adc` -> `BOT`, `jgl` -> `JUNGLE`).

- `champsmatch linkdiscord <league_username> [@discord_user_or_id]`
  Link Discord user IDs to league usernames so voice-channel detection works when Discord names differ.
  If no Discord user is passed, links the command caller.

- `champsmatch viewplayers`
  Show player role mappings table with name, usernames, primary/secondary roles, and linked Discord IDs.

- `champsmatch help`
  Show match command help.

- `champselo [player_or_username ...]`
  Show ELO table (rank, player, elo, wins, losses), optionally filtered by player names/usernames.
  Username arguments are resolved to mapped real names.

## Manual ELO Script (`manual_elo.py`)

Use `manual_elo.py` for offline ELO maintenance (outside the Discord bot runtime).

`--recalculate` now also reapplies current DB-backed username -> name mappings to historical match rows before rebuilding ratings.

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

### 4. Set mappings directly from CLI

```bash
poetry run python manual_elo.py --db-path /opt/random-champs/data/champs.db --set-mapping MaBalls Felix
poetry run python manual_elo.py --db-path /opt/random-champs/data/champs.db --set-mapping Wyn Wyn BOT
poetry run python manual_elo.py --db-path /opt/random-champs/data/champs.db --set-mapping Wyn Sean MID BOT
```

Set preferred primary role for latest mapped name:

```bash
poetry run python manual_elo.py --db-path /opt/random-champs/data/champs.db --set-preferred-role Wyn MID
```

### 5. Load player mappings from JSON

```bash
poetry run python manual_elo.py --db-path /opt/random-champs/data/champs.db --players-file players.json
```

Accepted JSON shapes for `--players-file`:
- single row object
- list of row objects
- `{ "players": [ ... ] }`

Player mapping row schema:
- `username` (required)
- `name` (required)
- `primary_role` (optional)
- `secondary_role` (optional)

## Manual Scoreboard Script (`manual_scoreboard.py`)

Use `manual_scoreboard.py` to parse a scoreboard image and print match JSON.

```bash
poetry run python manual_scoreboard.py /path/to/scoreboard.png
```

Compact JSON output:

```bash
poetry run python manual_scoreboard.py /path/to/scoreboard.png --compact
```

## Manual Draft Script (`manual_draft.py`)

Use `manual_draft.py` to generate a random `5v5` draft from all available players in DB.

```bash
poetry run python manual_draft.py --db-path /opt/random-champs/data/champs.db
```

Optional deterministic sampling:

```bash
poetry run python manual_draft.py --db-path /opt/random-champs/data/champs.db --seed 1337
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
