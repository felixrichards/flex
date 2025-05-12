import math
import random
import sys

from PIL import Image

from . import roles
from . import myresources


IMAGE_SIZE = 60


def _champ_to_champ_id(champ):
    if champ == "Wukong":
        return "MonkeyKing"
    if champ == "Nunu & Willump":
        return "Nunu"
    if champ == "Renata Glasc":
        return "Renata"
    if champ == "Kog'Maw":
        return "KogMaw"
    if champ == "LeBlanc":
        return "Leblanc"
    if champ == "K'Sante":
        return "KSante"
    if champ == "Rek'Sai":
        return "RekSai"
    if "'" in champ:
        champ = champ[:champ.find("'")] + champ[champ.find("'"):].lower()
    return champ.replace(" ", "").replace(".", "").replace("'", "")


def get_random_champs_weighted(N):
    ceiled_N = math.ceil(N / 5) * 5
    champs_by_role = {role: [] for role in roles.ROLES}
    champs_by_occurence = {}
    inverse_champs_by_occurence = {}

    for champ_data in myresources.CHAMPS_WITH_ROLE_DATA:
        champ, parsed_roles = champ_data.split("\t")[0], champ_data.split("\t")[1:-1]
        champs_by_occurence[champ] = 0
        for parsed_role, ROLE in zip(parsed_roles, roles.ROLES):
            if parsed_role:
                champs_by_role[ROLE].append(champ)
                champs_by_occurence[champ] += 1
        inverse_champs_by_occurence[champ] = round(1 / champs_by_occurence[champ] * 60)


    selected_champs = []
    for role in roles.ROLES:
        weighted_champs = sum([[champ] * inverse_champs_by_occurence[champ] for champ in champs_by_role[role]], start=[])
        random.shuffle(weighted_champs)
        i = 0
        while i < ceiled_N // 5:
            potential_champ = weighted_champs.pop()
            if potential_champ not in selected_champs:
                selected_champs.append(potential_champ)
                i += 1

    if N < ceiled_N:
        for _ in range(ceiled_N - N):
            selected_champs.remove(selected_champs[random.randint(0, len(selected_champs)-1)])

    return selected_champs


def make_grid_from_champs(champs):
    champ_images = [myresources.IMAGE_BY_CHAMP_ID[_champ_to_champ_id(champ)] for champ in champs]
    champ_images = [champ_image.resize((IMAGE_SIZE, IMAGE_SIZE)) for champ_image in champ_images]
    if len(champs) % 5 == 0:
        width = len(champs) // 5
        height = 5
    else:
        width = math.ceil(math.sqrt(len(champs)))
        height = round(math.sqrt(len(champs)))

    grid = Image.new('RGB', (width * IMAGE_SIZE, height * IMAGE_SIZE))
    for index, img in enumerate(champ_images):
        row = index // width
        col = index % width
        grid.paste(img, (col * IMAGE_SIZE, row * IMAGE_SIZE))
    return grid



if __name__ == "__main__":
    N = 40
    if len(sys.argv) == 2:
        N = int(sys.argv[1])
    selected_champs = get_random_champs_weighted(N=N)
    img = make_grid_from_champs(selected_champs)
    img.save("test.png")
    print(", ".join(selected_champs))
