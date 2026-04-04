from datetime import timezone

import manual_elo


def _row(player: str) -> dict:
    return {"player": player, "champion": "Ezreal", "kda": "1/2/3"}


def _match_payload(date: str) -> dict:
    return {
        "win": [_row(f"w{i}") for i in range(5)],
        "lose": [_row(f"l{i}") for i in range(5)],
        "date": date,
    }


def test_load_matches_uses_date_for_timestamp() -> None:
    match = manual_elo._load_matches(_match_payload("05/04/2026"))[0]
    assert match.timestamp.tzinfo == timezone.utc
    assert match.timestamp.year == 2026
    assert match.timestamp.month == 4
    assert match.timestamp.day == 5
    assert match.timestamp.hour == 12


def test_insert_matches_sorts_by_timestamp(monkeypatch) -> None:
    early = manual_elo._load_matches(_match_payload("01/01/2024"))[0]
    late = manual_elo._load_matches(_match_payload("01/01/2025"))[0]
    call_order: list[object] = []

    def fake_insert_match(_db_path, match):
        call_order.append(match.timestamp)
        return True

    monkeypatch.setattr(manual_elo.db, "insert_match", fake_insert_match)
    inserted, skipped = manual_elo._insert_matches("/tmp/unused.db", [late, early])

    assert inserted == 2
    assert skipped == 0
    assert call_order == sorted(call_order)


def test_load_player_mappings_accepts_players_wrapper() -> None:
    payload = {
        "players": [
            {
                "username": "MaBalls",
                "name": "Felix",
                "primary_role": "JUNGLE",
                "secondary_role": "TOP",
            }
        ]
    }
    rows = manual_elo._load_player_mappings(payload)
    assert len(rows) == 1
    assert rows[0].username == "MaBalls"
    assert rows[0].name == "Felix"
    assert rows[0].primary_role == "JUNGLE"
    assert rows[0].secondary_role == "TOP"


def test_load_player_mappings_accepts_list_shape() -> None:
    payload = [
        {"username": "Wyn", "name": "Wyn", "primary_role": "BOT"},
        {"username": "Wyn", "name": "Sean"},
    ]
    rows = manual_elo._load_player_mappings(payload)
    assert len(rows) == 2
    assert rows[0].primary_role == "BOT"
    assert rows[1].secondary_role is None
