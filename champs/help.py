GET_USAGE_BODY = """After the command, write the desired number of champs to get a random selection of champs even across roles.
If no number is given, 40 are returned.
You can also add filters, e.g. role, class. For example: champsget 3 assassin jungle.
"""

GET_HELP = "`champsget`\n\n" + GET_USAGE_BODY

MATCH_HELP = """`champsmatch` commands:

- `champsmatch`
  Attach a scoreboard image to parse and review.

- `champsmatch delete`
  Attach a scoreboard image to delete the matching match from history.

- `champsmatch help`
  Show this help."""

PLAYER_HELP = """`champsplayer` commands:

- `champsplayer add <username> <name> [primary_role] [secondary_role]`
  Add a username -> name mapping, optionally scoped by roles.
  Example: `champsplayer add MaBalls Felix adc top`

- `champsplayer delete <username> <name>`
  Delete username -> name mapping rows for that pair.

- `champsplayer view <player_or_username ...>`
  Show role mappings table (name, usernames, roles, linked Discord IDs) for specified players.

- `champsplayer linkdiscord <player_or_username> [@discord_user_or_id]`
  Link a Discord user to a player for voice-based draft detection.
  If no user is provided, links the command caller.

- `champsplayer help`
  Show this help.

You can also use `champshelp player`."""

ELO_HELP = """`champselo` usage:

- `champselo`
  Show full ELO table.

- `champselo <player_or_username ...>`
  Show filtered rows for specific players/usernames.

- `champselo help`
  Show this help."""

DRAFT_HELP = """`champsdraft` usage:

- `champsdraft`
  Use players currently in voice channels.

- `champsdraft <player_or_username> ...`
  Use an explicit player list (must resolve to 10 players).

- `champsdraft [<player_or_username> ...] [+player ...] [-player ...]`
  `+` opts a player in and `-` opts a player out.
  If no explicit list is provided, voice-channel players are used as the base.
"""

FEARLESS_HELP = """`champsfearless` commands:

- `champsfearless enable`
  Enable fearless tracking in this channel.

- `champsfearless disable`
  Disable fearless tracking in this channel.

- `champsfearless reset`
  Clear match history and bans for this channel.

- `champsfearless status`
  Show current fearless state for this channel.

- `champsfearless list`
  Show all currently banned champions.

- `champsfearless add <champion[, champion...]>`
  Manually add one or more champions to bans.

- `champsfearless remove <champion[, champion...]>`
  Remove one or more champions from bans.

- `champsfearless override <champion[, champion...]>`
  Replace the full ban list (empty argument clears all bans).

- `champsfearless help`
  Show this help."""

GENERAL_HELP = """`champshelp` usage:

- `champshelp`
  Show available commands.

- `champshelp <command>`
  Show detailed help for a command.

Commands:
- `get`: random champion generation
- `match`: parse/save/delete scoreboard matches
- `player`: manage player mappings + Discord links
- `elo`: show ELO leaderboard
- `draft`: build balanced teams
- `fearless`: manage fearless bans/session state
- `help`: this help command

Note: a **command** is top-level (for example `get`).
A **subcommand** is inside a command (for example `player add`)."""

HELP_HELP = """`champshelp` usage:

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
    "elo": ELO_HELP,
    "draft": DRAFT_HELP,
    "fearless": FEARLESS_HELP,
    "help": HELP_HELP,
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
