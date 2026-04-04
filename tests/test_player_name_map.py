from champs import db
from champs.db.models import PlayerMappingRecord
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
