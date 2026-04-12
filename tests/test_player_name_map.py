from champs import db
from champs.db.models import DiscordPlayerMappingRecord, MatchRecord, PlayerMappingRecord, PlayerRecord
from champs.payloads import Match
from sqlalchemy import select
from sqlalchemy.orm import Session


def _base_payload() -> dict:
    return {
        "win": [
            {"player": "Wyn", "champion": "Jhin", "kda": "1/1/1"},
            {"player": "Wyn", "champion": "Ahri", "kda": "1/1/1"},
            {"player": "Jay", "champion": "Zed", "kda": "1/1/1"},
            {"player": "Sam", "champion": "Ezreal", "kda": "1/1/1"},
            {"player": "Farmer", "champion": "Nocturne", "kda": "1/1/1"},
        ],
        "lose": [
            {"player": "James", "champion": "Senna", "kda": "1/1/1"},
            {"player": "Petez", "champion": "Sivir", "kda": "1/1/1"},
            {"player": "Brands", "champion": "Rakan", "kda": "1/1/1"},
            {"player": "Anticide", "champion": "Ekko", "kda": "1/1/1"},
            {"player": "Kaimen224", "champion": "Lillia", "kda": "1/1/1"},
        ],
    }


def test_wyn_sean_edge_case_prefers_bot_role(tmp_path) -> None:
    db_path = str(tmp_path / "wyn.db")
    db.init_db(db_path)
    match = Match.model_validate(_base_payload())
    resolved = db.resolve_match_names(db_path, match)
    win_names = [row.name for row in resolved.win]
    assert win_names[0] == "Wyn"
    assert win_names[1] == "Sean"


def test_wyn_sean_edge_case_fallback_first_wyn_second_sean(tmp_path) -> None:
    db_path = str(tmp_path / "wyn_fallback.db")
    db.init_db(db_path)
    payload = _base_payload()
    payload["win"][0]["champion"] = "Ahri"
    payload["win"][1]["champion"] = "Zed"
    match = Match.model_validate(payload)
    resolved = db.resolve_match_names(db_path, match)
    win_names = [row.name for row in resolved.win]
    assert win_names[0] == "Wyn"
    assert win_names[1] == "Sean"


def test_role_scoped_mapping_rule_for_duplicate_username(tmp_path) -> None:
    db_path = str(tmp_path / "wyn_role_rule.db")
    db.init_db(db_path)
    db.set_player_mapping(db_path, "Wyn", "Wyn", "BOT")
    db.set_player_mapping(db_path, "Wyn", "Sean")

    payload = _base_payload()
    payload["win"][0]["champion"] = "Jhin"   # BOT
    payload["win"][1]["champion"] = "Ahri"   # MID
    match = Match.model_validate(payload)
    resolved = db.resolve_match_names(db_path, match)
    win_names = [row.name for row in resolved.win]
    assert win_names[0] == "Wyn"
    assert win_names[1] == "Sean"


def test_secondary_role_is_stored_but_primary_drives_mapping(tmp_path) -> None:
    db_path = str(tmp_path / "wyn_secondary_role.db")
    db.init_db(db_path)
    db.set_player_mapping(db_path, "Wyn", "Wyn", "MID", "BOT")
    db.set_player_mapping(db_path, "Wyn", "Sean")

    payload = _base_payload()
    payload["win"][0]["champion"] = "Jhin"  # BOT only
    payload["win"][1]["champion"] = "Ahri"  # MID
    match = Match.model_validate(payload)
    resolved = db.resolve_match_names(db_path, match)
    win_names = [row.name for row in resolved.win]
    assert win_names[0] == "Sean"
    assert win_names[1] == "Wyn"

    engine = db._engine(db_path)
    with Session(engine) as session:
        mapping_row = session.scalar(
            select(PlayerMappingRecord).where(
                PlayerMappingRecord.username == "Wyn",
                PlayerMappingRecord.name == "Wyn",
                PlayerMappingRecord.preferred_role.is_not(None),
            )
        )
    assert mapping_row is not None
    assert mapping_row.preferred_role == "MID"
    assert mapping_row.secondary_role == "BOT"


