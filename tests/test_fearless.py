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
    fearless.FEARLESS_BY_CHANNEL[channel_id] = FearlessState(enabled=True, start=now)

    updated, message = fearless.record_match_champions(channel_id, _ten_champs(), now=now)

    assert updated is True
    assert "Fearless updated" in message
    assert len(fearless.FEARLESS_BY_CHANNEL[channel_id].matches) == 1
    assert len(fearless.get_fearless_bans(channel_id, now=now)) == 10


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
    assert state.start == now
    assert state.matches == []
