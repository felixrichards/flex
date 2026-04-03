import pytest

from champs.payloads import Match


def _row(player: str) -> dict:
    return {"player": player, "champion": "Ezreal", "kda": "1/2/3"}


def test_match_schema_accepts_5v5() -> None:
    payload = {
        "win": [_row(f"w{i}") for i in range(5)],
        "lose": [_row(f"l{i}") for i in range(5)],
        "date": None,
    }
    model = Match.model_validate(payload)
    assert len(model.win) == 5
    assert len(model.lose) == 5
    assert model.checksum


def test_match_schema_rejects_non_5v5() -> None:
    payload = {
        "win": [_row(f"w{i}") for i in range(4)],
        "lose": [_row(f"l{i}") for i in range(5)],
    }
    with pytest.raises(Exception):
        Match.model_validate(payload)


def test_match_checksum_is_order_invariant_within_team() -> None:
    payload_a = {
        "win": [
            _row("w0"),
            _row("w1"),
            _row("w2"),
            _row("w3"),
            _row("w4"),
        ],
        "lose": [
            _row("l0"),
            _row("l1"),
            _row("l2"),
            _row("l3"),
            _row("l4"),
        ],
        "date": None,
    }
    payload_b = {
        "win": [
            _row("w4"),
            _row("w2"),
            _row("w0"),
            _row("w1"),
            _row("w3"),
        ],
        "lose": [
            _row("l3"),
            _row("l0"),
            _row("l4"),
            _row("l2"),
            _row("l1"),
        ],
        "date": None,
    }
    match_a = Match.model_validate(payload_a)
    match_b = Match.model_validate(payload_b)
    assert match_a.checksum == match_b.checksum
