from champs.db import db
from champs.payloads import Match


def _make_match(win_names, lose_names) -> Match:
    return Match.model_validate(
        {
            "win": [{"player": name, "champion": "Ezreal", "kda": "1/1/1"} for name in win_names],
            "lose": [{"player": name, "champion": "Nami", "kda": "1/1/1"} for name in lose_names],
            "date": None,
        }
    )


def test_get_elo_rows_resolves_username_to_mapped_name_and_dedupes(tmp_path) -> None:
    db_path = str(tmp_path / "elo_query.db")
    db.init_db(db_path)
    db.set_player_mapping(db_path, "MaBalls", "Felix")
    db.set_player_mapping(db_path, "Wyn", "Wyn", "BOT")
    db.set_player_mapping(db_path, "Wyn", "Sean")

    match = Match.model_validate(
        {
            "win": [
                {"player": "MaBalls", "champion": "Udyr", "kda": "1/1/1"},
                {"player": "Wyn", "champion": "Jhin", "kda": "1/1/1"},
                {"player": "A", "champion": "Ahri", "kda": "1/1/1"},
                {"player": "B", "champion": "Ashe", "kda": "1/1/1"},
                {"player": "C", "champion": "Nami", "kda": "1/1/1"},
            ],
            "lose": [
                {"player": "Wyn", "champion": "Ahri", "kda": "1/1/1"},
                {"player": "D", "champion": "Gwen", "kda": "1/1/1"},
                {"player": "E", "champion": "Vi", "kda": "1/1/1"},
                {"player": "F", "champion": "Leona", "kda": "1/1/1"},
                {"player": "G", "champion": "Jax", "kda": "1/1/1"},
            ],
        }
    )
    assert db.insert_match(db_path, match) is True

    full = db.get_elo_rows(db_path)
    assert len(full) >= 3

    by_username = db.get_elo_rows(db_path, ["MaBalls"])
    assert [row.player for row in by_username] == ["Felix"]

    by_name = db.get_elo_rows(db_path, ["Felix"])
    assert [row.player for row in by_name] == ["Felix"]

    by_name_lower = db.get_elo_rows(db_path, ["felix"])
    assert [row.player for row in by_name_lower] == ["Felix"]

    deduped = db.get_elo_rows(db_path, ["Felix", "MaBalls", "Felix"])
    assert [row.player for row in deduped] == ["Felix"]

    wyn = db.get_elo_rows(db_path, ["Wyn"])
    assert [row.player for row in wyn] == ["Wyn"]
