from champs.draft import HELP as DRAFT_HELP
from champs.elo import HELP as ELO_HELP
from champs.fearless import HELP as FEARLESS_HELP
from champs.forcedodge import HELP as FORCEDODGE_HELP
from champs.get import HELP as GET_HELP
from champs.match import HELP as MATCH_HELP
from champs.player import HELP as PLAYER_HELP
from champs.role import HELP as ROLE_HELP

GENERAL_HELP = """`champshelp` usage:

- `champshelp`
  Show available commands.

- `champshelp <command>`
  Show detailed help for a command.

Commands:
- `get`: random champion generation
- `match`: parse/save/delete scoreboard matches
- `player`: manage player mappings + Discord links
- `role`: set your own linked player roles
- `elo`: show ELO leaderboard
- `draft`: build balanced teams
- `dodge`: submit a dodge for current draft
- `forcedodge`: admin dodge penalty override
- `fearless`: manage fearless bans/session state
- `help`: this help command

Note: a **command** is top-level (for example `get`).
A **subcommand** is inside a command (for example `player add`)."""

HELP = """`champshelp` usage:

- `champshelp`
  Show available commands and command/subcommand explanation.

- `champshelp <command>`
  Show detailed help for one command.

Examples:
- `champshelp get`
- `champshelp player`
- `champshelp fearless`"""

COMMAND_HELP = {
    "get": GET_HELP,
    "match": MATCH_HELP,
    "player": PLAYER_HELP,
    "role": ROLE_HELP,
    "elo": ELO_HELP,
    "draft": DRAFT_HELP,
    "dodge": "Use `/dodge` for ephemeral dodge submissions, or `champsdodge` (DM confirmation).",
    "forcedodge": FORCEDODGE_HELP,
    "fearless": FEARLESS_HELP,
    "help": HELP,
}


def _normalise_command_token(raw: str) -> str:
    token = raw.strip().lower()
    if token.startswith("champs"):
        token = token[len("champs") :]
    return token


async def handle_help(ctx, args) -> None:
    if not args:
        await ctx.send(GENERAL_HELP)
        return

    command = _normalise_command_token(args[0])
    help_text = COMMAND_HELP.get(command)
    if help_text is None:
        await ctx.send(f"Unknown command `{args[0]}`. Use `champshelp` to see available commands.")
        return

    await ctx.send(help_text)
