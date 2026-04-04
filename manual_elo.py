from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from champs.db import db
from champs.db.models import MatchPlayerRecord, MatchRecord, PlayerRecord
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


def _ensure_players_exist(db_path: str, names: Iterable[str]) -> int:
    engine = db._engine(db_path)
    unique_names = sorted({name.strip() for name in names if name and name.strip()}, key=str.casefold)
    if not unique_names:
        return 0

    with Session(engine) as session:
        existing_names = set(session.scalars(select(PlayerRecord.name)).all())
        added = 0
        for name in unique_names:
            if name in existing_names:
                continue
            session.add(PlayerRecord(name=name, rating=db.INITIAL_RATING))
            added += 1
        session.commit()
    return added


def _reset_history_and_ratings(db_path: str, *, reset_ratings: bool = True) -> tuple[int, int, int]:
    engine = db._engine(db_path)
    with Session(engine) as session:
        match_row_count = len(session.scalars(select(MatchPlayerRecord.id)).all())
        match_count = len(session.scalars(select(MatchRecord.checksum)).all())
        player_rows = session.scalars(select(PlayerRecord)).all()

        session.execute(delete(MatchPlayerRecord))
        session.execute(delete(MatchRecord))
        if reset_ratings:
            for player in player_rows:
                player.rating = db.INITIAL_RATING
        session.commit()
    return match_count, match_row_count, len(player_rows)


def _soft_reset_ratings(db_path: str, factor: float, target: int) -> tuple[int, float]:
    if not (0.0 <= factor <= 1.0):
        raise ValueError("Soft reset factor must be between 0.0 and 1.0.")

    engine = db._engine(db_path)
    with Session(engine) as session:
        players = session.scalars(select(PlayerRecord)).all()
        if not players:
            return 0, 0.0

        total_delta = 0.0
        for player in players:
            old_rating = float(player.rating)
            new_rating = float(target) + float(factor) * (old_rating - float(target))
            rounded = int(round(new_rating))
            total_delta += abs(old_rating - rounded)
            player.rating = rounded
        session.commit()
    return len(players), total_delta


def _backup_db_file(db_path: str) -> str:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB file not found for backup: {db_path}")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = f"{db_path}.backup-{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


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


def _get_player_mapping_rows(db_path: str) -> list[tuple[str, str, str, str, str]]:
    rows = db.get_player_mapping_overview_rows(db_path)
    return [
        (
            row.name,
            ", ".join(row.usernames),
            row.primary_role or "-",
            row.secondary_role or "-",
            ", ".join(row.discord_user_ids) if row.discord_user_ids else "-",
        )
        for row in rows
    ]


def _print_player_mappings_table(db_path: str) -> None:
    rows = _get_player_mapping_rows(db_path)
    if not rows:
        print("No player mappings found in DB.")
        return

    name_width = max(len("Name"), *(len(name) for name, _, _, _, _ in rows))
    usernames_width = max(len("Usernames"), *(len(usernames) for _, usernames, _, _, _ in rows))
    primary_width = max(len("Primary"), *(len(primary) for _, _, primary, _, _ in rows))
    secondary_width = max(len("Secondary"), *(len(secondary) for _, _, _, secondary, _ in rows))
    discord_width = max(len("Discord IDs"), *(len(discord_ids) for _, _, _, _, discord_ids in rows))
    border = (
        f"+-{'-' * name_width}-+-{'-' * usernames_width}-+-{'-' * primary_width}-"
        f"+-{'-' * secondary_width}-+-{'-' * discord_width}-+"
    )

    print("\nPlayer mappings")
    print(border)
    print(
        f"| {'Name'.ljust(name_width)} | {'Usernames'.ljust(usernames_width)} | "
        f"{'Primary'.ljust(primary_width)} | {'Secondary'.ljust(secondary_width)} | "
        f"{'Discord IDs'.ljust(discord_width)} |"
    )
    print(border)
    for name, usernames, primary, secondary, discord_ids in rows:
        print(
            f"| {name.ljust(name_width)} | {usernames.ljust(usernames_width)} | "
            f"{primary.ljust(primary_width)} | {secondary.ljust(secondary_width)} | "
            f"{discord_ids.ljust(discord_width)} |"
        )
    print(border)


def _should_print_ratings(args) -> bool:
    return bool(
        args.input_file
        or args.players_file
        or args.recalculate
        or args.reset_history
        or args.soft_reset
        or args.set_mapping
        or args.set_preferred_role
    )


def _should_print_player_mappings(args) -> bool:
    return bool(args.show_player_mappings or args.players_file)


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
    parser.add_argument(
        "--reset-history",
        action="store_true",
        help="Delete all stored match history and reset all existing player ELO ratings to initial value.",
    )
    parser.add_argument(
        "--soft-reset",
        action="store_true",
        help="Compress current player ratings towards a target while preserving relative ordering.",
    )
    parser.add_argument(
        "--soft-reset-factor",
        type=float,
        default=0.2,
        help="Compression factor for --soft-reset (0.0..1.0). Example: 0.2 moves 1100->1020 and 900->980.",
    )
    parser.add_argument(
        "--soft-reset-target",
        type=int,
        default=db.INITIAL_RATING,
        help="Target rating used by --soft-reset (default: 1000).",
    )
    parser.add_argument(
        "--show-player-mappings",
        action="store_true",
        help="Show actual names, associated usernames, and preferred roles.",
    )
    args = parser.parse_args()

    if (
        not args.input_file
        and not args.players_file
        and not args.recalculate
        and not args.reset_history
        and not args.soft_reset
        and not args.set_mapping
        and not args.set_preferred_role
        and not args.show_player_mappings
    ):
        raise ValueError(
            "Provide --input-file, --players-file, --recalculate, --set-mapping, "
            "--set-preferred-role, --reset-history, --soft-reset, --show-player-mappings, or a combination."
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

    if args.reset_history or args.soft_reset:
        backup_path = _backup_db_file(args.db_path)
        print(f"Created DB backup: {backup_path}")

    if args.soft_reset:
        updated_players, total_delta = _soft_reset_ratings(
            args.db_path,
            factor=args.soft_reset_factor,
            target=args.soft_reset_target,
        )
        print(
            f"Soft reset applied to {updated_players} player(s). "
            f"factor={args.soft_reset_factor:.3f}, target={args.soft_reset_target}, total_elo_shift={total_delta:.0f}"
        )

    if args.reset_history:
        preserve_compressed_ratings = bool(args.soft_reset)
        deleted_matches, deleted_match_rows, reset_players = _reset_history_and_ratings(
            args.db_path,
            reset_ratings=not preserve_compressed_ratings,
        )
        print(f"Deleted matches: {deleted_matches}")
        print(f"Deleted match rows: {deleted_match_rows}")
        if preserve_compressed_ratings:
            print(f"Preserved current player ratings after history reset: {reset_players}")
        else:
            print(f"Reset player ratings: {reset_players}")

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
        added_players = _ensure_players_exist(args.db_path, (row.name for row in rows))
        print(f"Loaded player mappings: {len(rows)}")
        print(f"Added players: {added_players}")

    if args.recalculate:
        db.recalculate_all_ratings(args.db_path, refresh_mappings=True)
        print("Ratings recalculated from complete match history.")

    if _should_print_player_mappings(args):
        _print_player_mappings_table(args.db_path)

    if _should_print_ratings(args):
        _print_ratings_table(args.db_path)


if __name__ == "__main__":
    main()
