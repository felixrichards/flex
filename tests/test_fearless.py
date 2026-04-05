from datetime import datetime, timedelta, timezone

import pytest

from champs import fearless
from champs.payloads.fearless import FearlessMatch, FearlessState


def _ten_champs() -> list[str]:
    return fearless.ALL_CHAMPS[:10]


@pytest.fixture(autouse=True)
def _clear_fearless_state() -> None:
    fearless.FEARLESS_BY_CHANNEL.clear()


def test_fearless_match_requires_10_unique_champs() -> None:
    champs = _ten_champs()
    model = FearlessMatch.model_validate({"champs": champs})
    assert len(model.champs) == 10

    with pytest.raises(Exception):
        FearlessMatch.model_validate({"champs": champs[:9]})

    with pytest.raises(Exception):
        FearlessMatch.model_validate({"champs": champs[:9] + [champs[0]]})


def test_record_match_champions_updates_bans_when_enabled() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    channel_id = 123
    fearless.FEARLESS_BY_CHANNEL[channel_id] = FearlessState(enabled=True, start=None)

    updated, message = fearless.record_match_champions(channel_id, _ten_champs(), now=now)

    assert updated is True
    assert "Fearless updated" in message
    assert fearless.FEARLESS_BY_CHANNEL[channel_id].start == now
    assert len(fearless.FEARLESS_BY_CHANNEL[channel_id].matches) == 1
    assert len(fearless.get_fearless_bans(channel_id, now=now)) == 10


def test_enable_does_not_start_session_clock() -> None:
    class _Ctx:
        def __init__(self) -> None:
            self.channel = type("Channel", (), {"id": 321})()
            self.messages: list[str] = []

        async def send(self, message: str) -> None:
            self.messages.append(message)

    ctx = _Ctx()
    fearless.FEARLESS_BY_CHANNEL[321] = FearlessState(enabled=False, start=None)

    import asyncio

    asyncio.run(fearless.handle_fearless(ctx, ("enable",)))

    state = fearless.FEARLESS_BY_CHANNEL[321]
    assert state.enabled is True
    assert state.start is None


def test_enabled_without_first_game_does_not_start_or_rollover_clock() -> None:
    channel_id = 654
    future = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    fearless.FEARLESS_BY_CHANNEL[channel_id] = FearlessState(
        enabled=True,
        start=None,
        banned=["Ahri"],
        matches=[],
    )

    bans = fearless.get_fearless_bans(channel_id, now=future)

    assert bans == ["Ahri"]
    state = fearless.FEARLESS_BY_CHANNEL[channel_id]
    assert state.start is None
    assert state.enabled is True


def test_rollover_window_is_anchored_to_first_recorded_game() -> None:
    channel_id = 777
    enabled_at = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    first_game_at = enabled_at + timedelta(hours=5)

    fearless.FEARLESS_BY_CHANNEL[channel_id] = FearlessState(enabled=True, start=None)

    updated, _ = fearless.record_match_champions(channel_id, _ten_champs(), now=first_game_at)
    assert updated is True
    assert fearless.FEARLESS_BY_CHANNEL[channel_id].start == first_game_at

    still_in_window = first_game_at + timedelta(hours=5)
    assert len(fearless.get_fearless_bans(channel_id, now=still_in_window)) == 10

    post_window = first_game_at + timedelta(hours=7)
    assert fearless.get_fearless_bans(channel_id, now=post_window) == []


def test_get_fearless_bans_rolls_over_after_six_hours() -> None:
    channel_id = 456
    old_start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    now = old_start + timedelta(hours=7)
    fearless.FEARLESS_BY_CHANNEL[channel_id] = FearlessState(
        enabled=True,
        start=old_start,
        banned=_ten_champs(),
        matches=[FearlessMatch.model_validate({"timestamp": old_start, "champs": _ten_champs()})],
    )

    bans = fearless.get_fearless_bans(channel_id, now=now)

    assert bans == []
    state = fearless.FEARLESS_BY_CHANNEL[channel_id]
    assert state.enabled is True
    assert state.start is None
    assert state.matches == []
