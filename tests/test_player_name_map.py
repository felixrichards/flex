from champs import utils


def _base_match() -> dict:
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


def test_wyn_sean_edge_case_prefers_bot_role() -> None:
    mapped = utils.apply_player_name_map(_base_match())
    win_names = [row["player"] for row in mapped["win"]]
    assert win_names[0] == "Wyn"
    assert win_names[1] == "Sean"


def test_wyn_sean_edge_case_fallback_first_wyn_second_sean() -> None:
    match = _base_match()
    match["win"][0]["champion"] = "Ahri"
    match["win"][1]["champion"] = "Zed"
    mapped = utils.apply_player_name_map(match)
    win_names = [row["player"] for row in mapped["win"]]
    assert win_names[0] == "Wyn"
    assert win_names[1] == "Sean"
