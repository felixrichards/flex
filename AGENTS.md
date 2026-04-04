# Project Context

This repository contains a lightweight Discord bot for League of Legends custom-game tooling:
- random champion generation (`champsget`)
- scoreboard OCR parsing (`champsmatch`)
- match history persistence + ELO tracking (SQLite + SQLAlchemy)
- manual maintenance scripts (`manual_elo.py`, `manual_scoreboard.py`)

The app is optimized for a small private user group, but still has validation, tests, and reproducible CV/OCR behavior.

# Start-of-Task Checklist

At the beginning of each new task:
1. Read this `AGENTS.md` file.
2. Read `codex/TASKS.md` for high-level project history.
3. Read `codex/LOG.md` for technical change history.

# Environment Setup

1. Install dependencies:
```bash
poetry install --extras dev
```

2. Run tests:
```bash
poetry run pytest -q
```

3. Run bot (requires `DISCORD_TOKEN` and optional `CHAMPS_DB_PATH`):
```bash
poetry run python -m champs
```

4. Useful manual scripts:
```bash
poetry run python manual_elo.py --help
poetry run python manual_scoreboard.py --help
```

# Testing Notes

- Full suite:
```bash
poetry run pytest -q tests
```
- Scoreboard parser fixtures:
```bash
poetry run pytest -q tests/test_scoreboard_parser_resources.py
```
- ELO/mapping behavior:
```bash
poetry run pytest -q tests/test_elo_iterative.py tests/test_elo_query.py tests/test_player_name_map.py
```
