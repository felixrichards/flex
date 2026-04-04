from __future__ import annotations

import argparse
import json

from champs.scoreboard import scoreboard_cv
from champs.payloads import Match


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run scoreboard OCR on an image and print parsed match JSON."
    )
    parser.add_argument("image_path", help="Path to scoreboard image")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of pretty-printed output",
    )
    args = parser.parse_args()

    parsed = scoreboard_cv.detect_post_match(args.image_path)
    match = Match.model_validate(parsed)
    payload = match.model_dump(mode="json", exclude={"timestamp"})

    if args.compact:
        print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
    else:
        print(json.dumps(payload, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
