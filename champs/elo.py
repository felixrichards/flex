from champs.db import db


def _format_elo_table(rows) -> str:
    if not rows:
        return "No matching players found."

    rank_width = max(len("Rank"), *(len(str(row.rank)) for row in rows))
    player_width = max(len("Player"), *(len(row.player) for row in rows))
    elo_width = max(len("ELO"), *(len(str(row.elo)) for row in rows))
    wins_width = max(len("Wins"), *(len(str(row.wins)) for row in rows))
    losses_width = max(len("Losses"), *(len(str(row.losses)) for row in rows))

    border = (
        f"+-{'-' * rank_width}-+-{'-' * player_width}-+-{'-' * elo_width}-"
        f"+-{'-' * wins_width}-+-{'-' * losses_width}-+"
    )

    lines = [
        border,
        (
            f"| {'Rank'.rjust(rank_width)} | {'Player'.ljust(player_width)} | "
            f"{'ELO'.rjust(elo_width)} | {'Wins'.rjust(wins_width)} | {'Losses'.rjust(losses_width)} |"
        ),
        border,
    ]
    for row in rows:
        lines.append(
            f"| {str(row.rank).rjust(rank_width)} | {row.player.ljust(player_width)} | "
            f"{str(row.elo).rjust(elo_width)} | {str(row.wins).rjust(wins_width)} | {str(row.losses).rjust(losses_width)} |"
        )
    lines.append(border)
    return "```text\n" + "\n".join(lines) + "\n```"


async def handle_elo(ctx, args, db_path: str) -> None:
    rows = db.get_elo_rows(db_path, list(args) if args else None)
    await ctx.send(_format_elo_table(rows))
