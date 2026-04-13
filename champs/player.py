import asyncio
import re

from champs.constants import Privilege, privilege_name
from champs.db import db

HELP = """`champsplayer` commands:

- `champsplayer add <username> <name> [primary_role] [secondary_role]`
  Add a username -> name mapping, optionally scoped by roles.
  Example: `champsplayer add MaBalls Felix adc top`

- `champsplayer delete <name>`
  Delete a player from DB only if they have zero matches (removes mappings, Discord links, and player row).

- `champsplayer view <player_or_username ...>`
  Show role mappings table (name, usernames, roles, linked Discord IDs) for specified players.

- `champsplayer linkdiscord <player_or_username> [@discord_user_or_id]`
  Link a Discord user to a player for voice-based draft detection.
  If no user is provided, links the command caller.

- `champsplayer admin <player_or_username>`
  Set player privilege to admin (`2`).
  Only callable by a linked superadmin (`3`).

- `champsplayer private <player_or_username>`
  Toggle whether this player appears in unfiltered `champselo` output.

You can also use `champshelp player`."""


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
    await ctx.send(HELP)


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
    name = " ".join(args).strip()
    if not name:
        await ctx.send("Usage: `champsplayer delete <name>`")
        return

    try:
        result = await asyncio.to_thread(db.delete_player_completely, db_path, name)
    except Exception as exc:
        await ctx.send(f"Could not delete player: {exc}")
        return

    if result.associated_matches > 0 or result.associated_match_rows > 0:
        names = ", ".join(result.deleted_name_variants) if result.deleted_name_variants else name
        await ctx.send(
            f"Cannot delete `{names}` because they have recorded match history "
            f"({result.associated_match_rows} match row(s) across {result.associated_matches} match(es))."
        )
        return

    if (
        result.deleted_player_rows == 0
        and result.deleted_mapping_rows == 0
        and result.deleted_discord_rows == 0
    ):
        await ctx.send(f"No player found for `{name}`.")
        return

    names = ", ".join(result.deleted_name_variants) if result.deleted_name_variants else name
    await ctx.send(
        f"Deleted player `{names}`. "
        f"players={result.deleted_player_rows}, mappings={result.deleted_mapping_rows}, "
        f"discord_links={result.deleted_discord_rows}."
    )


async def _handle_player_view(ctx, args, db_path: str) -> None:
    if not args:
        await ctx.send("Usage: `champsplayer view <player_or_username ...>`")
        return
    rows = await asyncio.to_thread(db.get_player_mapping_overview_rows, db_path, list(args))
    await ctx.send(_format_player_mapping_table(rows))


def _parse_discord_user_id(token: str) -> int | None:
    stripped = token.strip()
    mention_match = re.fullmatch(r"<@!?(\d+)>", stripped)
    if mention_match:
        return int(mention_match.group(1))
    if stripped.isdigit():
        return int(stripped)
    return None


async def _handle_player_linkdiscord(ctx, args, db_path: str) -> None:
    if len(args) < 1:
        await ctx.send("Usage: `champsplayer linkdiscord <player_or_username> [@discord_user_or_id]`")
        return

    player_identifier = args[0].strip()
    if not player_identifier:
        await ctx.send("Usage: `champsplayer linkdiscord <player_or_username> [@discord_user_or_id]`")
        return

    discord_user_id: int | None = None
    if ctx.message.mentions:
        discord_user_id = int(ctx.message.mentions[0].id)
    elif len(args) >= 2:
        discord_user_id = _parse_discord_user_id(args[1])
        if discord_user_id is None:
            await ctx.send("Could not parse Discord user. Use a mention like `@user` or a numeric Discord user ID.")
            return
    else:
        discord_user_id = int(ctx.author.id)

    resolved_player_name = await asyncio.to_thread(db.resolve_player_identifier_for_link, db_path, player_identifier)
    if resolved_player_name is None:
        await ctx.send(
            f"Could not resolve `{player_identifier}` to a known player. "
            "Use `champsplayer add <username> <name> <primary_role> <secondary_role>` first."
        )
        return

    actor_privilege = await asyncio.to_thread(db.get_discord_user_privilege, db_path, ctx.author.id)
    existing_target = await asyncio.to_thread(db.get_discord_linked_player_name, db_path, discord_user_id)
    if (
        existing_target is not None
        and existing_target.casefold() != resolved_player_name.casefold()
        and actor_privilege < int(Privilege.ADMIN)
    ):
        await ctx.send("Only admins can remap a Discord user from one player to another.")
        return

    try:
        await asyncio.to_thread(db.set_discord_player_mapping, db_path, discord_user_id, resolved_player_name)
    except Exception as exc:
        await ctx.send(f"Could not save Discord mapping: {exc}")
        return

    await ctx.send(f"Linked Discord user `{discord_user_id}` -> player `{resolved_player_name}`")


async def _handle_player_admin(ctx, args, db_path: str) -> None:
    player_identifier = " ".join(args).strip()
    if not player_identifier:
        await ctx.send("Usage: `champsplayer admin <player_or_username>`")
        return

    caller_privilege = await asyncio.to_thread(db.get_discord_user_privilege, db_path, ctx.author.id)
    if caller_privilege < int(Privilege.SUPERADMIN):
        await ctx.send("Only superadmins can grant admin privilege.")
        return

    try:
        resolved_name = await asyncio.to_thread(
            db.set_player_privilege,
            db_path,
            player_identifier,
            int(Privilege.ADMIN),
        )
    except Exception as exc:
        await ctx.send(f"Could not grant admin privilege: {exc}")
        return

    await ctx.send(
        f"Updated `{resolved_name}` privilege to `{privilege_name(int(Privilege.ADMIN))}` ({int(Privilege.ADMIN)})."
    )


async def _handle_player_private(ctx, args, db_path: str) -> None:
    player_identifier = " ".join(args).strip()
    if not player_identifier:
        await ctx.send("Usage: `champsplayer private <caseinsensitive_player_or_casesensitive_username>`")
        return

    try:
        resolved_name, is_private = await asyncio.to_thread(db.toggle_player_private, db_path, player_identifier)
    except Exception as exc:
        await ctx.send(f"Could not toggle privacy: {exc}")
        return

    state_text = "hidden" if is_private else "visible"
    await ctx.send(
        f"`{resolved_name}` is now `{state_text}` in unfiltered `champselo` output."
    )


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
    if subcommand == "linkdiscord":
        await _handle_player_linkdiscord(ctx, args[1:], db_path)
        return
    if subcommand == "admin":
        await _handle_player_admin(ctx, args[1:], db_path)
        return
    if subcommand == "private":
        await _handle_player_private(ctx, args[1:], db_path)
        return
    await _handle_player_help(ctx)
