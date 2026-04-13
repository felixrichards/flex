import asyncio

from champs.constants import DODGE_PENALTY, Privilege
from champs.db import db

HELP = """`champsforcedodge` usage:

- `champsforcedodge <player_or_username> [dodges]`
  Apply manual dodge penalties for a player.
  `dodges` defaults to `1`.
  Positive values apply penalties; negative values undo recent dodge penalties exactly.

Rules:
- Caller must be a linked admin or superadmin (privilege >= 2).
- Penalty base per dodge is `10` CP, scaled by dodge history and games played."""


async def handle_forcedodge(ctx, args, db_path: str) -> None:
    if args and args[0].lower() in {"help", "--help", "-h"}:
        await ctx.send(HELP)
        return

    if not args:
        await ctx.send("Usage: `champsforcedodge <player_or_username> [dodges]`")
        return

    caller_priv = await asyncio.to_thread(db.get_discord_user_privilege, db_path, ctx.author.id)
    if caller_priv < int(Privilege.ADMIN):
        await ctx.send("Only admins can use `champsforcedodge`.")
        return

    identifier = args[0].strip()
    count = 1
    if len(args) >= 2:
        try:
            count = int(args[1])
        except ValueError:
            await ctx.send("`dodges` must be an integer.")
            return
    if count == 0:
        await ctx.send("`dodges` cannot be zero.")
        return

    resolved_name = await asyncio.to_thread(db.resolve_player_identifier, db_path, identifier)
    if resolved_name is None:
        await ctx.send(f"Unknown player: `{identifier}`")
        return

    if count > 0:
        penalties: list[int] = []
        for _ in range(count):
            penalty = await asyncio.to_thread(
                db.apply_dodge_penalty,
                db_path,
                resolved_name,
                float(DODGE_PENALTY),
                source="forcedodge",
                channel_id=getattr(getattr(ctx, "channel", None), "id", None),
            )
            penalties.append(penalty)
        total = sum(penalties)
        await ctx.send(
            f"Applied {count} forced dodge(s) to `{resolved_name}`. Total CP change: `-{total}` "
            f"({', '.join(str(value) for value in penalties)})."
        )
        return

    undo_count = abs(count)
    try:
        restored = await asyncio.to_thread(db.undo_recent_dodge_penalties, db_path, resolved_name, undo_count)
    except Exception as exc:
        await ctx.send(f"Could not undo dodge(s): {exc}")
        return

    await ctx.send(
        f"Undid {undo_count} dodge(s) for `{resolved_name}`. Total CP restored: `+{restored}`."
    )
