import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone

import discord

from champs.common.json_payload import extract_json_payload
from champs.db import db
from champs.discord_views import ParseFeedbackView
from champs import fearless
from champs.payloads.match import Match
from champs.scoreboard import scoreboard_cv


MATCH_HELP = """`champsmatch` commands:

- `champsmatch`
  Attach a scoreboard image to parse and review.

- `champsmatch delete`
  Attach a scoreboard image to delete the matching match from history.

- `champsmatch help`
  Show this help."""


PENDING_MATCHES: dict[int, Match] = {}


def _format_scoreboard_message(match: Match) -> str:
    def row_text(row):
        name = row.name or row.player
        identity = f"{row.player} ({name})" if name else row.player
        return f"- {identity}: {row.champion} {row.kda}"

    win_rows = "\n".join(row_text(row) for row in match.win)
    lose_rows = "\n".join(row_text(row) for row in match.lose)
    return f"**Win**\n{win_rows}\n\n**Lose**\n{lose_rows}"


def _format_correction_payload(match: Match) -> str:
    payload = match.model_dump(mode="json", exclude={"timestamp", "checksum"})
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _parse_match_payload(payload) -> Match | None:
    try:
        return Match.model_validate(payload)
    except Exception:
        return None


async def _store_match_from_message(interaction: discord.Interaction, db_path: str) -> None:
    match = PENDING_MATCHES.get(interaction.message.id)
    if match is None:
        await interaction.followup.send("No pending parsed match found for this message.", ephemeral=True)
        return
    inserted, response = await _save_match_to_db(db_path, match, channel_id=interaction.channel.id if interaction.channel else None)
    if inserted:
        PENDING_MATCHES.pop(interaction.message.id, None)
    await interaction.followup.send(response, ephemeral=True)


async def _save_match_to_db(db_path: str, match: Match, channel_id: int | None = None) -> tuple[bool, str]:
    stamped = match.model_copy(update={"timestamp": datetime.now(timezone.utc)})
    inserted = await asyncio.to_thread(db.insert_match, db_path, stamped)
    if not inserted:
        return False, "Match already stored."

    fearless_message = ""
    if channel_id is not None:
        champions = [row.champion for row in stamped.win + stamped.lose]
        _, fearless_message = fearless.record_match_champions(channel_id, champions)
    response = "Saved to match history."
    if fearless_message:
        response = f"{response}\n{fearless_message}"
    return True, response


async def _append_correction_prompt(interaction: discord.Interaction) -> str:
    match = PENDING_MATCHES.get(interaction.message.id)
    if match is None:
        return "Reply with corrected JSON if needed."
    payload = _format_correction_payload(match)
    return (
        "Please correct the JSON below and reply to this message with the updated JSON.\n"
        "```json\n"
        f"{payload}\n"
        "```"
    )


async def _read_attachment_to_match(ctx) -> Match | None:
    if not ctx.message.attachments:
        return None

    attachment = ctx.message.attachments[0]
    try:
        payload = await attachment.read()
    except Exception as exc:
        await ctx.send(f"Could not read attachment: {exc}")
        return None

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name

    try:
        result = await asyncio.to_thread(scoreboard_cv.detect_post_match, tmp_path)
    except Exception as exc:
        await ctx.send(f"Scoreboard parse failed: {exc}")
        return None
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return Match.model_validate(result)


async def _read_attachment_to_display_match(ctx, db_path: str) -> Match | None:
    raw_match = await _read_attachment_to_match(ctx)
    if raw_match is None:
        return None
    return await asyncio.to_thread(db.resolve_match_names, db_path, raw_match)


async def _handle_match_help(ctx) -> None:
    await ctx.send(MATCH_HELP)


async def _handle_match_delete(ctx, db_path: str) -> None:
    if not ctx.message.attachments:
        await ctx.send("Attach a scoreboard image and run `champsmatch delete`.")
        return
    match = await _read_attachment_to_match(ctx)
    if match is None:
        return
    deleted = await asyncio.to_thread(db.delete_match, db_path, match.checksum or "")
    if deleted:
        await ctx.send("Deleted match from history.")
    else:
        await ctx.send("No matching match found in history.")


async def _handle_match_parse(ctx, db_path: str) -> None:
    if not ctx.message.attachments:
        await ctx.send("Attach a scoreboard image and run `champsmatch`.")
        return

    match = await _read_attachment_to_display_match(ctx, db_path)
    if match is None:
        return

    async def on_confirm(interaction: discord.Interaction) -> None:
        await _store_match_from_message(interaction, db_path)

    view = ParseFeedbackView(
        requester_id=ctx.author.id,
        on_confirm=on_confirm,
        on_wrong=_append_correction_prompt,
    )
    message = await ctx.send(_format_scoreboard_message(match), view=view)
    view.message = message
    PENDING_MATCHES[message.id] = match


async def handle_match(ctx, args, db_path: str) -> None:
    subcommand = args[0].lower() if args else "parse"
    if subcommand == "help":
        await _handle_match_help(ctx)
        return
    if subcommand == "delete":
        await _handle_match_delete(ctx, db_path)
        return
    if subcommand != "parse":
        await _handle_match_help(ctx)
        return
    await _handle_match_parse(ctx, db_path)


async def handle_on_message(message: discord.Message, bot, db_path: str) -> bool:
    if message.author.bot:
        return True

    if message.reference and message.reference.resolved:
        referenced = message.reference.resolved
        if isinstance(referenced, discord.Message) and referenced.author == bot.user:
            payload = extract_json_payload(message.content)
            if payload is None:
                return False
            match = _parse_match_payload(payload)
            if match is None:
                await message.channel.send("Scoreboard JSON not recognized. Expect win/lose arrays of 5 rows each.")
                return True
            match = await asyncio.to_thread(db.resolve_match_names, db_path, match)
            PENDING_MATCHES[referenced.id] = match
            await referenced.edit(content=_format_scoreboard_message(match))
            inserted, response = await _save_match_to_db(
                db_path,
                match,
                channel_id=message.channel.id if message.channel else None,
            )
            if inserted:
                PENDING_MATCHES.pop(referenced.id, None)
                await message.channel.send(f"Updated and saved.\n{response}")
            else:
                await message.channel.send(f"Updated.\n{response}")
            return True
    return False
