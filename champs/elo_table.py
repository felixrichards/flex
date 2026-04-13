from __future__ import annotations

from champs.db.db import EloRow


def format_elo_rows(
    rows: list[EloRow],
    *,
    include_scale: bool,
    include_elo: bool = True,
    short_headers: bool = True,
    codeblock: bool = True,
) -> str:
    if not rows:
        return "No matching players found."

    rank_header = "#" if short_headers else "Rank"
    player_header = "P" if short_headers else "Player"
    cp_header = "CP"
    elo_header = "E" if short_headers else "ELO"
    wins_header = "W" if short_headers else "Wins"
    losses_header = "L" if short_headers else "Losses"
    dodges_header = "D" if short_headers else "Dodges"
    scale_header = "S" if short_headers else "Scale"

    rank_width = max(len(rank_header), *(len(str(row.rank)) for row in rows))
    player_width = max(len(player_header), *(len(row.player) for row in rows))
    cp_width = max(len(cp_header), *(len(str(row.cp)) for row in rows))
    elo_width = max(len(elo_header), *(len(str(row.elo)) for row in rows))
    wins_width = max(len(wins_header), *(len(str(row.wins)) for row in rows))
    losses_width = max(len(losses_header), *(len(str(row.losses)) for row in rows))
    dodges_width = max(len(dodges_header), *(len(str(row.dodges)) for row in rows))

    if include_scale:
        scale_values = [f"{row.dodge_scale:.2f}" for row in rows]
        scale_width = max(len(scale_header), *(len(value) for value in scale_values))
    else:
        scale_values = []
        scale_width = 0

    header = (
        f"{rank_header.rjust(rank_width)} {player_header.ljust(player_width)} {cp_header.rjust(cp_width)} "
        f"{wins_header.rjust(wins_width)} {losses_header.rjust(losses_width)} {dodges_header.rjust(dodges_width)}"
    )
    if include_elo:
        header = (
            f"{rank_header.rjust(rank_width)} {player_header.ljust(player_width)} {cp_header.rjust(cp_width)} "
            f"{elo_header.rjust(elo_width)} {wins_header.rjust(wins_width)} "
            f"{losses_header.rjust(losses_width)} {dodges_header.rjust(dodges_width)}"
        )
    if include_scale:
        header += f" {scale_header.rjust(scale_width)}"

    lines = [header]
    for idx, row in enumerate(rows):
        line = (
            f"{str(row.rank).rjust(rank_width)} {row.player.ljust(player_width)} {str(row.cp).rjust(cp_width)} "
            f"{str(row.wins).rjust(wins_width)} {str(row.losses).rjust(losses_width)} {str(row.dodges).rjust(dodges_width)}"
        )
        if include_elo:
            line = (
                f"{str(row.rank).rjust(rank_width)} {row.player.ljust(player_width)} {str(row.cp).rjust(cp_width)} "
                f"{str(row.elo).rjust(elo_width)} {str(row.wins).rjust(wins_width)} "
                f"{str(row.losses).rjust(losses_width)} {str(row.dodges).rjust(dodges_width)}"
            )
        if include_scale:
            line += f" {scale_values[idx].rjust(scale_width)}"
        lines.append(line)

    rendered = "\n".join(lines)
    if not codeblock:
        return rendered
    return f"```text\n{rendered}\n```"
