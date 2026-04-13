from __future__ import annotations

from enum import IntEnum

DRAFT_WINDOW_SECONDS = 300
DODGE_WINDOW_SECONDS = 60
DODGE_PENALTY = 10
DODGE_MAX_NO_PENALTY = 5


class Privilege(IntEnum):
    PLAYER = 0
    OPERATOR = 1
    ADMIN = 2
    SUPERADMIN = 3


def privilege_name(value: int) -> str:
    try:
        return Privilege(value).name.lower()
    except ValueError:
        return f"unknown({value})"
