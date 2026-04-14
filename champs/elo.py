from champs.db import db
from champs.elo_table import format_elo_rows

HELP = """`champselo` usage:

- `champselo`
  Show full ELO table.

- `champselo <player_or_username ...>`
  Show filtered rows for specific players/usernames.

Columns:
- `CP`: ranking points (affected by dodge penalties)
- `W`: wins
- `L`: losses
- `D`: dodges
- `S`: dodge penalty scale (only shown for filtered queries)."""


def _resolve_caller(db_path: str, ctx) -> tuple[str | None, bool]:
    caller_id = getattr(getattr(ctx, "author", None), "id", None)
    if caller_id is None:
        return None, False

    caller_name = db.get_discord_linked_player_name(db_path, caller_id)
    if caller_name is None:
        return None, False
    return caller_name.casefold(), db.is_player_private(db_path, caller_name)


def _filter_public_rows(rows) -> tuple[list, list]:
    visible_rows = []
    blocked_private_rows = []
    for row in rows:
        if not row.private:
            visible_rows.append(row)
        else:
            blocked_private_rows.append(row)
    return visible_rows, blocked_private_rows


def _filtered_empty_message(blocked_private_rows: list, args) -> str:
    if blocked_private_rows and len(args) == 1:
        return "That player's rank is private."
    return "No matching players found."


async def handle_elo(ctx, args, db_path: str) -> None:
    if args and args[0].lower() in {"help", "--help", "-h"}:
        await ctx.send(HELP)
        return

    caller_name_key, caller_is_private = _resolve_caller(db_path, ctx)
    if caller_name_key and caller_is_private:
        await ctx.send("Private players cannot use `champselo`.")
        return

    rows = db.get_elo_rows(db_path, list(args) if args else None)

    include_scale = bool(args)
    if args:
        visible_rows, blocked_private_rows = _filter_public_rows(rows)

        if not visible_rows:
            await ctx.send(_filtered_empty_message(blocked_private_rows, args))
            return

        rows = visible_rows

    await ctx.send(
        format_elo_rows(
            rows,
            include_scale=include_scale,
            include_rank=True,
            include_elo=False,
            short_headers=not bool(args),
            codeblock=True,
        )
    )
