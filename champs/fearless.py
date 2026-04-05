from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from champs.common.utils import get_all_champs
from champs.payloads.fearless import FearlessMatch, FearlessState

FEARLESS_WINDOW = timedelta(hours=6)

ALL_CHAMPS = get_all_champs()
CHAMP_LOOKUP = {re.sub(r"[^a-z0-9]", "", champ.lower()): champ for champ in ALL_CHAMPS}

FEARLESS_BY_CHANNEL: dict[int, FearlessState] = {}

USAGE = """`champsfearless` commands:

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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_champ_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _resolve_champion(value: str) -> str | None:
    key = _normalise_champ_key(value.strip())
    if not key:
        return None
    return CHAMP_LOOKUP.get(key)


def _split_champion_input(raw_args: tuple[str, ...] | list[str]) -> list[str]:
    text = " ".join(raw_args).strip()
    if not text:
        return []
    if "," in text:
        return [chunk.strip() for chunk in text.split(",") if chunk.strip()]
    return [text]


def _parse_input_champions(raw_args: tuple[str, ...] | list[str]) -> tuple[list[str], list[str]]:
    resolved: list[str] = []
    unknown: list[str] = []
    for chunk in _split_champion_input(raw_args):
        champ = _resolve_champion(chunk)
        if champ is None:
            unknown.append(chunk)
            continue
        if champ not in resolved:
            resolved.append(champ)
    return resolved, unknown


def _state_remaining_window(state: FearlessState, now: datetime) -> timedelta | None:
    if state.start is None:
        return None
    remaining = FEARLESS_WINDOW - (now - state.start)
    if remaining.total_seconds() <= 0:
        return timedelta(seconds=0)
    return remaining


def _format_duration(duration: timedelta) -> str:
    total_seconds = int(duration.total_seconds())
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _apply_rollover(state: FearlessState, now: datetime) -> bool:
    if state.start is None:
        return False
    if now - state.start < FEARLESS_WINDOW:
        return False
    # Keep mode enabled but wait for the next recorded game to start a new window.
    state.start = None
    state.banned.clear()
    state.matches.clear()
    return True


def _get_state(channel_id: int, *, create: bool, now: datetime | None = None) -> FearlessState | None:
    now = now or _utc_now()
    state = FEARLESS_BY_CHANNEL.get(channel_id)
    if state is None and create:
        state = FearlessState()
        FEARLESS_BY_CHANNEL[channel_id] = state
    if state is not None:
        _apply_rollover(state, now)
    return state


def get_fearless_bans(channel_id: int, *, now: datetime | None = None) -> list[str]:
    state = _get_state(channel_id, create=False, now=now)
    if state is None or not state.enabled:
        return []
    return list(state.banned)


def record_match_champions(channel_id: int, champions: list[str], *, now: datetime | None = None) -> tuple[bool, str]:
    now = now or _utc_now()
    state = _get_state(channel_id, create=False, now=now)
    if state is None or not state.enabled:
        return False, ""

    resolved: list[str] = []
    unknown: list[str] = []
    for champ in champions:
        canonical = _resolve_champion(champ)
        if canonical is None:
            unknown.append(champ)
            continue
        if canonical not in resolved:
            resolved.append(canonical)

    if unknown:
        return False, f"Fearless was enabled, but these champions were not recognized: {', '.join(unknown)}."

    try:
        match = FearlessMatch.model_validate({"timestamp": now, "champs": resolved})
    except Exception as exc:
        return False, f"Fearless was enabled, but bans were not updated: {exc}"

    # Session window starts on first recorded game, not on enable.
    if state.start is None:
        state.start = now

    state.matches.append(match)
    for champ in match.champs:
        if champ not in state.banned:
            state.banned.append(champ)

    return True, f"Fearless updated: +10 champions ({len(state.banned)} total banned)."


def _status_text(channel_id: int, now: datetime | None = None) -> str:
    now = now or _utc_now()
    state = _get_state(channel_id, create=False, now=now)
    if state is None:
        return "Fearless is not configured in this channel. Use `champsfearless enable` to start."

    enabled_text = "enabled" if state.enabled else "disabled"
    lines = [
        f"Fearless is **{enabled_text}** in this channel.",
        f"Matches tracked: `{len(state.matches)}`",
        f"Banned champions: `{len(state.banned)}`",
    ]

    if state.enabled:
        if state.start is None:
            lines.append("Clock: waiting for first recorded game.")
        else:
            lines.append(f"Clock started: `{_format_utc_timestamp(state.start)}`")
            remaining = _state_remaining_window(state, now)
            if remaining is not None:
                lines.append(f"Auto-reset in: `{_format_duration(remaining)}`")

    return "\n".join(lines)


async def handle_fearless(ctx, args) -> None:
    channel_id = getattr(ctx.channel, "id", None)
    if channel_id is None:
        await ctx.send("Could not resolve channel ID for fearless state.")
        return

    subcommand = args[0].lower() if args else "status"

    if subcommand == "help":
        await ctx.send(USAGE)
        return

    if subcommand == "status":
        await ctx.send(_status_text(channel_id))
        return

    if subcommand == "enable":
        state = _get_state(channel_id, create=True)
        assert state is not None
        already_enabled = state.enabled
        state.enabled = True
        if already_enabled:
            await ctx.send(f"Fearless is already enabled.\n{_status_text(channel_id)}")
        else:
            await ctx.send(f"Fearless enabled in this channel.\n{_status_text(channel_id)}")
        return

    if subcommand == "disable":
        state = _get_state(channel_id, create=True)
        assert state is not None
        state.enabled = False
        await ctx.send("Fearless disabled in this channel.")
        return

    if subcommand == "reset":
        state = _get_state(channel_id, create=True)
        assert state is not None
        state.banned.clear()
        state.matches.clear()
        state.start = None
        await ctx.send("Fearless state reset for this channel.")
        return

    if subcommand == "list":
        state = _get_state(channel_id, create=False)
        bans = list(state.banned) if state is not None else []
        if not bans:
            await ctx.send("No current fearless bans in this channel.")
            return
        await ctx.send(", ".join(bans))
        return

    if subcommand in {"add", "remove", "override"}:
        state = _get_state(channel_id, create=True)
        assert state is not None
        champs, unknown = _parse_input_champions(args[1:])
        if unknown:
            await ctx.send(f"Unknown champion(s): {', '.join(unknown)}")
            return

        if subcommand == "add":
            if not champs:
                await ctx.send("Usage: `champsfearless add <champion[, champion...]>`")
                return
            added = [champ for champ in champs if champ not in state.banned]
            state.banned.extend(added)
            await ctx.send(f"Added {len(added)} champion(s) to fearless bans.")
            return

        if subcommand == "remove":
            if not champs:
                await ctx.send("Usage: `champsfearless remove <champion[, champion...]>`")
                return
            existing = set(state.banned)
            removed = [champ for champ in champs if champ in existing]
            state.banned = [champ for champ in state.banned if champ not in champs]
            await ctx.send(f"Removed {len(removed)} champion(s) from fearless bans.")
            return

        state.banned = champs
        await ctx.send(f"Fearless bans overridden. Current bans: {len(state.banned)} champion(s).")
        return

    await ctx.send(USAGE)
