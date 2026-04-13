from __future__ import annotations

import argparse
import os

from champs.constants import Privilege, privilege_name
from champs.db import db


def _print_players(db_path: str) -> None:
    rows = db.get_elo_rows(db_path)
    if not rows:
        print("No players found.")
        return

    print("Player privileges")
    printed: set[str] = set()
    for row in rows:
        if row.player in printed:
            continue
        printed.add(row.player)
        priv = db.get_player_privilege(db_path, row.player)
        print(f"- {row.player}: {privilege_name(priv)} ({priv})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual player administration.")
    parser.add_argument("--db-path", default=os.getenv("CHAMPS_DB_PATH", "/opt/random-champs/data/champs.db"))
    parser.add_argument(
        "--set-privilege",
        nargs=2,
        action="append",
        metavar=("PLAYER", "PRIV"),
        help="Set player privilege. PRIV must be one of 0(player), 1(operator), 2(admin), 3(superadmin).",
    )
    parser.add_argument("--show", action="store_true", help="Show current player privileges.")
    args = parser.parse_args()

    if not args.set_privilege and not args.show:
        raise ValueError("Provide --set-privilege PLAYER PRIV and/or --show")

    db.init_db(args.db_path)

    if args.set_privilege:
        for identifier, raw_priv in args.set_privilege:
            privilege = int(raw_priv)
            if privilege not in {int(level) for level in Privilege}:
                raise ValueError("PRIV must be one of 0,1,2,3")
            resolved_name = db.set_player_privilege(args.db_path, identifier, privilege)
            print(f"Set privilege: {resolved_name} -> {privilege_name(privilege)} ({privilege})")

    if args.show:
        _print_players(args.db_path)


if __name__ == "__main__":
    main()
