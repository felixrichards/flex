import random

from ..myresources import CHAMPS_WITH_ROLE_DATA


TOP = "TOP"
JUNGLE = "JUNGLE"
MID = "MID"
BOT = "BOT"
SUPP = "SUPP"
ROLES = TOP, JUNGLE, MID, BOT, SUPP

champs_by_role = {role: [] for role in ROLES}

for champ_data in CHAMPS_WITH_ROLE_DATA:
    champ, parsed_roles = champ_data.split("\t")[0], champ_data.split("\t")[1:-1]
    for parsed_role, ROLE in zip(parsed_roles, ROLES):
        if parsed_role:
            champs_by_role[ROLE].append(champ)
            

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
