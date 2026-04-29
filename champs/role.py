import asyncio

from champs.db import db

HELP = """`champsrole` usage:

- `champsrole <mainrole> [<secondaryrole>]`
  Set your player roles using your linked Discord account.
  You must already be linked with `champsplayer linkdiscord`.
  Example: `champsrole mid bot`"""


async def handle_role(ctx, args, db_path: str) -> None:
    if not args or args[0].lower() in {"help", "--help", "-h"}:
        await ctx.send(HELP)
        return

    primary_role = args[0].strip()
    secondary_role = args[1].strip() if len(args) > 1 else None

    linked_player = await asyncio.to_thread(db.get_discord_linked_player_name, db_path, ctx.author.id)
    if linked_player is None:
        await ctx.send("Your Discord account is not linked to a player. Use `champsplayer linkdiscord` first.")
        return

    try:
        resolved_name = await asyncio.to_thread(
            db.set_player_roles,
            db_path,
            linked_player,
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
