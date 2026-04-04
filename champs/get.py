import enum
import random
from io import BytesIO
from typing import List, Tuple

import discord

from champs.random_champs import filters, random_champ_weighted, secret


USAGE = """After the command, write the desired number of champs to get a random selection of champs even across roles.
If no number is given, 40 are returned.
You can also add filters, e.g. role, class. For example: champsget 3 assassin jungle.
"""


RANDOM_WYNS = [
    "wyn is a fucking moron",
    "wyn is literally steve from minecraft",
    "petrol head wyn strikes again",
    "wyn has single digit IQ",
    "wyn has double digit IQ",
    "wyn's anivia is actually really good",
    "wyn on ad vs. wyn off-role",
    "wyn's favourite beer is budweiser",
    "wyn spent >1k on a greenhouse for tomatoes",
    "wyn drives a 2008 honda civic which he paid 10k for in 2024",
    "wyn wishes he could main qiyana",
    "just imagine being wyn",
    "wyn likes to go fly fishing with his dad",
    "leblanc combo 2022",
    "wyn gets silent when tilted",
    "wyn cannot play jhin",
]


def _get_random_wyn() -> str:
    wyns = RANDOM_WYNS.copy()
    random.shuffle(wyns)
    return wyns[0]


def _is_int(value: str) -> bool:
    try:
        int(value)
        return True
    except Exception:
        return False


class Special(enum.Enum):
    WYN = 0
    HALF = 1
    PERSON = 2

    @staticmethod
    def get_special(value: str):
        if value == "1337":
            return Special.WYN
        if value == "0.5":
            return Special.HALF
        if value.upper() in secret.OTP_CHAMPS:
            return Special.PERSON
        return None


class BotArgsError(Exception):
    pass


def parse_get_args(args) -> Tuple[int, List[str], Special | None, List[str]]:
    if len(args) == 0:
        return 40, [], None, []

    count = None
    filter_strs: list[str] = []
    special = Special.get_special(args[0]) or None
    unrecognised_arguments = []

    if special is Special.HALF:
        count = 1

    if special is Special.PERSON:
        filter_strs.append(args[0])

    for arg in args:
        if _is_int(arg) and count is None:
            count = int(arg)
        elif filters.is_valid_filter(arg):
            filter_strs.append(arg)
        else:
            unrecognised_arguments.append(arg)

    if count is None and not filter_strs and unrecognised_arguments:
        raise BotArgsError("No recognised arguments were passed.")

    if count is None:
        count = 40

    if count < 1 or count > 120:
        raise BotArgsError("Number must be a whole number between 1 & 120.")

    return count, filter_strs, special, unrecognised_arguments


async def handle_get(ctx, args) -> None:
    try:
        count, filter_strs, special, unrecognised_arguments = parse_get_args(args)
    except BotArgsError as exc:
        await ctx.send(f"{str(exc)}\n\n{USAGE}")
        return

    if special is Special.WYN:
        await ctx.send(_get_random_wyn())
        return

    if unrecognised_arguments and not special:
        await ctx.send(f"Unrecognised arguments: {', '.join(unrecognised_arguments)}.")

    if special is Special.PERSON:
        champ, img = secret.get_champ_and_img(filter_strs[0])
        champs = [champ]
    elif filter_strs:
        champs = random_champ_weighted.get_random_champs_with_filters(count, filter_strs)
        if not champs:
            await ctx.send("No champions found.")
            return
        img = random_champ_weighted.make_grid_from_champs(champs, force_line=True)
    else:
        selected_champs_by_role = random_champ_weighted.get_random_champs_by_role_weighted(count)
        img = random_champ_weighted.make_grid_from_champs_by_role(selected_champs_by_role)
        champs = sum(selected_champs_by_role.values(), start=[])

    if special is Special.HALF:
        champs = [champ[: len(champ) // 2] for champ in champs]
        img = img.crop((0, 0, 30, 60))

    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    file = discord.file.File(img_bytes, filename="champs.png")
    await ctx.send(", ".join(champs), file=file)