def test_role_preferences_are_unique_per_actual_name(tmp_path) -> None:
    db_path = str(tmp_path / "name_unique_roles.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "AliasOne", "Felix", "MID", "BOT")
    db.set_player_mapping(db_path, "AliasTwo", "Felix", "TOP", "JUNGLE")

    engine = db._engine(db_path)
    with Session(engine) as session:
        role_rows = session.scalars(
            select(PlayerMappingRecord).where(
                PlayerMappingRecord.name == "Felix",
                PlayerMappingRecord.preferred_role.is_not(None),
            )
        ).all()

    assert len(role_rows) == 1
    assert role_rows[0].preferred_role == "TOP"
    assert role_rows[0].secondary_role == "JUNGLE"


def test_repeated_role_set_for_same_username_updates_instead_of_accumulating(tmp_path) -> None:
    db_path = str(tmp_path / "same_user_role_update.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "Wyn", "Wyn", "MID", "BOT")
    db.set_player_mapping(db_path, "Wyn", "Wyn", "TOP", "JUNGLE")

    engine = db._engine(db_path)
    with Session(engine) as session:
        role_rows = session.scalars(
            select(PlayerMappingRecord).where(
                PlayerMappingRecord.username == "Wyn",
                PlayerMappingRecord.name == "Wyn",
                PlayerMappingRecord.preferred_role.is_not(None),
            )
        ).all()

    assert len(role_rows) == 1
    assert role_rows[0].preferred_role == "TOP"
    assert role_rows[0].secondary_role == "JUNGLE"


def test_delete_player_mapping_removes_only_target_pair(tmp_path) -> None:
    db_path = str(tmp_path / "delete_player_mapping.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "AliasA", "Felix")
    db.set_player_mapping(db_path, "AliasA", "Felix", "MID", "BOT")
    db.set_player_mapping(db_path, "AliasB", "Felix")

    deleted = db.delete_player_mapping(db_path, "AliasA", "Felix")
    assert deleted == 2

    engine = db._engine(db_path)
    with Session(engine) as session:
        remaining = session.scalars(
            select(PlayerMappingRecord).where(PlayerMappingRecord.name == "Felix")
        ).all()

    assert all(row.username != "AliasA" for row in remaining)
    assert any(row.username == "AliasB" for row in remaining)


def test_player_mapping_overview_includes_usernames_roles_and_discord_ids(tmp_path) -> None:
    db_path = str(tmp_path / "player_mapping_overview.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "AliasOne", "Felix", "MID", "BOT")
    db.set_player_mapping(db_path, "AliasTwo", "Felix")
    db.set_discord_player_mapping(db_path, 111, "AliasOne")
    db.set_discord_player_mapping(db_path, 222, "AliasTwo")

    rows = db.get_player_mapping_overview_rows(db_path)
    felix = [row for row in rows if row.name == "Felix"]
    assert len(felix) == 1
    row = felix[0]
    assert {"AliasOne", "AliasTwo"}.issubset(set(row.usernames))
    assert row.primary_role == "MID"
    assert row.secondary_role == "BOT"
    assert {"111", "222"} == set(row.discord_user_ids)


def test_player_mapping_overview_filters_by_name_or_username(tmp_path) -> None:
    db_path = str(tmp_path / "player_mapping_overview_filter.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "AliasFelix", "Felix", "MID", "BOT")
    db.set_player_mapping(db_path, "AliasJay", "Jay", "TOP", "JUNGLE")

    by_name = db.get_player_mapping_overview_rows(db_path, ["Felix"])
    assert [row.name for row in by_name] == ["Felix"]

    by_username = db.get_player_mapping_overview_rows(db_path, ["AliasJay"])
    assert [row.name for row in by_username] == ["Jay"]

    multi = db.get_player_mapping_overview_rows(db_path, ["Felix", "AliasJay"])
    assert [row.name for row in multi] == ["Felix", "Jay"]


def test_player_mapping_overview_prefers_actual_name_over_username(tmp_path) -> None:
    db_path = str(tmp_path / "player_mapping_overview_name_precedence.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "AliasFelix", "Felix", "MID", "BOT")
    db.set_player_mapping(db_path, "Felix", "NotFelix", "TOP", "JUNGLE")

    rows = db.get_player_mapping_overview_rows(db_path, ["Felix"])
    assert [row.name for row in rows] == ["Felix"]


def test_discord_link_for_actual_name_does_not_bleed_to_same_username_aliases(tmp_path) -> None:
    db_path = str(tmp_path / "discord_link_name_isolation.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "Wyn", "Sean", "SUPP", "TOP")
    db.set_player_mapping(db_path, "Wyn", "Wyn", "BOT", "JUNGLE")
    db.set_discord_player_mapping(db_path, 999, "Wyn")

    rows = db.get_player_mapping_overview_rows(db_path, ["Wyn", "Sean"])
    by_name = {row.name: row for row in rows}
    assert "Wyn" in by_name and "Sean" in by_name
    assert "999" in set(by_name["Wyn"].discord_user_ids)
    assert "999" not in set(by_name["Sean"].discord_user_ids)


def test_set_player_mapping_reuses_existing_name_case_insensitively(tmp_path) -> None:
    db_path = str(tmp_path / "mapping_name_case_insensitive.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "AliasOne", "Felix")
    db.set_player_mapping(db_path, "AliasTwo", "felix", "MID", "BOT")

    engine = db._engine(db_path)
    with Session(engine) as session:
        rows = session.scalars(
            select(PlayerMappingRecord).where(PlayerMappingRecord.username.in_(["AliasOne", "AliasTwo"]))
        ).all()

    assert rows
    assert all(row.name == "Felix" for row in rows)
    assert not any(row.name == "felix" for row in rows)


def test_delete_player_completely_is_blocked_when_player_has_matches(tmp_path) -> None:
    db_path = str(tmp_path / "delete_player_completely_blocked.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "FelixMain", "Felix", "MID", "BOT")
    db.set_player_mapping(db_path, "OtherMain", "Other", "TOP", "JUNGLE")
    db.set_discord_player_mapping(db_path, 101, "FelixMain")
    db.set_discord_player_mapping(db_path, 202, "OtherMain")

    first = Match.model_validate(
        {
            "win": [
                {"player": "FelixMain", "champion": "Ahri", "kda": "1/1/1"},
                {"player": "W2", "champion": "Vi", "kda": "1/1/1"},
                {"player": "W3", "champion": "Nami", "kda": "1/1/1"},
                {"player": "W4", "champion": "Annie", "kda": "1/1/1"},
                {"player": "W5", "champion": "Jinx", "kda": "1/1/1"},
            ],
            "lose": [
                {"player": "L1", "champion": "Zed", "kda": "1/1/1"},
                {"player": "L2", "champion": "Riven", "kda": "1/1/1"},
                {"player": "L3", "champion": "Leona", "kda": "1/1/1"},
                {"player": "L4", "champion": "Trundle", "kda": "1/1/1"},
                {"player": "L5", "champion": "Caitlyn", "kda": "1/1/1"},
            ],
        }
    )
    second = Match.model_validate(
        {
            "win": [
                {"player": "OtherMain", "champion": "Ornn", "kda": "1/1/1"},
                {"player": "OW2", "champion": "Vi", "kda": "1/1/1"},
                {"player": "OW3", "champion": "Nami", "kda": "1/1/1"},
                {"player": "OW4", "champion": "Annie", "kda": "1/1/1"},
                {"player": "OW5", "champion": "Jinx", "kda": "1/1/1"},
            ],
            "lose": [
                {"player": "OL1", "champion": "Zed", "kda": "1/1/1"},
                {"player": "OL2", "champion": "Riven", "kda": "1/1/1"},
                {"player": "OL3", "champion": "Leona", "kda": "1/1/1"},
                {"player": "OL4", "champion": "Trundle", "kda": "1/1/1"},
                {"player": "OL5", "champion": "Caitlyn", "kda": "1/1/1"},
            ],
        }
    )
    assert db.insert_match(db_path, first) is True
    assert db.insert_match(db_path, second) is True

    result = db.delete_player_completely(db_path, "felix")
    assert result.deleted_player_rows == 0
    assert result.deleted_mapping_rows == 0
    assert result.deleted_discord_rows == 0
    assert result.associated_matches >= 1
    assert result.associated_match_rows >= 1
    assert "Felix" in set(result.deleted_name_variants)

    engine = db._engine(db_path)
    with Session(engine) as session:
        assert session.scalars(select(PlayerMappingRecord).where(PlayerMappingRecord.name == "Felix")).all()
        assert session.scalars(select(PlayerRecord).where(PlayerRecord.name == "Felix")).all()
        assert session.scalars(
            select(DiscordPlayerMappingRecord).where(DiscordPlayerMappingRecord.player_username == "FelixMain")
        ).all()
        matches = session.scalars(select(MatchRecord)).all()

    assert len(matches) == 2


def test_delete_player_completely_removes_unmatched_player_data(tmp_path) -> None:
    db_path = str(tmp_path / "delete_player_completely_unmatched.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "AliasNonsense", "Nonsense")
    db.set_discord_player_mapping(db_path, 999, "AliasNonsense")
    manual_player_add = PlayerRecord(name="Nonsense", rating=1000)
    engine = db._engine(db_path)
    with Session(engine) as session:
        session.add(manual_player_add)
        session.commit()

    result = db.delete_player_completely(db_path, "nonsense")
    assert result.associated_matches == 0
    assert result.associated_match_rows == 0
    assert result.deleted_mapping_rows >= 1
    assert result.deleted_discord_rows >= 1
    assert result.deleted_player_rows >= 1

    with Session(engine) as session:
        assert not session.scalars(select(PlayerRecord).where(PlayerRecord.name == "Nonsense")).all()
        assert not session.scalars(select(PlayerMappingRecord).where(PlayerMappingRecord.name == "Nonsense")).all()
        assert not session.scalars(
            select(DiscordPlayerMappingRecord).where(DiscordPlayerMappingRecord.player_username == "AliasNonsense")
        ).all()


def test_delete_player_exact_case_variant_without_matches_when_other_variant_has_matches(tmp_path) -> None:
    db_path = str(tmp_path / "delete_player_exact_case_variant.db")
    db.init_db(db_path)

    # Canonical player with match history.
    db.set_player_mapping(db_path, "FelixMain", "Felix", "MID", "BOT")
    match = Match.model_validate(
        {
            "win": [
                {"player": "FelixMain", "champion": "Ahri", "kda": "1/1/1"},
                {"player": "W2", "champion": "Vi", "kda": "1/1/1"},
                {"player": "W3", "champion": "Nami", "kda": "1/1/1"},
                {"player": "W4", "champion": "Annie", "kda": "1/1/1"},
                {"player": "W5", "champion": "Jinx", "kda": "1/1/1"},
            ],
            "lose": [
                {"player": "L1", "champion": "Zed", "kda": "1/1/1"},
                {"player": "L2", "champion": "Riven", "kda": "1/1/1"},
                {"player": "L3", "champion": "Leona", "kda": "1/1/1"},
                {"player": "L4", "champion": "Trundle", "kda": "1/1/1"},
                {"player": "L5", "champion": "Caitlyn", "kda": "1/1/1"},
            ],
        }
    )
    assert db.insert_match(db_path, match) is True

    # Legacy bad-case duplicate with no matches.
    engine = db._engine(db_path)
    with Session(engine) as session:
        session.add(PlayerMappingRecord(username="felixAlias", name="felix", preferred_role=None, secondary_role=None))
        session.add(PlayerRecord(name="felix", rating=1000))
        session.add(DiscordPlayerMappingRecord(discord_user_id="777", player_username="felixAlias"))
        session.commit()

    result = db.delete_player_completely(db_path, "felix")
    assert result.associated_matches == 0
    assert result.associated_match_rows == 0
    assert result.deleted_mapping_rows >= 1
    assert result.deleted_player_rows >= 1
    assert result.deleted_discord_rows >= 1
    assert "felix" in set(result.deleted_name_variants)

    with Session(engine) as session:
        assert not session.scalars(select(PlayerRecord).where(PlayerRecord.name == "felix")).all()
        assert session.scalars(select(PlayerRecord).where(PlayerRecord.name == "Felix")).all()
        assert not session.scalars(select(PlayerMappingRecord).where(PlayerMappingRecord.name == "felix")).all()
        assert session.scalars(select(PlayerMappingRecord).where(PlayerMappingRecord.name == "Felix")).all()
        assert not session.scalars(
            select(DiscordPlayerMappingRecord).where(DiscordPlayerMappingRecord.player_username == "felixAlias")
        ).all()
        assert session.scalars(select(MatchRecord)).all()
