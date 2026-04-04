from __future__ import annotations

import argparse
import os
import random

from champs.db import db
from champs.draft import (
    DraftPlayer,
    _build_draft,
    _build_resolver_state,
    _format_draft_message,
    _resolve_player_identifier,
)


def _all_available_players(db_path: str) -> list[DraftPlayer]:
    state = _build_resolver_state(db_path)
    names = sorted(set(state.canonical_name_by_casefold.values()), key=str.casefold)
    players: list[DraftPlayer] = []
    for name in names:
        player = _resolve_player_identifier(name, state)
        if player is not None:
            players.append(player)
    return players


def _strip_discord_code_block(text: str) -> str:
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a random balanced draft from all available players."
    )
    parser.add_argument("--db-path", default=os.getenv("CHAMPS_DB_PATH", "/opt/random-champs/data/champs.db"))
    parser.add_argument("--seed", type=int, help="Optional random seed for reproducible random player selection.")
    args = parser.parse_args()

    db.init_db(args.db_path)
    all_players = _all_available_players(args.db_path)

    if len(all_players) < 10:
        raise ValueError(f"Need at least 10 available players, found {len(all_players)}.")

    rng = random.Random(args.seed)
    selected = all_players if len(all_players) == 10 else rng.sample(all_players, 10)
    draft = _build_draft(selected, randomize=True, rng=rng)
    print(_strip_discord_code_block(_format_draft_message(draft)))


if __name__ == "__main__":
    main()
