import asyncio
from types import SimpleNamespace

from champs import role


class _FakeCtx:
    def __init__(self, author_id: int = 1234) -> None:
        self.messages: list[str] = []
        self.author = SimpleNamespace(id=author_id)

    async def send(self, message: str) -> None:
        self.messages.append(message)


def test_handle_role_requires_discord_link(monkeypatch) -> None:
    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(role.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(role.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: None)

    ctx = _FakeCtx(author_id=555)
    asyncio.run(role.handle_role(ctx, ("mid", "bot"), "/tmp/test.db"))

    assert ctx.messages == ["Your Discord account is not linked to a player. Use `champsplayer linkdiscord` first."]


def test_handle_role_sets_linked_player_roles(monkeypatch) -> None:
    calls: list[tuple[str, str, str, str | None]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(role.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(role.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: "Felix")

    def _fake_set_player_roles(db_path, identifier, primary, secondary=None):
        calls.append((db_path, identifier, primary, secondary))
        return "Felix"

    monkeypatch.setattr(role.db, "set_player_roles", _fake_set_player_roles)

    ctx = _FakeCtx(author_id=555)
    asyncio.run(role.handle_role(ctx, ("mid", "bot"), "/tmp/test.db"))

    assert calls == [("/tmp/test.db", "Felix", "mid", "bot")]
    assert ctx.messages == ["Updated `Felix` roles to `mid`/`bot`."]
