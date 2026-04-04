import asyncio
from types import SimpleNamespace

from champs import player
from champs import match


class _FakeCtx:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)


def test_handle_player_add_preserves_primary_secondary_order(monkeypatch) -> None:
    calls: list[tuple[str, str, str | None, str | None]] = []

    def _fake_set_player_mapping(_db_path, username, name, primary_role=None, secondary_role=None):
        calls.append((username, name, primary_role, secondary_role))

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(player.db, "set_player_mapping", _fake_set_player_mapping)
    monkeypatch.setattr(player.asyncio, "to_thread", _fake_to_thread)

    ctx = _FakeCtx()
    asyncio.run(player._handle_player_add(ctx, ["MaBalls", "Felix", "adc", "top"], "/tmp/test.db"))

    assert calls == [("MaBalls", "Felix", "adc", "top")]
    assert ctx.messages == ["Saved mapping: `MaBalls` -> `Felix` for roles `adc`/`top`"]


class _FakeLinkCtx:
    def __init__(self, author_id: int = 1234, mentions=None) -> None:
        self.messages: list[str] = []
        self.author = SimpleNamespace(id=author_id)
        self.message = SimpleNamespace(mentions=mentions or [])

    async def send(self, message: str) -> None:
        self.messages.append(message)


def test_handle_match_linkdiscord_prefers_actual_name(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def _fake_resolve(_db_path, identifier):
        assert identifier == "Felix"
        return "Felix"

    def _fake_set_discord(_db_path, discord_user_id, player_value):
        calls.append((discord_user_id, player_value))

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(match.db, "resolve_player_identifier_for_link", _fake_resolve)
    monkeypatch.setattr(match.db, "set_discord_player_mapping", _fake_set_discord)
    monkeypatch.setattr(match.asyncio, "to_thread", _fake_to_thread)

    ctx = _FakeLinkCtx(author_id=9876)
    asyncio.run(match._handle_match_linkdiscord(ctx, ["Felix"], "/tmp/test.db"))

    assert calls == [(9876, "Felix")]
    assert ctx.messages == ["Linked Discord user `9876` -> player `Felix`"]


def test_handle_match_linkdiscord_username_resolves_to_actual_name(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def _fake_resolve(_db_path, identifier):
        assert identifier == "MaBalls"
        return "Felix"

    def _fake_set_discord(_db_path, discord_user_id, player_value):
        calls.append((discord_user_id, player_value))

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(match.db, "resolve_player_identifier_for_link", _fake_resolve)
    monkeypatch.setattr(match.db, "set_discord_player_mapping", _fake_set_discord)
    monkeypatch.setattr(match.asyncio, "to_thread", _fake_to_thread)

    ctx = _FakeLinkCtx(author_id=4321)
    asyncio.run(match._handle_match_linkdiscord(ctx, ["MaBalls"], "/tmp/test.db"))

    assert calls == [(4321, "Felix")]
    assert ctx.messages == ["Linked Discord user `4321` -> player `Felix`"]
