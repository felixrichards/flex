import asyncio
import re

from champs.constants import Privilege
from champs.db import db

HELP = """`champsrole` usage:

- `champsrole <mainrole> [<secondaryrole>]`
  Set your player roles using your linked Discord account.
  You must already be linked with `champsplayer linkdiscord`.
  Example: `champsrole mid bot`

- `champsrole @discord_user <mainrole> [<secondaryrole>]`
- `champsrole <mainrole> [<secondaryrole>] @discord_user`
  Set roles for another linked player (admin-only)."""


def _parse_mention_user_id(token: str) -> int | None:
    token = token.strip()
    match = re.fullmatch(r"<@!?(\d+)>", token)
    if not match:
        return None
    return int(match.group(1))


async def handle_role(ctx, args, db_path: str) -> None:
    if not args or args[0].lower() in {"help", "--help", "-h"}:
        await ctx.send(HELP)
        return

    tokens = [arg.strip() for arg in args if arg.strip()]
    mention_user_id: int | None = None
    if tokens:
        leading_mention = _parse_mention_user_id(tokens[0])
        trailing_mention = _parse_mention_user_id(tokens[-1])
        if leading_mention is not None and trailing_mention is not None and len(tokens) > 1:
            await ctx.send("Use only one mention, either at the start or end of `champsrole`.")
            return
        if leading_mention is not None:
            mention_user_id = leading_mention
            tokens = tokens[1:]
        elif trailing_mention is not None:
            mention_user_id = trailing_mention
            tokens = tokens[:-1]

    if not tokens or len(tokens) > 2:
        await ctx.send(HELP)
        return

    primary_role = tokens[0]
    secondary_role = tokens[1] if len(tokens) > 1 else None

    actor_linked_player = await asyncio.to_thread(db.get_discord_linked_player_name, db_path, ctx.author.id)
    if actor_linked_player is None:
        await ctx.send("Your Discord account is not linked to a player. Use `champsplayer linkdiscord` first.")
        return

    target_discord_user_id = mention_user_id if mention_user_id is not None else int(ctx.author.id)
    if mention_user_id is not None:
        actor_privilege = await asyncio.to_thread(db.get_discord_user_privilege, db_path, ctx.author.id)
        if actor_privilege < int(Privilege.ADMIN):
            await ctx.send("Only admins can set roles for other players.")
            return

    target_player = await asyncio.to_thread(db.get_discord_linked_player_name, db_path, target_discord_user_id)
    if target_player is None:
        await ctx.send("Target Discord user is not linked to a player. Use `champsplayer linkdiscord` first.")
        return

    try:
        resolved_name = await asyncio.to_thread(
            db.set_player_roles,
            db_path,
            target_player,
            primary_role,
            secondary_role,
        )
    except Exception as exc:
        await ctx.send(f"Could not set roles: {exc}")
        return

    if secondary_role:
        await ctx.send(f"Updated `{resolved_name}` roles to `{primary_role}`/`{secondary_role}`.")
        return
    await ctx.send(f"Updated `{resolved_name}` main role to `{primary_role}`.")
