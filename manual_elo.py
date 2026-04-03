from __future__ import annotations

import argparse
import json
import os
from typing import Iterable

from champs import db
from champs.payloads import Match


def _load_matches(payload: object) -> list[Match]:
    if isinstance(payload, dict) and "matches" in payload:
        payload = payload["matches"]
    if isinstance(payload, dict):
        return [Match.model_validate(payload)]
    if isinstance(payload, list):
        return [Match.model_validate(item) for item in payload]
    raise ValueError("Payload must be a Match object, a list of matches, or {'matches': [...]} shape.")


def _insert_matches(db_path: str, matches: Iterable[Match]) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    for match in matches:
        if db.insert_match(db_path, match):
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual ELO maintenance: add backlog matches and/or rebuild ratings from full history."
    )
    parser.add_argument("--db-path", default=os.getenv("CHAMPS_DB_PATH", "/opt/random-champs/data/champs.db"))
    parser.add_argument("--input-file", help="Path to JSON payload for manual match ingestion")
    parser.add_argument(
        "--recalculate",
        action="store_true",
        help="Rebuild all player ratings from full stored match history",
    )
    args = parser.parse_args()

    if not args.input_file and not args.recalculate:
        raise ValueError("Provide --input-file, --recalculate, or both.")

    db.init_db(args.db_path)

    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        matches = _load_matches(payload)
        inserted, skipped = _insert_matches(args.db_path, matches)
        print(f"Inserted matches: {inserted}")
        print(f"Skipped matches: {skipped}")

    if args.recalculate:
        db.recalculate_all_ratings(args.db_path)
        print("Ratings recalculated from complete match history.")


if __name__ == "__main__":
    main()
