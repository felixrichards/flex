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


async def handle_elo(ctx, args, db_path: str) -> None:
    if args and args[0].lower() in {"help", "--help", "-h"}:
        await ctx.send(HELP)
        return
    rows = db.get_elo_rows(db_path, list(args) if args else None)
    include_scale = bool(args)
    await ctx.send(
        format_elo_rows(
            rows,
            include_scale=include_scale,
            include_elo=False,
            short_headers=not bool(args),
            codeblock=True,
        )
    )
