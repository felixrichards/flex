from champs.db import db


def test_apply_and_undo_dodge_penalties_use_exact_history(tmp_path) -> None:
    db_path = str(tmp_path / "dodges.db")
    db.init_db(db_path)
    db.set_player_mapping(db_path, "AliasFelix", "Felix")
    db.set_player_privilege(db_path, "Felix", 0)

    first = db.apply_dodge_penalty(db_path, "Felix", 10.0, source="test")
    second = db.apply_dodge_penalty(db_path, "Felix", 10.0, source="test")

    rows = db.get_elo_rows(db_path, ["Felix"])
    assert len(rows) == 1
    row = rows[0]
    assert first == 10
    assert second == 20
    assert row.dodges == 2
    assert row.cp == 1000 - first - second

    restored = db.undo_recent_dodge_penalties(db_path, "Felix", 1)
    assert restored == second

    updated = db.get_elo_rows(db_path, ["Felix"])[0]
    assert updated.dodges == 1
    assert updated.cp == 1000 - first


def test_get_elo_rows_contains_cp_dodges_and_scale(tmp_path) -> None:
    db_path = str(tmp_path / "elo_cp_fields.db")
    db.init_db(db_path)
    db.set_player_mapping(db_path, "AliasOne", "Felix")
    db.set_player_privilege(db_path, "Felix", 0)

    penalty = db.apply_dodge_penalty(db_path, "Felix", 10.0, source="test")
    assert penalty == 10

    rows = db.get_elo_rows(db_path)
    felix = [row for row in rows if row.player == "Felix"][0]
    assert felix.cp == 990
    assert felix.elo == 1000
    assert felix.dodges == 1
    assert felix.dodge_scale == 2.0
