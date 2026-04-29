import random

from ..myresources import CHAMPS_BY_ROLE


TOP = "TOP"
JUNGLE = "JUNGLE"
MID = "MID"
BOT = "BOT"
SUPP = "SUPP"
ROLES = TOP, JUNGLE, MID, BOT, SUPP

champs_by_role = {c: r.copy() for c, r in CHAMPS_BY_ROLE.items()}
            

all_champs = []
for role in ROLES:
    random.shuffle(champs_by_role[role])
    champs = champs_by_role[role]
    i = 0
    while i < 8:
        potential_champ = champs.pop()
        if potential_champ not in all_champs:
            all_champs.append(potential_champ)
            i += 1

print(", ".join(all_champs))
