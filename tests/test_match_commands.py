import asyncio
from types import SimpleNamespace

from champs import match
from champs import player


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


def test_handle_player_delete_requires_name() -> None:
    ctx = _FakeCtx()
    asyncio.run(player._handle_player_delete(ctx, [], "/tmp/test.db"))
    assert ctx.messages == ["Usage: `champsplayer delete <name>`"]


def test_handle_player_delete_calls_full_delete(monkeypatch) -> None:
    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    def _fake_delete_player(_db_path, name):
        assert _db_path == "/tmp/test.db"
        assert name == "felix"
        return player.db.PlayerDeleteResult(
            deleted_player_rows=1,
            deleted_mapping_rows=2,
            deleted_discord_rows=1,
            associated_matches=0,
            associated_match_rows=0,
            deleted_name_variants=("Felix",),
        )

    monkeypatch.setattr(player.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(player.db, "delete_player_completely", _fake_delete_player)

    ctx = _FakeCtx()
    asyncio.run(player._handle_player_delete(ctx, ["felix"], "/tmp/test.db"))

    assert len(ctx.messages) == 1
    assert "Deleted player `Felix`." in ctx.messages[0]


def test_handle_player_delete_blocks_when_match_history_exists(monkeypatch) -> None:
    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    def _fake_delete_player(_db_path, name):
        assert _db_path == "/tmp/test.db"
        assert name == "felix"
        return player.db.PlayerDeleteResult(
            deleted_player_rows=0,
            deleted_mapping_rows=0,
            deleted_discord_rows=0,
            associated_matches=2,
            associated_match_rows=12,
            deleted_name_variants=("Felix",),
        )

    monkeypatch.setattr(player.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(player.db, "delete_player_completely", _fake_delete_player)

    ctx = _FakeCtx()
    asyncio.run(player._handle_player_delete(ctx, ["felix"], "/tmp/test.db"))

    assert len(ctx.messages) == 1
    assert "Cannot delete `Felix` because they have recorded match history" in ctx.messages[0]


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

    monkeypatch.setattr(player.db, "resolve_player_identifier_for_link", _fake_resolve)
    monkeypatch.setattr(player.db, "set_discord_player_mapping", _fake_set_discord)
    monkeypatch.setattr(player.db, "get_discord_user_privilege", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(player.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(player.asyncio, "to_thread", _fake_to_thread)

    ctx = _FakeLinkCtx(author_id=9876)
    asyncio.run(player._handle_player_linkdiscord(ctx, ["Felix"], "/tmp/test.db"))

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

    monkeypatch.setattr(player.db, "resolve_player_identifier_for_link", _fake_resolve)
    monkeypatch.setattr(player.db, "set_discord_player_mapping", _fake_set_discord)
    monkeypatch.setattr(player.db, "get_discord_user_privilege", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(player.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(player.asyncio, "to_thread", _fake_to_thread)

    ctx = _FakeLinkCtx(author_id=4321)
    asyncio.run(player._handle_player_linkdiscord(ctx, ["MaBalls"], "/tmp/test.db"))

    assert calls == [(4321, "Felix")]
    assert ctx.messages == ["Linked Discord user `4321` -> player `Felix`"]


def test_handle_match_linkdiscord_blocks_non_admin_remap(monkeypatch) -> None:
    def _fake_resolve(_db_path, identifier):
        return "Felix" if identifier == "Felix" else None

    def _fake_existing_target(_db_path, discord_user_id):
        assert discord_user_id == 4321
        return "Wyn"

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(player.db, "resolve_player_identifier_for_link", _fake_resolve)
    monkeypatch.setattr(player.db, "get_discord_user_privilege", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(player.db, "get_discord_linked_player_name", _fake_existing_target)
    monkeypatch.setattr(player.asyncio, "to_thread", _fake_to_thread)

    ctx = _FakeLinkCtx(author_id=9999)
    asyncio.run(player._handle_player_linkdiscord(ctx, ["Felix", "4321"], "/tmp/test.db"))

    assert ctx.messages == ["Only admins can remap a Discord user from one player to another."]


def test_handle_player_admin_requires_superadmin(monkeypatch) -> None:
    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(player.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(player.db, "get_discord_user_privilege", lambda *_args, **_kwargs: 2)

    ctx = _FakeLinkCtx(author_id=1111)
    asyncio.run(player._handle_player_admin(ctx, ["Felix"], "/tmp/test.db"))

    assert ctx.messages == ["Only superadmins can grant admin privilege."]


def test_handle_player_private_requires_identifier() -> None:
    ctx = _FakeLinkCtx(author_id=1111)
    asyncio.run(player._handle_player_private(ctx, [], "/tmp/test.db"))
    assert ctx.messages == ["Usage: `champsplayer private <caseinsensitive_player_or_casesensitive_username>`"]


def test_handle_player_private_toggles_and_reports_state(monkeypatch) -> None:
    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(player.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(player.db, "toggle_player_private", lambda *_args, **_kwargs: ("Felix", True))

    ctx = _FakeLinkCtx(author_id=1111)
    asyncio.run(player._handle_player_private(ctx, ["Felix"], "/tmp/test.db"))

    assert ctx.messages == ["`Felix` is now `hidden` in unfiltered `champselo` output."]


def test_handle_on_message_corrected_payload_is_saved(monkeypatch) -> None:
    class _FakeDiscordMessage:
        def __init__(self, message_id: int, author, content: str = "") -> None:
            self.id = message_id
            self.author = author
            self.content = content
            self.edited_content = None

        async def edit(self, content=None, view=None):
            self.edited_content = content

    class _FakeChannel:
        def __init__(self, channel_id: int) -> None:
            self.id = channel_id
            self.sent: list[str] = []

        async def send(self, message: str) -> None:
            self.sent.append(message)

    class _FakeIncomingMessage:
        def __init__(self, author, referenced, channel) -> None:
            self.author = author
            self.reference = SimpleNamespace(resolved=referenced)
            self.content = "```json\n{}\n```"
            self.channel = channel

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    parsed_match = object()

    monkeypatch.setattr(match.discord, "Message", _FakeDiscordMessage)
    monkeypatch.setattr(match.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(match, "extract_json_payload", lambda _content: {"win": [], "lose": []})
    monkeypatch.setattr(match, "_parse_match_payload", lambda _payload: parsed_match)
    monkeypatch.setattr(match.db, "resolve_match_names", lambda _db_path, parsed: parsed)
    monkeypatch.setattr(match, "_format_scoreboard_message", lambda _m: "formatted scoreboard")

    async def _fake_save(_db_path, _match, channel_id=None):
        assert channel_id == 55
        return True, "Saved to match history."

    monkeypatch.setattr(match, "_save_match_to_db", _fake_save)

    bot_user = SimpleNamespace(id=7, bot=True)
    referenced = _FakeDiscordMessage(message_id=999, author=bot_user, content="old")
    channel = _FakeChannel(channel_id=55)
    incoming_author = SimpleNamespace(bot=False)
    incoming = _FakeIncomingMessage(author=incoming_author, referenced=referenced, channel=channel)
    bot = SimpleNamespace(user=bot_user)

    handled = asyncio.run(match.handle_on_message(incoming, bot, "/tmp/test.db"))

    assert handled is True
    assert referenced.edited_content == "formatted scoreboard"
    assert channel.sent[-1].startswith("Updated and saved.")
    assert 999 not in match.PENDING_MATCHES
