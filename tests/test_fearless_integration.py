import asyncio
from types import SimpleNamespace

import pytest

from champs import fearless
from champs import get as get_route
from champs.random_champs import constants


class _FakeImage:
    def save(self, handle, format=None) -> None:
        handle.write(b"png")

    def crop(self, _box):
        return self


class _FakeCtx:
    def __init__(self, channel_id: int = 1) -> None:
        self.channel = SimpleNamespace(id=channel_id)
        self.messages: list[tuple[str, object | None]] = []

    async def send(self, message: str, file=None) -> None:
        self.messages.append((message, file))


@pytest.fixture(autouse=True)
def _clear_fearless_state() -> None:
    fearless.FEARLESS_BY_CHANNEL.clear()


def test_handle_fearless_enable_add_remove_and_list() -> None:
    ctx = _FakeCtx(channel_id=99)

    asyncio.run(fearless.handle_fearless(ctx, ("enable",)))
    asyncio.run(fearless.handle_fearless(ctx, ("add", "Ahri, Nunu & Willump")))
    asyncio.run(fearless.handle_fearless(ctx, ("remove", "Ahri")))
    asyncio.run(fearless.handle_fearless(ctx, ("list",)))

    assert "Fearless enabled in this channel." in ctx.messages[0][0]
    assert "Added 2 champion(s)" in ctx.messages[1][0]
    assert "Removed 1 champion(s)" in ctx.messages[2][0]
    assert ctx.messages[3][0] == "Nunu & Willump"


def test_handle_fearless_unknown_champion_is_rejected() -> None:
    ctx = _FakeCtx(channel_id=88)

    asyncio.run(fearless.handle_fearless(ctx, ("add", "DefinitelyNotAChamp")))

    assert ctx.messages[0][0] == "Unknown champion(s): DefinitelyNotAChamp"


def test_handle_get_main_flow_passes_fearless_bans(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    ctx = _FakeCtx(channel_id=7)

    def _fake_get_bans(channel_id: int):
        assert channel_id == 7
        return ["Ahri", "Lux"]

    def _fake_weighted(count: int, fearless_bans=None):
        captured["count"] = count
        captured["fearless_bans"] = list(fearless_bans or [])
        return {role: [f"{role}_CHAMP"] for role in constants.ROLES}

    monkeypatch.setattr(get_route.fearless, "get_fearless_bans", _fake_get_bans)
    monkeypatch.setattr(
        get_route.random_champ_weighted,
        "get_random_champs_by_role_weighted",
        _fake_weighted,
    )
    monkeypatch.setattr(get_route.random_champ_weighted, "make_grid_from_champs_by_role", lambda *_: _FakeImage())

    asyncio.run(get_route.handle_get(ctx, ("5",)))

    assert captured["count"] == 5
    assert captured["fearless_bans"] == ["Ahri", "Lux"]
    assert "TOP_CHAMP" in ctx.messages[0][0]


def test_handle_get_filter_flow_does_not_use_fearless(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeCtx(channel_id=2)

    monkeypatch.setattr(
        get_route.fearless,
        "get_fearless_bans",
        lambda *_: (_ for _ in ()).throw(AssertionError("fearless bans should not be read for filter flow")),
    )
    monkeypatch.setattr(
        get_route.random_champ_weighted,
        "get_random_champs_with_filters",
        lambda *_: ["Ahri"],
    )
    monkeypatch.setattr(get_route.random_champ_weighted, "make_grid_from_champs", lambda *_args, **_kwargs: _FakeImage())

    asyncio.run(get_route.handle_get(ctx, ("1", "mid")))

    assert ctx.messages[0][0] == "Ahri"
