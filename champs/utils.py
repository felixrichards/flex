
from . import myresources


def get_all_champs():
    return myresources.CHAMPS


def apply_player_name_map(match_dict: dict) -> dict:
    mapping = myresources.PLAYER_TO_NAME
    roles_by_champ = myresources.ROLES_BY_CHAMP
    lower_roles_by_champ = {key.lower(): value for key, value in roles_by_champ.items()}

    def is_bot_champ(champion: str) -> bool:
        if not champion:
            return False
        roles = roles_by_champ.get(champion)
        if roles is None:
            roles = lower_roles_by_champ.get(champion.lower())
        if roles is None:
            return False
        return "BOT" in roles

    entries = []
    for side in ("win", "lose"):
        for idx, row in enumerate(match_dict.get(side, [])):
            entries.append((side, idx, row))

    wyn_entries = [(side, idx, row) for side, idx, row in entries if row.get("player") == "Wyn"]
    wyn_assignment = {}
    if len(wyn_entries) >= 2:
        bot_flags = [is_bot_champ(row.get("champion", "")) for _, _, row in wyn_entries]
        if sum(bot_flags) == 1:
            for (side, idx, _), is_bot in zip(wyn_entries, bot_flags):
                wyn_assignment[(side, idx)] = "Wyn" if is_bot else "Sean"
        else:
            for i, (side, idx, _) in enumerate(wyn_entries):
                wyn_assignment[(side, idx)] = "Wyn" if i == 0 else "Sean"

    def remap(side: str):
        mapped_rows = []
        for idx, row in enumerate(match_dict.get(side, [])):
            assigned = wyn_assignment.get((side, idx))
            player = assigned if assigned is not None else mapping.get(row.get("player"), row.get("player"))
            mapped_rows.append(
                {
                    "player": player,
                    "champion": row.get("champion"),
                    "kda": row.get("kda"),
                }
            )
        return mapped_rows

    result = {
        "win": remap("win"),
        "lose": remap("lose"),
        "date": match_dict.get("date"),
    }
    timestamp = match_dict.get("timestamp")
    if timestamp is not None:
        result["timestamp"] = timestamp
    return result
