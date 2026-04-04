from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from champs.db import db
from champs.db.models import MatchPlayerRecord, PlayerRecord
from champs.payloads import Match, PlayerMappingImport, PlayerMappingRow


def _timestamp_from_date(date_value: str, sequence_index: int = 0) -> datetime:
    normalized = date_value.strip()
    formats = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d")
    parsed: datetime | None = None
    for fmt in formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValueError(f"Unsupported match date format: {date_value!r}. Expected dd/mm/yyyy, dd-mm-yyyy, or yyyy-mm-dd.")
    # Rough but deterministic ordering within a day.
    return parsed.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=timezone.utc) + timedelta(seconds=sequence_index)


def _load_matches(payload: object) -> list[Match]:
    if isinstance(payload, dict) and "matches" in payload:
        payload = payload["matches"]
    if isinstance(payload, dict):
        match = Match.model_validate(payload)
        if match.date:
            match = match.model_copy(update={"timestamp": _timestamp_from_date(match.date)})
        return [match]
    if isinstance(payload, list):
        matches: list[Match] = []
        for idx, item in enumerate(payload):
            match = Match.model_validate(item)
            if match.date:
                match = match.model_copy(update={"timestamp": _timestamp_from_date(match.date, sequence_index=idx)})
            matches.append(match)
        return matches
    raise ValueError("Payload must be a Match object, a list of matches, or {'matches': [...]} shape.")


def _load_player_mappings(payload: object) -> list[PlayerMappingRow]:
    if isinstance(payload, dict):
        if "players" in payload:
            return PlayerMappingImport.model_validate(payload).players
        return [PlayerMappingRow.model_validate(payload)]
    if isinstance(payload, list):
        return [PlayerMappingRow.model_validate(item) for item in payload]
    raise ValueError(
        "Player mapping payload must be a row object, a list of rows, or {'players': [...]} shape."
    )


def _insert_matches(db_path: str, matches: Iterable[Match]) -> tuple[int, int]:
    ordered_matches = sorted(list(matches), key=lambda match: match.timestamp)
    inserted = 0
    skipped = 0
    for match in ordered_matches:
        if db.insert_match(db_path, match):
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


def _print_ratings_table(db_path: str) -> None:
    engine = db._engine(db_path)
    with Session(engine) as session:
        players = session.scalars(select(PlayerRecord)).all()
        match_rows = session.scalars(select(MatchPlayerRecord)).all()

    if not players:
        print("No players found in DB.")
        return

    records_by_player: dict[str, tuple[int, int]] = {}
    for row in match_rows:
        wins, losses = records_by_player.get(row.player_name, (0, 0))
        if row.win:
            wins += 1
        else:
            losses += 1
        records_by_player[row.player_name] = (wins, losses)

    rows = []
    for player in players:
        wins, losses = records_by_player.get(player.name, (0, 0))
        rows.append((player.name, int(player.rating), wins, losses))
    rows.sort(key=lambda row: (-row[1], row[0].lower()))

    name_width = max(len("Player"), *(len(name) for name, _, _, _ in rows))
    rating_width = max(len("ELO"), *(len(str(rating)) for _, rating, _, _ in rows))
    wins_width = max(len("Wins"), *(len(str(wins)) for _, _, wins, _ in rows))
    losses_width = max(len("Losses"), *(len(str(losses)) for _, _, _, losses in rows))
    border = f"+-{'-' * name_width}-+-{'-' * rating_width}-+-{'-' * wins_width}-+-{'-' * losses_width}-+"

    print("\nPlayer ratings")
    print(border)
    print(
        f"| {'Player'.ljust(name_width)} | {'ELO'.rjust(rating_width)} | "
        f"{'Wins'.rjust(wins_width)} | {'Losses'.rjust(losses_width)} |"
    )
    print(border)
    for name, rating, wins, losses in rows:
        print(
            f"| {name.ljust(name_width)} | {str(rating).rjust(rating_width)} | "
            f"{str(wins).rjust(wins_width)} | {str(losses).rjust(losses_width)} |"
        )
    print(border)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual ELO maintenance: add backlog matches and/or rebuild ratings from full history."
    )
    parser.add_argument("--db-path", default=os.getenv("CHAMPS_DB_PATH", "/opt/random-champs/data/champs.db"))
    parser.add_argument("--input-file", help="Path to JSON payload for manual match ingestion")
    parser.add_argument("--players-file", help="Path to JSON payload for player mapping ingestion")
    parser.add_argument(
        "--set-mapping",
        nargs="+",
        action="append",
        metavar="VALUE",
        help="Set username -> real-name mapping. Optional third and fourth args are primary/secondary roles.",
    )
    parser.add_argument(
        "--set-preferred-role",
        nargs=2,
        action="append",
        metavar=("PLAYER", "ROLE"),
        help="Set preferred role for a username using their latest mapped name.",
    )
    parser.add_argument(
        "--recalculate",
        action="store_true",
        help="Rebuild all player ratings from full stored match history",
    )
    args = parser.parse_args()

    if not args.input_file and not args.players_file and not args.recalculate and not args.set_mapping and not args.set_preferred_role:
        raise ValueError(
            "Provide --input-file, --players-file, --recalculate, --set-mapping, --set-preferred-role, or a combination."
        )

    db.init_db(args.db_path)

    if args.set_mapping:
        for values in args.set_mapping:
            if len(values) not in (2, 3, 4):
                raise ValueError("--set-mapping requires PLAYER NAME [PRIMARY_ROLE] [SECONDARY_ROLE]")
            username, name = values[0], values[1]
            preferred_role = values[2] if len(values) >= 3 else None
            secondary_role = values[3] if len(values) == 4 else None
            db.set_player_mapping(args.db_path, username, name, preferred_role, secondary_role)
            if preferred_role and secondary_role:
                print(
                    f"Set mapping: {username} -> {name} "
                    f"(primary_role={preferred_role.upper()}, secondary_role={secondary_role.upper()})"
                )
            elif preferred_role:
                print(f"Set mapping: {username} -> {name} (primary_role={preferred_role.upper()})")
            else:
                print(f"Set mapping: {username} -> {name}")

    if args.set_preferred_role:
        for username, role in args.set_preferred_role:
            db.set_player_preferred_role(args.db_path, username, role)
            print(f"Set preferred role: {username} -> {role.upper()}")

    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        matches = _load_matches(payload)
        inserted, skipped = _insert_matches(args.db_path, matches)
        print(f"Inserted matches: {inserted}")
        print(f"Skipped matches: {skipped}")

    if args.players_file:
        with open(args.players_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        rows = _load_player_mappings(payload)
        for row in rows:
            db.set_player_mapping(
                args.db_path,
                row.username,
                row.name,
                row.primary_role,
                row.secondary_role,
            )
        print(f"Loaded player mappings: {len(rows)}")

    if args.recalculate:
        db.recalculate_all_ratings(args.db_path, refresh_mappings=True)
        print("Ratings recalculated from complete match history.")

    _print_ratings_table(args.db_path)


if __name__ == "__main__":
    main()
