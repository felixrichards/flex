from champs.scoreboard import scoreboard_cv


def test_fuzzy_match_handles_i_l_confusion() -> None:
    vocab = {"kailen224", "wyn", "sam"}
    assert scoreboard_cv.fuzzy_match("kallen224", vocab, threshold=0.7) == "kailen224"


def test_best_row_match_handles_i_l_confusion() -> None:
    boxes = [
        scoreboard_cv.OCRBox(text="kallen224", score=0.95, x1=0, y1=10, x2=30, y2=20),
    ]
    matched, similarity = scoreboard_cv.best_row_match(
        boxes=boxes,
        vocabulary={"kailen224"},
        target_y=15,
        row_gap=20,
        threshold=0.7,
    )
    assert matched == "kailen224"
    assert similarity >= 0.7
