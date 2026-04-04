import json

import pytest

from champs.scoreboard import scoreboard_cv
from conftest import resource_path


def _load_cases() -> list[dict]:
    path = resource_path("scoreboard_cases.json")
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else []


CASES = _load_cases()


def _canonical_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        [
            {
                "player": row["player"],
                "champion": row["champion"].lower(),
                "kda": row["kda"],
            }
            for row in rows
        ],
        key=lambda r: (r["player"], r["champion"], r["kda"]),
    )


def _canonical_match(data: dict) -> dict:
    return {
        "win": _canonical_rows(data["win"]),
        "lose": _canonical_rows(data["lose"]),
        "date": data.get("date"),
    }


@pytest.mark.skipif(not CASES, reason="No resource-driven parser cases configured.")
@pytest.mark.parametrize("case", CASES, ids=[case.get("id", str(i)) for i, case in enumerate(CASES)])
def test_scoreboard_parser_case(case: dict) -> None:
    filename = case["filename"]
    expected = {"win": case["win"], "lose": case["lose"], "date": None}
    image_path = resource_path("scoreboards", filename)
    result = scoreboard_cv.detect_post_match(str(image_path))
    assert _canonical_match(result) == _canonical_match(expected)


def test_scoreboard_parser_6a_6b_identical() -> None:
    image_6a = resource_path("scoreboards", "6a.png")
    image_6b = resource_path("scoreboards", "6b.png")
    result_6a = scoreboard_cv.detect_post_match(str(image_6a))
    result_6b = scoreboard_cv.detect_post_match(str(image_6b))
    assert _canonical_match(result_6a) == _canonical_match(result_6b)
