import asyncio

from champs.db import db

PLAYER_HELP = """`champsplayer` commands:

- `champsplayer add <username> <name> [primary_role] [secondary_role]`
  Add a username -> name mapping, optionally scoped by roles.
  Example: `champsplayer add MaBalls Felix adc top`

- `champsplayer delete <username> <name>`
  Delete username -> name mapping rows for that pair.

- `champsplayer view <player_or_username ...>`
  Show role mappings table (name, usernames, roles, linked Discord IDs) for specified players.

- `champsplayer help`
  Show this help."""


def _format_player_mapping_table(rows) -> str:
    if not rows:
        return "No player mappings found."

    name_width = max(len("Name"), *(len(row.name) for row in rows))
    usernames_width = max(len("Usernames"), *(len(", ".join(row.usernames)) for row in rows))
    primary_width = max(len("Primary"), *(len(row.primary_role or "-") for row in rows))
    secondary_width = max(len("Secondary"), *(len(row.secondary_role or "-") for row in rows))
    discord_width = max(len("Discord IDs"), *(len(", ".join(row.discord_user_ids) or "-") for row in rows))

    border = (
        f"+-{'-' * name_width}-+-{'-' * usernames_width}-+-{'-' * primary_width}-"
        f"+-{'-' * secondary_width}-+-{'-' * discord_width}-+"
    )
    lines = [
        border,
        (
            f"| {'Name'.ljust(name_width)} | {'Usernames'.ljust(usernames_width)} | "
            f"{'Primary'.ljust(primary_width)} | {'Secondary'.ljust(secondary_width)} | "
            f"{'Discord IDs'.ljust(discord_width)} |"
        ),
        border,
    ]
    for row in rows:
        usernames = ", ".join(row.usernames)
        discord_ids = ", ".join(row.discord_user_ids) if row.discord_user_ids else "-"
        lines.append(
            f"| {row.name.ljust(name_width)} | {usernames.ljust(usernames_width)} | "
            f"{(row.primary_role or '-').ljust(primary_width)} | {(row.secondary_role or '-').ljust(secondary_width)} | "
            f"{discord_ids.ljust(discord_width)} |"
        )
    lines.append(border)
    return "```text\n" + "\n".join(lines) + "\n```"


async def _handle_player_help(ctx) -> None:
    await ctx.send(PLAYER_HELP)


async def _handle_player_add(ctx, args, db_path: str) -> None:
    if len(args) < 2:
        await ctx.send("Usage: `champsplayer add <username> <name> [primary_role] [secondary_role]`")
        return
    username = args[0].strip()
    primary_role = args[-2] if len(args) >= 4 else (args[-1] if len(args) >= 3 else None)
    secondary_role = args[-1] if len(args) >= 4 else None
    if secondary_role:
        name = " ".join(args[1:-2]).strip()
    elif primary_role:
        name = " ".join(args[1:-1]).strip()
    else:
        name = " ".join(args[1:]).strip()
    if not name:
        await ctx.send("Usage: `champsplayer add <username> <name> [primary_role] [secondary_role]`")
        return
    try:
        await asyncio.to_thread(db.set_player_mapping, db_path, username, name, primary_role, secondary_role)
    except Exception as exc:
        if primary_role:
            fallback_name = " ".join(args[1:]).strip()
            if fallback_name:
                try:
                    await asyncio.to_thread(db.set_player_mapping, db_path, username, fallback_name, None)
                except Exception as fallback_exc:
                    await ctx.send(f"Could not save player mapping: {fallback_exc}")
                    return
                await ctx.send(f"Saved mapping: `{username}` -> `{fallback_name}`")
                return
        await ctx.send(f"Could not save player mapping: {exc}")
        return
    role_suffix = ""
    if primary_role and secondary_role:
        role_suffix = f" for roles `{primary_role}`/`{secondary_role}`"
    elif primary_role:
        role_suffix = f" for role `{primary_role}`"
    await ctx.send(f"Saved mapping: `{username}` -> `{name}`{role_suffix}")


async def _handle_player_delete(ctx, args, db_path: str) -> None:
    if len(args) < 2:
        await ctx.send("Usage: `champsplayer delete <username> <name>`")
        return

    username = args[0].strip()
    name = " ".join(args[1:]).strip()
    if not username or not name:
        await ctx.send("Usage: `champsplayer delete <username> <name>`")
        return

    try:
        deleted = await asyncio.to_thread(db.delete_player_mapping, db_path, username, name)
    except Exception as exc:
        await ctx.send(f"Could not delete player mapping: {exc}")
        return

    if deleted > 0:
        await ctx.send(f"Deleted {deleted} mapping row(s) for `{username}` -> `{name}`.")
    else:
        await ctx.send(f"No mapping rows found for `{username}` -> `{name}`.")


async def _handle_player_view(ctx, args, db_path: str) -> None:
    if not args:
        await ctx.send("Usage: `champsplayer view <player_or_username ...>`")
        return
    rows = await asyncio.to_thread(db.get_player_mapping_overview_rows, db_path, list(args))
    await ctx.send(_format_player_mapping_table(rows))


async def handle_player(ctx, args, db_path: str) -> None:
    subcommand = args[0].lower() if args else "help"
    if subcommand == "help":
        await _handle_player_help(ctx)
        return
    if subcommand == "add":
        await _handle_player_add(ctx, args[1:], db_path)
        return
    if subcommand == "delete":
        await _handle_player_delete(ctx, args[1:], db_path)
        return
    if subcommand == "view":
        await _handle_player_view(ctx, args[1:], db_path)
        return
    await _handle_player_help(ctx)
