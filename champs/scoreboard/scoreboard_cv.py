from __future__ import annotations

import json
import os
import re
import statistics
import time

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import cv2
from rapidocr_onnxruntime import RapidOCR

from ..myresources import CHAMPS_PLAYERS_MANIFEST


KDA_RE = re.compile(r"[Xx]?\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)")


@dataclass
class OCRBox:
    text: str
    score: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def normalize_path(path: str | Path) -> str:
    return str(Path(os.path.expanduser(str(path))).resolve())


def preprocess_text_crop(image: cv2.typing.MatLike, invert: bool = False) -> cv2.typing.MatLike:
    upscaled = cv2.resize(image, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh_mode = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    _, thresh = cv2.threshold(blurred, 0, 255, thresh_mode + cv2.THRESH_OTSU)
    return thresh


class RapidPostExtractor:
    def __init__(self) -> None:
        self.ocr = RapidOCR()
        self._ocr_calls = 0
        self._ocr_time_ms = 0.0

    def snapshot_stats(self) -> tuple[int, float]:
        return self._ocr_calls, self._ocr_time_ms

    def read_boxes(self, image: str | cv2.typing.MatLike) -> list[OCRBox]:
        started = time.perf_counter()
        result, _ = self.ocr(image)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._ocr_calls += 1
        self._ocr_time_ms += elapsed_ms
        boxes: list[OCRBox] = []
        for polygon, text, score in result or []:
            xs = [point[0] for point in polygon]
            ys = [point[1] for point in polygon]
            boxes.append(
                OCRBox(
                    text=normalize_text(text),
                    score=float(score),
                    x1=min(xs),
                    y1=min(ys),
                    x2=max(xs),
                    y2=max(ys),
                )
            )
        return boxes

    def read_crop_texts(self, image: cv2.typing.MatLike, invert: bool = False) -> list[str]:
        processed = preprocess_text_crop(image, invert=invert)
        return [box.text for box in self.read_boxes(processed) if box.text]


def load_manifest() -> tuple[set[str], set[str]]:
    player_vocab: set[str] = set()
    champion_vocab: set[str] = set()

    data = CHAMPS_PLAYERS_MANIFEST

    player_vocab.update(normalize_text(player) for player in data.get("players", []) if normalize_text(player))
    champion_vocab.update(normalize_text(champion) for champion in data.get("champions", []) if normalize_text(champion))
    return player_vocab, champion_vocab


def fuzzy_match(text: str, vocabulary: set[str], threshold: float = 0.7) -> str:
    candidate = normalize_text(text)
    if not candidate or not vocabulary:
        return candidate

    best = candidate
    best_score = 0.0
    lowered = normalize_for_match(candidate)
    for item in vocabulary:
        lowered_item = normalize_for_match(item)
        score = SequenceMatcher(a=lowered, b=lowered_item).ratio()
        if score > best_score:
            best = item
            best_score = score
    return best if best_score >= threshold else candidate


def parse_kda_text(text: str) -> str:
    match = KDA_RE.search(text)
    if not match:
        raise ValueError(f"Could not parse KDA from {text!r}")
    return "/".join(match.groups())


def parse_kda_from_texts(texts: list[str]) -> str | None:
    if not texts:
        return None
    combined = " ".join(texts)
    try:
        return parse_kda_text(combined)
    except ValueError:
        pass

    tokens = re.findall(r"\d+|/", combined)
    for idx in range(len(tokens) - 4):
        if tokens[idx].isdigit() and tokens[idx + 1] == "/" and tokens[idx + 2].isdigit() and tokens[idx + 3] == "/" and tokens[idx + 4].isdigit():
            return f"{tokens[idx]}/{tokens[idx + 2]}/{tokens[idx + 4]}"
    return None


def collect_kda_rows(boxes: list[OCRBox], width: int) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    for box in boxes:
        if not (0.62 * width <= box.cx <= 0.82 * width):
            continue
        if not KDA_RE.fullmatch(box.text):
            continue
        rows.append((box.cy, parse_kda_text(box.text)))

    rows.sort(key=lambda item: item[0])
    if len(rows) != 10:
        raise ValueError(f"Expected 10 KDA rows, found {len(rows)}")
    return rows


def split_rows(rows: list[tuple[float, str]]) -> tuple[list[tuple[float, str]], list[tuple[float, str]]]:
    gaps = [rows[idx + 1][0] - rows[idx][0] for idx in range(len(rows) - 1)]
    split_index = max(range(len(gaps)), key=gaps.__getitem__) + 1
    top_rows = rows[:split_index]
    bottom_rows = rows[split_index:]
    if len(top_rows) != 5 or len(bottom_rows) != 5:
        raise ValueError(f"Could not split rows into 5 and 5: got {len(top_rows)} and {len(bottom_rows)}")
    return top_rows, bottom_rows


def result_is_victory(boxes: list[OCRBox]) -> bool:
    for box in boxes:
        upper = box.text.upper()
        if "VICTORY" in upper:
            return True
        if "DEFEAT" in upper:
            return False
    raise ValueError("Could not determine winner: screenshot must include the VICTORY/DEFEAT header.")


def is_identity_text(text: str) -> bool:
    stripped = normalize_text(text)
    if not stripped:
        return False
    if "/" in stripped:
        return False
    if re.fullmatch(r"[0-9,\.]+", stripped):
        return False
    upper = stripped.upper()
    if upper in {"TEAM1", "TEAM2", "SCOREBOARD", "PROGRESSION", "KDA"}:
        return False
    if " / MIN" in upper:
        return False
    return True


def best_row_match(
    boxes: list[OCRBox],
    vocabulary: set[str],
    target_y: float,
    row_gap: float,
    threshold: float,
) -> tuple[str, float]:
    if not boxes:
        return "", 0.0

    best_text = boxes[0].text
    best_score = -10.0
    best_similarity = 0.0
    for box in boxes:
        candidate = normalize_text(box.text)
        normalized = normalize_for_match(candidate)
        if not normalized:
            continue

        raw_sim = 0.0
        best_vocab = candidate
        if vocabulary:
            for item in vocabulary:
                score = SequenceMatcher(a=normalized, b=normalize_for_match(item)).ratio()
                if score > raw_sim:
                    raw_sim = score
                    best_vocab = item

        y_penalty = abs(box.cy - target_y) / max(row_gap, 1.0)
        score = raw_sim - 0.35 * y_penalty + 0.05 * box.score
        if score > best_score:
            best_score = score
            best_similarity = raw_sim
            best_text = best_vocab if raw_sim >= threshold else candidate

    return best_text, best_similarity


def extract_row_identity(
    image: cv2.typing.MatLike,
    extractor: RapidPostExtractor,
    boxes: list[OCRBox],
    width: int,
    row_y: float,
    row_gap: float,
    player_vocab: set[str],
    champion_vocab: set[str],
) -> tuple[str, str]:
    height = image.shape[0]
    x1 = width * 0.12
    x2 = width * 0.36
    y1 = row_y - row_gap * 0.55
    y2 = row_y + row_gap * 0.65

    candidates = [box for box in boxes if x1 <= box.cx <= x2 and y1 <= box.cy <= y2 and is_identity_text(box.text)]
    player_candidates = [box for box in candidates if box.cy <= row_y + row_gap * 0.10]
    champion_candidates = [box for box in candidates if box.cy >= row_y + row_gap * 0.08]

    player, player_sim = best_row_match(player_candidates, player_vocab, target_y=row_y, row_gap=row_gap, threshold=0.55)
    champion, champ_sim = best_row_match(
        champion_candidates,
        champion_vocab,
        target_y=row_y + row_gap * 0.30,
        row_gap=row_gap,
        threshold=0.5,
    )

    if player_sim < 0.7 or champ_sim < 0.7:
        row_crop = image[
            max(0, int(row_y - row_gap * 0.45)) : min(height, int(row_y + row_gap * 0.80)),
            int(width * 0.14) : int(width * 0.34),
        ]
        row_texts = extractor.read_crop_texts(row_crop)
        if len(row_texts) >= 2:
            if player_sim < 0.7:
                player = fuzzy_match(row_texts[0], player_vocab, threshold=0.6)
            if champ_sim < 0.7:
                champion = fuzzy_match(row_texts[1], champion_vocab, threshold=0.58)

    if not player or not champion:
        raise ValueError(f"Could not resolve player/champion in row near y={row_y:.1f}")
    return player, champion


def build_team(
    image: cv2.typing.MatLike,
    extractor: RapidPostExtractor,
    boxes: list[OCRBox],
    width: int,
    rows: list[tuple[float, str]],
    player_vocab: set[str],
    champion_vocab: set[str],
) -> list[dict[str, str]]:
    ys = [row_y for row_y, _ in rows]
    gaps = [right - left for left, right in zip(ys, ys[1:])]
    row_gap = statistics.median(gaps) if gaps else 42.0

    team: list[dict[str, str]] = []
    for row_y, kda in rows:
        player, champion = extract_row_identity(
            image,
            extractor,
            boxes,
            width,
            row_y,
            row_gap,
            player_vocab,
            champion_vocab,
        )
        final_kda = kda
        if re.fullmatch(r"0/\d+/0", kda):
            kda_crop = image[
                max(0, int(row_y - row_gap * 0.30)) : min(image.shape[0], int(row_y + row_gap * 0.30)),
                int(width * 0.64) : int(width * 0.83),
            ]
            refined_kda = parse_kda_from_texts(extractor.read_crop_texts(kda_crop))
            if refined_kda and refined_kda != kda:
                refined_kda_inv = parse_kda_from_texts(extractor.read_crop_texts(kda_crop, invert=True))
                if refined_kda_inv == refined_kda:
                    final_kda = refined_kda
        team.append({"player": player, "champion": champion, "kda": final_kda})
    return team


def detect_post_match(
    image_path: str | Path,
    extractor: RapidPostExtractor | None = None,
) -> dict[str, Any]:
    image_path = normalize_path(image_path)
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(image_path)

    extractor = extractor or RapidPostExtractor()
    full_boxes = extractor.read_boxes(image_path)
    player_vocab, champion_vocab = load_manifest()

    kda_rows = collect_kda_rows(full_boxes, image.shape[1])
    top_rows, bottom_rows = split_rows(kda_rows)

    top_team = build_team(image, extractor, full_boxes, image.shape[1], top_rows, player_vocab, champion_vocab)
    bottom_team = build_team(image, extractor, full_boxes, image.shape[1], bottom_rows, player_vocab, champion_vocab)
    top_is_win = result_is_victory(full_boxes)
    return {
        "win": top_team if top_is_win else bottom_team,
        "lose": bottom_team if top_is_win else top_team,
        "date": None,
    }
