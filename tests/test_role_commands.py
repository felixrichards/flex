import asyncio
from types import SimpleNamespace

from champs import role


class _FakeCtx:
    def __init__(self, author_id: int = 1234) -> None:
        self.messages: list[str] = []
        self.author = SimpleNamespace(id=author_id)
        self.message = SimpleNamespace(mentions=[])

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


def test_handle_role_sets_mentioned_player_roles_when_mention_trails(monkeypatch) -> None:
    calls: list[tuple[str, str, str, str | None]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    def _fake_linked(_db_path, discord_user_id):
        if int(discord_user_id) == 555:
            return "Caller"
        if int(discord_user_id) == 999:
            return "Felix"
        return None

    def _fake_set_player_roles(db_path, identifier, primary, secondary=None):
        calls.append((db_path, identifier, primary, secondary))
        return "Felix"

    monkeypatch.setattr(role.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(role.db, "get_discord_linked_player_name", _fake_linked)
    monkeypatch.setattr(role.db, "get_discord_user_privilege", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(role.db, "set_player_roles", _fake_set_player_roles)

    ctx = _FakeCtx(author_id=555)
    asyncio.run(role.handle_role(ctx, ("mid", "bot", "<@999>"), "/tmp/test.db"))

    assert calls == [("/tmp/test.db", "Felix", "mid", "bot")]
    assert ctx.messages == ["Updated `Felix` roles to `mid`/`bot`."]


def test_handle_role_sets_mentioned_player_roles_when_mention_leads(monkeypatch) -> None:
    calls: list[tuple[str, str, str, str | None]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    def _fake_linked(_db_path, discord_user_id):
        if int(discord_user_id) == 555:
            return "Caller"
        if int(discord_user_id) == 999:
            return "Felix"
        return None

    def _fake_set_player_roles(db_path, identifier, primary, secondary=None):
        calls.append((db_path, identifier, primary, secondary))
        return "Felix"

    monkeypatch.setattr(role.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(role.db, "get_discord_linked_player_name", _fake_linked)
    monkeypatch.setattr(role.db, "get_discord_user_privilege", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(role.db, "set_player_roles", _fake_set_player_roles)

    ctx = _FakeCtx(author_id=555)
    asyncio.run(role.handle_role(ctx, ("<@999>", "mid", "bot"), "/tmp/test.db"))

    assert calls == [("/tmp/test.db", "Felix", "mid", "bot")]
    assert ctx.messages == ["Updated `Felix` roles to `mid`/`bot`."]


def test_handle_role_rejects_other_target_for_non_admin(monkeypatch) -> None:
    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(role.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(role.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: "Caller")
    monkeypatch.setattr(role.db, "get_discord_user_privilege", lambda *_args, **_kwargs: 0)

    ctx = _FakeCtx(author_id=555)
    asyncio.run(role.handle_role(ctx, ("mid", "<@999>"), "/tmp/test.db"))

    assert ctx.messages == ["Only admins can set roles for other players."]
